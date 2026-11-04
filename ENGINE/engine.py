#!/usr/bin/env python3
"""
Antigravity Local CYOA Engine Server
===================================
A standalone local orchestration server for running CYOA turns locally.
Connects with the PWA frontend (running on port 3000) and exposes:
- POST /generate: End-to-end 7-step orchestrated pipeline:
  Step 1: ModeValidator.validate_action() checks action vs mode.
  Step 2: PacingController.evaluate_focus() & validate_transition() evaluates zoom and transitions.
  Step 3: PacingController.advance_time() computes elapsed minutes and fires event clocks.
  Step 4: PromptAssembler.build_system_prompt() loads foundation, lore, state, and active turns.
  Step 5: Generate narrative response (mock or model output).
  Step 6: StyleContractValidator.validate_prose() checks output against campaign style contract.
  Step 7: TransactionManager stages mutations and commits atomically with idempotency token.
- GET /health: Status and active diagnostics (operational_mode, zoom_level, in-game elapsed time, features).

CORS enabled for local web and PWA clients.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import local engine modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.prompt_assembler import PromptAssembler
from ENGINE.state_parser import StateParser
from ENGINE.mode_validator import ModeValidator, validate_action, get_campaign_mode
from ENGINE.pacing_controller import (
    PacingController,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP,
    VALID_ZOOM_LEVELS
)
from ENGINE.style_contract import StyleContractValidator
from ENGINE.transaction_manager import TransactionManager, TransactionError

PORT = int(os.environ.get("ANTIGRAVITY_PORT", 8000))


class EngineRequestHandler(BaseHTTPRequestHandler):
    current_mode = "classic_cyoa"
    current_zoom = "detailed_scene"
    current_elapsed_time = 0

    def _set_cors_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(204)

    def do_GET(self):
        if self.path in ["/", "/health", "/status"]:
            self._set_cors_headers(200)
            status_data = {
                "status": "online",
                "engine": "Antigravity Local CYOA Orchestrator",
                "root_dir": ROOT_DIR,
                "version": "1.0.0",
                "operational_mode": getattr(EngineRequestHandler, "current_mode", "classic_cyoa"),
                "zoom_level": getattr(EngineRequestHandler, "current_zoom", "detailed_scene"),
                "elapsed_time": getattr(EngineRequestHandler, "current_elapsed_time", 0),
                "in_game_elapsed_time": getattr(EngineRequestHandler, "current_elapsed_time", 0),
                "elapsed_time_minutes": getattr(EngineRequestHandler, "current_elapsed_time", 0),
                "engine_features": [
                    "mode_validator",
                    "pacing_controller",
                    "prompt_assembler",
                    "style_contract",
                    "transaction_manager",
                    "world_foundation"
                ]
            }
            self.wfile.write(json.dumps(status_data).encode("utf-8"))
        elif self.path in ["/v1/models", "/api/models"]:
            self._set_cors_headers(200)
            models_data = {
                "object": "list",
                "data": [
                    {"id": "local-antigravity", "object": "model", "owned_by": "antigravity"},
                    {"id": "gemini-2.5-flash", "object": "model", "owned_by": "google"},
                    {"id": "gemini-2.5-pro", "object": "model", "owned_by": "google"}
                ]
            }
            self.wfile.write(json.dumps(models_data).encode("utf-8"))
        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def do_POST(self):
        if self.path in ["/generate", "/v1/chat/completions", "/api/turn"]:
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)
            try:
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {str(e)}"}).encode("utf-8"))
                return

            player_action = payload.get("action", "")
            campaign = payload.get("campaign", "")
            pacing = payload.get("pacing", "standard")
            turn_num = payload.get("currentTurn")
            if turn_num is None:
                turn_num = payload.get("turn", 1)
            try:
                turn_num = int(turn_num)
            except (ValueError, TypeError):
                turn_num = 1

            # Resolve campaign workspace directory
            campaign_dir = payload.get("campaign_dir")
            if not campaign_dir and campaign:
                cand = os.path.join(ROOT_DIR, "CAMPAIGNS", campaign)
                if os.path.isdir(cand):
                    campaign_dir = cand

            # Resolve workspace root directory if custom campaign_dir is supplied
            workspace_root = ROOT_DIR
            if campaign_dir and os.path.isdir(campaign_dir):
                parent = os.path.dirname(campaign_dir)
                if os.path.basename(parent) == "CAMPAIGNS":
                    workspace_root = os.path.dirname(parent)
            if payload.get("root_dir"):
                workspace_root = payload.get("root_dir")

            # Resolve operational mode
            mode = payload.get("operational_mode") or payload.get("mode")
            if not mode:
                mode = ModeValidator.get_campaign_mode(campaign, workspace_root)

            # Idempotency token generation & early check for retries
            idempotency_token = TransactionManager.generate_transaction_id(turn_num, player_action)
            committed_record = None
            if campaign_dir and os.path.isdir(campaign_dir):
                committed_record = TransactionManager.get_committed_transaction(
                    campaign_dir=campaign_dir,
                    transaction_id=idempotency_token,
                    turn=turn_num,
                    action=player_action
                )

            if committed_record:
                # Return the existing committed transaction without re-executing mutations
                turn_file_rel = f"TURNS/ACTIVE/turn_{turn_num:04d}.md"
                turn_file_path = os.path.join(campaign_dir, turn_file_rel)
                cached_resp = "Turn already committed."
                if os.path.exists(turn_file_path):
                    try:
                        with open(turn_file_path, "r", encoding="utf-8") as f:
                            t_content = f.read()
                        if "## GM Response" in t_content:
                            cached_resp = t_content.split("## GM Response", 1)[1].split("## System State Delta", 1)[0].strip()
                        else:
                            cached_resp = t_content
                    except Exception:
                        pass

                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "response": cached_resp,
                    "transaction_id": idempotency_token,
                    "idempotency_token": idempotency_token,
                    "mode": mode,
                    "committed": True,
                    "retry": True
                }).encode("utf-8"))
                return

            # -------------------------------------------------------------
            # STEP 1: ModeValidator.validate_action()
            # -------------------------------------------------------------
            is_valid, error_msg, parsed_action = ModeValidator.validate_action(
                action=player_action,
                mode=mode,
                campaign_id=campaign,
                root_dir=workspace_root
            )

            if not is_valid:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "error": "INVALID_ACTION",
                    "message": error_msg,
                    "mode": mode
                }).encode("utf-8"))
                return

            # -------------------------------------------------------------
            # STEP 2: PacingController.evaluate_focus() & validate_transition()
            # -------------------------------------------------------------
            pacing_ctrl = PacingController()

            pacing_state = payload.get("pacing_state")
            if not pacing_state and isinstance(payload.get("state"), dict):
                pacing_state = payload.get("state", {}).get("pacing_state")
            if not pacing_state and campaign_dir and os.path.exists(os.path.join(campaign_dir, "GAMEPLAY", "status.json")):
                try:
                    with open(os.path.join(campaign_dir, "GAMEPLAY", "status.json"), "r", encoding="utf-8") as f:
                        pacing_state = json.load(f).get("pacing_state")
                except Exception:
                    pass
            if not pacing_state:
                pacing_state = PacingController.create_default_pacing()

            proposed_zoom = (
                payload.get("proposed_zoom")
                or payload.get("zoom_level")
                or pacing_ctrl.evaluate_focus(player_action, pacing_state)
            )
            proposed_time_skip = int(payload.get("proposed_time_skip_minutes", 0))
            proposed_intensity = payload.get("proposed_intensity")
            if proposed_intensity is None:
                proposed_intensity = pacing_ctrl.recommend_intensity(player_action, pacing_state)
            else:
                proposed_intensity = int(proposed_intensity)

            proposed_location = payload.get("proposed_location")
            causal_justification = bool(payload.get("causal_justification", False))
            explicit_permission = bool(payload.get("explicit_permission", False))

            is_allowed, transition_reason = pacing_ctrl.validate_transition(
                current_pacing=pacing_state,
                proposed_action=player_action,
                proposed_zoom=proposed_zoom,
                proposed_time_skip_minutes=proposed_time_skip,
                proposed_intensity=proposed_intensity,
                proposed_location=proposed_location,
                causal_justification=causal_justification,
                explicit_permission=explicit_permission,
            )

            if not is_allowed:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "error": "TRANSITION_REJECTED",
                    "message": transition_reason,
                    "zoom_level": pacing_state.get("zoom_level"),
                    "pacing_state": pacing_state
                }).encode("utf-8"))
                return

            # -------------------------------------------------------------
            # STEP 3: PacingController.advance_time() & event clocks
            # -------------------------------------------------------------
            delta_minutes = payload.get("delta_minutes")
            if delta_minutes is None:
                if proposed_time_skip > 0:
                    delta_minutes = proposed_time_skip
                elif proposed_zoom == ZOOM_TIME_SKIP:
                    delta_minutes = 480
                elif proposed_zoom == ZOOM_MONTAGE:
                    delta_minutes = 1440
                elif proposed_zoom == ZOOM_SHORT_SUMMARY:
                    delta_minutes = 30
                else:
                    delta_minutes = 10
            else:
                delta_minutes = int(delta_minutes)

            updated_pacing, triggered_events = pacing_ctrl.advance_time(
                current_pacing=pacing_state,
                delta_minutes=delta_minutes
            )
            updated_pacing["zoom_level"] = proposed_zoom
            updated_pacing["narrative_intensity"] = proposed_intensity
            if proposed_location:
                updated_pacing["current_location"] = proposed_location

            # Update engine diagnostic state
            EngineRequestHandler.current_mode = mode
            EngineRequestHandler.current_zoom = proposed_zoom
            EngineRequestHandler.current_elapsed_time = updated_pacing.get("elapsed_time_minutes", 0)

            # -------------------------------------------------------------
            # STEP 4: PromptAssembler.build_system_prompt()
            # -------------------------------------------------------------
            assembler = PromptAssembler(workspace_root)
            system_prompt = assembler.build_system_prompt(campaign) if campaign else ""

            # -------------------------------------------------------------
            # STEP 5: Generate narrative response
            # -------------------------------------------------------------
            response_text = self.generate_turn(
                campaign, player_action, pacing, turn_num, payload, system_prompt=system_prompt
            )

            # -------------------------------------------------------------
            # STEP 6: StyleContractValidator.validate_prose()
            # -------------------------------------------------------------
            style_validator = StyleContractValidator.from_campaign(campaign, workspace_root)
            is_style_valid, violations, style_score = style_validator.validate_prose(response_text)

            # -------------------------------------------------------------
            # STEP 7: TransactionManager stages mutations and commits atomically
            # -------------------------------------------------------------
            idempotency_token = TransactionManager.generate_transaction_id(turn_num, player_action)

            committed_record = None
            if campaign_dir and os.path.isdir(campaign_dir):
                committed_record = TransactionManager.get_committed_transaction(
                    campaign_dir=campaign_dir,
                    transaction_id=idempotency_token,
                    turn=turn_num,
                    action=player_action
                )

            tx_result = None
            if not committed_record:
                tx_mgr = TransactionManager(campaign_dir)
                tx_mgr.current_transaction_id = idempotency_token
                tx_mgr.current_turn = turn_num
                tx_mgr.current_action = player_action

                should_commit = payload.get("commit", True)
                # Avoid modifying template_campaign repository files during unconfigured calls
                if campaign == "template_campaign" and "campaign_dir" not in payload and not payload.get("commit"):
                    should_commit = False

                if campaign_dir and os.path.isdir(campaign_dir) and should_commit:
                    tx_result = tx_mgr.execute_narrative_turn(
                        campaign_dir=campaign_dir,
                        turn=turn_num,
                        action=player_action,
                        gm_output=response_text,
                        metadata={
                            "pacing_state": updated_pacing,
                            "zoom_level": proposed_zoom,
                            "narrative_intensity": proposed_intensity,
                            "idempotency_token": idempotency_token
                        }
                    )
                    # Persist pacing_state in status.json
                    status_path = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
                    if os.path.exists(status_path):
                        try:
                            with open(status_path, "r", encoding="utf-8") as f:
                                s_data = json.load(f)
                            s_data["pacing_state"] = updated_pacing
                            with open(status_path, "w", encoding="utf-8") as f:
                                json.dump(s_data, f, indent=2)
                        except Exception:
                            pass

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "response": response_text,
                "transaction_id": idempotency_token,
                "idempotency_token": idempotency_token,
                "mode": mode,
                "zoom_level": proposed_zoom,
                "narrative_intensity": proposed_intensity,
                "pacing_state": updated_pacing,
                "triggered_events": triggered_events,
                "style_score": style_score,
                "style_valid": is_style_valid,
                "committed": (tx_result is not None or committed_record is not None)
            }).encode("utf-8"))
        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown POST route"}).encode("utf-8"))

    def generate_turn(
        self, campaign: str, action: str, pacing: str, turn: int, payload: dict, system_prompt: str = ""
    ) -> str:
        # Check if environment or payload has a Gemini key to perform direct LLM generation
        api_key = payload.get("apiKey") or payload.get("api_key") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                return self._call_cloud_gemini(api_key, campaign, action, pacing, turn, system_prompt)
            except Exception as e:
                print(f"[Engine] Cloud Gemini call failed: {e}. Falling back to rule-based simulation.")

        # Local Engine Simulation adhering strictly to CORE-002, CORE-003 receipts & numbered choices
        next_turn = turn + 1
        state = payload.get("state") if isinstance(payload.get("state"), dict) else None
        summary = self._metric_summary(campaign, state)
        sys_line = f"[SYS: Turn {next_turn}" + (f" | {summary}" if summary else "") + " | Checkpoints: 5/5]"

        # Generic rule-based fallback (campaign-agnostic, deterministic).
        return (
            "Your action resolves cleanly amidst the shifting currents of the adventure. "
            "Taking stock of your surroundings, you observe the immediate ripple effects of your choice.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Press forward along your primary path.\n"
            "2. Inspect your immediate environment for hidden clues or resources.\n"
            "3. Confer with your companions to consolidate strategy.\n"
            "4. Rest and recover your somatic vitals before proceeding.\n\n"
            f"{sys_line}"
        )

    def _campaign_metrics(self, campaign: str) -> list:
        """Return the metric definitions declared by a campaign, if any."""
        if not campaign:
            return []
        config_path = os.path.join(ROOT_DIR, "CAMPAIGNS", campaign, "campaign_config.json")
        if not os.path.exists(config_path):
            return []
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("metrics", []) or []
        except Exception:
            return []

    @staticmethod
    def _resolve_path(data, path):
        if not isinstance(data, dict) or not path:
            return None
        node = data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]
        return node

    def _metric_summary(self, campaign: str, state) -> str:
        """Render a SYS-block summary from the campaign's declared metrics and the supplied state."""
        parts = []
        for metric in self._campaign_metrics(campaign):
            if metric.get("id") == "turn":
                continue
            value = self._resolve_path(state, metric.get("path"))
            if value is None:
                continue
            label = metric.get("label") or metric.get("id") or "Metric"
            max_value = self._resolve_path(state, metric.get("max_path")) if metric.get("max_path") else None
            if max_value is not None and metric.get("type") != "text":
                parts.append(f"{label}: {value} / {max_value}")
            else:
                parts.append(f"{label}: {value}")
        return " | ".join(parts)

    def _call_cloud_gemini(
        self, api_key: str, campaign: str, action: str, pacing: str, turn: int, system_prompt: str = ""
    ) -> str:
        if not system_prompt:
            assembler = PromptAssembler(workspace_root)
            system_prompt = assembler.build_system_prompt(campaign)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        body = {
            "contents": [{"role": "user", "parts": [{"text": f"Player Action for Turn {turn}: {action}"}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]}
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"]


def main():
    server = HTTPServer(("0.0.0.0", PORT), EngineRequestHandler)
    print(f"==================================================")
    print(f" Antigravity Local Engine Server Running on Port {PORT}")
    print(f" Endpoint: http://localhost:{PORT}/generate")
    print(f" Ready to receive CYOA turn requests from UI...")
    print(f"==================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Local Engine...")
        server.server_close()


if __name__ == "__main__":
    main()
