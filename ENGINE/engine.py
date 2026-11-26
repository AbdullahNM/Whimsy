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
import time
import copy
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
from ENGINE.deterministic_core import Core, ActionValidationError, TransitionRejectedError
from ENGINE.outcome import Outcome
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
DEFAULT_BIND_HOST = os.environ.get("WHIMSY_HOST") or ("0.0.0.0" if os.path.exists("/.dockerenv") else "127.0.0.1")

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
FASTROUTER_CHAT_URL = "https://api.fastrouter.ai/api/v1/chat/completions"
PUBLIC_BUNDLED_CAMPAIGNS = frozenset({"template_campaign", "sample_campaign"})


def _is_safe_http_url(url: str) -> bool:
    """Allow https:// URLs or loopback http:// URLs only."""
    from urllib.parse import urlparse
    parsed = urlparse(url.strip())
    if parsed.scheme == "https" and bool(parsed.netloc):
        return True
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        return True
    return False


def resolve_llm_config(payload: dict) -> dict:
    """
    Resolve provider, API key, model, and endpoint URL with strict credential isolation:
    - Caller-supplied endpoints/providers NEVER receive server environment credentials.
    - Each server environment key is strictly paired with its own trusted endpoint.
    """
    payload = payload or {}
    caller_key = (payload.get("apiKey") or payload.get("api_key") or "").strip()
    caller_provider = (payload.get("provider") or "").strip().lower()
    caller_base = (payload.get("apiBaseUrl") or payload.get("api_base_url") or "").strip()
    caller_model = (payload.get("model") or "").strip()

    # Path 1: Caller supplied their own API key
    if caller_key:
        if caller_base and not _is_safe_http_url(caller_base):
            return {
                "provider": caller_provider or "custom",
                "api_key": "",
                "model": caller_model,
                "api_base": "",
                "credential_error": "Caller-supplied apiBaseUrl must use https:// or loopback http://.",
            }

        provider = caller_provider
        if not provider:
            if caller_base:
                if "fastrouter.ai" in caller_base:
                    provider = "fastrouter"
                elif "openrouter.ai" in caller_base:
                    provider = "openrouter"
                else:
                    provider = "custom"
            elif caller_model.startswith("fastrouter/"):
                provider = "fastrouter"
            elif caller_key.startswith("sk-or-") or caller_model.startswith("openrouter/"):
                provider = "openrouter"
            elif caller_key.startswith("AIza") or (caller_model.startswith("gemini") and "/" not in caller_model):
                provider = "gemini"
            else:
                provider = "openrouter"

        model = caller_model
        if provider == "fastrouter" and (not model or model in ("local-antigravity", "local-endpoint")):
            model = "openai/gpt-4o-mini"
        elif provider == "openrouter" and (not model or model in ("local-antigravity", "local-endpoint")):
            model = "anthropic/claude-3.5-sonnet"
        elif provider == "gemini" and (not model or model in ("local-antigravity", "local-endpoint")):
            model = "gemini-2.5-flash"

        if provider == "fastrouter":
            trusted_base = caller_base or FASTROUTER_CHAT_URL
        elif provider == "openrouter":
            trusted_base = caller_base or OPENROUTER_CHAT_URL
        elif provider == "custom":
            trusted_base = caller_base
        else:
            trusted_base = ""

        return {
            "provider": provider,
            "api_key": caller_key,
            "model": model,
            "api_base": trusted_base,
        }

    # Path 2: No caller key -> NEVER let caller_base or custom provider steer env secrets
    if caller_base or caller_provider == "custom":
        return {
            "provider": caller_provider or "custom",
            "api_key": "",
            "model": caller_model,
            "api_base": "",
            "credential_error": "Caller-selected endpoint requires a caller-supplied apiKey.",
        }

    env_whimsy_key = (os.environ.get("WHIMSY_API_KEY") or "").strip()
    env_whimsy_provider = (os.environ.get("WHIMSY_PROVIDER") or "").strip().lower()
    env_whimsy_base = (os.environ.get("WHIMSY_API_BASE") or "").strip()
    env_fr_key = (os.environ.get("FASTROUTER_API_KEY") or "").strip()
    env_or_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    env_gem_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    env_model = (os.environ.get("WHIMSY_MODEL") or "").strip()

    # Determine requested or server-default provider without cross-sending keys
    target_provider = caller_provider or env_whimsy_provider
    if not target_provider:
        if caller_model.startswith("fastrouter/") or env_fr_key:
            target_provider = "fastrouter"
        elif caller_model.startswith("openrouter/") or env_or_key:
            target_provider = "openrouter"
        elif env_whimsy_key and env_whimsy_base:
            target_provider = "custom"
        elif env_gem_key:
            target_provider = "gemini"

    if target_provider == "fastrouter":
        if not env_fr_key and not (env_whimsy_key and env_whimsy_provider == "fastrouter"):
            return {"provider": "fastrouter", "api_key": "", "model": caller_model, "api_base": ""}
        return {
            "provider": "fastrouter",
            "api_key": env_fr_key or env_whimsy_key,
            "model": caller_model or env_model or os.environ.get("FASTROUTER_MODEL") or "openai/gpt-4o-mini",
            "api_base": FASTROUTER_CHAT_URL,
        }

    if target_provider == "openrouter":
        if not env_or_key and not (env_whimsy_key and env_whimsy_provider == "openrouter"):
            return {"provider": "openrouter", "api_key": "", "model": caller_model, "api_base": ""}
        return {
            "provider": "openrouter",
            "api_key": env_or_key or env_whimsy_key,
            "model": caller_model or env_model or os.environ.get("OPENROUTER_MODEL") or "anthropic/claude-3.5-sonnet",
            "api_base": OPENROUTER_CHAT_URL,
        }

    if target_provider == "gemini":
        if not env_gem_key and not (env_whimsy_key and env_whimsy_provider == "gemini"):
            return {"provider": "gemini", "api_key": "", "model": caller_model, "api_base": ""}
        return {
            "provider": "gemini",
            "api_key": env_gem_key or env_whimsy_key,
            "model": caller_model or env_model or "gemini-2.5-flash",
            "api_base": "",
        }

    if target_provider == "custom" and env_whimsy_key and env_whimsy_base and _is_safe_http_url(env_whimsy_base):
        return {
            "provider": "custom",
            "api_key": env_whimsy_key,
            "model": caller_model or env_model or "gpt-4o-mini",
            "api_base": env_whimsy_base,
        }

    return {"provider": target_provider, "api_key": "", "model": caller_model or env_model, "api_base": ""}


def _read_text_safe(path: str) -> str:
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _read_json_safe(path: str):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _is_campaign_api_allowed(campaign_id: str) -> bool:
    """Allow public bundled campaigns over CORS HTTP by default; private campaigns require explicit opt-in."""
    if os.environ.get("WHIMSY_ALLOW_PRIVATE_CAMPAIGN_API") == "1":
        return True
    return campaign_id in PUBLIC_BUNDLED_CAMPAIGNS


def list_workspace_campaigns(root_dir: str) -> list[dict]:
    """List exposed campaigns with valid campaign_config.json under CAMPAIGNS/."""
    campaigns_dir = os.path.join(root_dir, "CAMPAIGNS")
    items = []
    if not os.path.isdir(campaigns_dir):
        return items
    for name in sorted(os.listdir(campaigns_dir)):
        if not _is_campaign_api_allowed(name):
            continue
        cdir = os.path.join(campaigns_dir, name)
        cfg_path = os.path.join(cdir, "campaign_config.json")
        if os.path.isdir(cdir) and os.path.isfile(cfg_path):
            cfg = _read_json_safe(cfg_path)
            if isinstance(cfg, dict):
                cid = cfg.get("id", name)
                if _is_campaign_api_allowed(cid):
                    items.append({"id": cid, "config": cfg})
    return items


def load_campaign_bundle(root_dir: str, campaign_id: str) -> dict | None:
    """Load full disk state for a campaign so the browser UI can hydrate without FSA."""
    if not campaign_id or ".." in campaign_id or "/" in campaign_id or "\\" in campaign_id:
        return None
    cdir = os.path.join(root_dir, "CAMPAIGNS", campaign_id)
    if not os.path.isdir(cdir):
        return None

    cfg = _read_json_safe(os.path.join(cdir, "campaign_config.json"))
    if not isinstance(cfg, dict):
        return None

    gp_dir = os.path.join(cdir, "GAMEPLAY")
    active_dir = os.path.join(cdir, "TURNS", "ACTIVE")
    active_turns = []
    if os.path.isdir(active_dir):
        for fname in sorted(os.listdir(active_dir)):
            if fname.endswith(".md"):
                active_turns.append({
                    "name": fname,
                    "content": _read_text_safe(os.path.join(active_dir, fname)),
                })

    world_bible = {}
    bible_dir = os.path.join(cdir, "WORLD_BIBLE")
    if os.path.isdir(bible_dir):
        import re as _re
        for cat in sorted(os.listdir(bible_dir)):
            cat_dir = os.path.join(bible_dir, cat)
            if not os.path.isdir(cat_dir):
                continue
            articles = []
            for fname in sorted(os.listdir(cat_dir)):
                if not fname.endswith(".md"):
                    continue
                content = _read_text_safe(os.path.join(cat_dir, fname))
                m = _re.search(r"^#\s+(.+)$", content, _re.MULTILINE)
                title = m.group(1).strip() if m else os.path.splitext(fname)[0].replace("_", " ").title()
                articles.append({
                    "id": os.path.splitext(fname)[0],
                    "title": title,
                    "content": content,
                })
            if articles:
                world_bible[cat] = articles

    from ENGINE.agent_channel import AgentChannelManager
    channel_msgs = AgentChannelManager(cdir).load_messages(force_disk=True)

    return {
        "campaign_id": cfg.get("id", campaign_id),
        "config": cfg,
        "status_json": _read_json_safe(os.path.join(gp_dir, "status.json")),
        "status": _read_text_safe(os.path.join(gp_dir, "status.md")),
        "relations_json": _read_json_safe(os.path.join(gp_dir, "relations.json")),
        "relations": _read_text_safe(os.path.join(gp_dir, "relations.md")),
        "items_json": _read_json_safe(os.path.join(gp_dir, "items.json")),
        "items": _read_text_safe(os.path.join(gp_dir, "items.md")),
        "upcoming_hooks": _read_text_safe(os.path.join(gp_dir, "upcoming_hooks.md")),
        "ontology_json": (
            _read_json_safe(os.path.join(cdir, "ontology.json"))
            or _read_json_safe(os.path.join(cdir, "WORLD_FOUNDATION", "ontology.json"))
        ),
        "narrative_steering": _read_text_safe(os.path.join(cdir, "IDEAS", "narrative_steering.md")),
        "agent_channel": channel_msgs,
        "active_turns": active_turns,
        "world_bible": world_bible,
    }


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
                    {"id": "openrouter/anthropic/claude-3.5-sonnet", "object": "model", "owned_by": "openrouter"},
                    {"id": "openrouter/google/gemini-2.5-flash", "object": "model", "owned_by": "openrouter"},
                    {"id": "fastrouter/openai/gpt-4o-mini", "object": "model", "owned_by": "fastrouter"},
                    {"id": "fastrouter/anthropic/claude-3.5-sonnet", "object": "model", "owned_by": "fastrouter"},
                    {"id": "gemini-2.5-flash", "object": "model", "owned_by": "google"},
                    {"id": "gemini-2.5-pro", "object": "model", "owned_by": "google"}
                ]
            }
            self.wfile.write(json.dumps(models_data).encode("utf-8"))
        elif self.path in ["/campaigns", "/api/campaigns"]:
            campaigns = list_workspace_campaigns(ROOT_DIR)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "campaigns": [c["id"] for c in campaigns],
                "configs": {c["id"]: c["config"] for c in campaigns}
            }).encode("utf-8"))
        elif self.path.startswith("/api/campaign?") or self.path.startswith("/campaign?"):
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            campaign = query.get("campaign", ["template_campaign"])[0]
            if not _is_campaign_api_allowed(campaign):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"error": "Private campaign bundle access is disabled over HTTP."}).encode("utf-8"))
                return
            bundle = load_campaign_bundle(ROOT_DIR, campaign)
            if not bundle:
                self._set_cors_headers(404)
                self.wfile.write(json.dumps({"error": f"Campaign '{campaign}' not found"}).encode("utf-8"))
                return
            self._set_cors_headers(200)
            self.wfile.write(json.dumps(bundle).encode("utf-8"))
        elif self.path.startswith("/telemetry") or self.path.startswith("/api/telemetry"):
            from urllib.parse import urlparse, parse_qs
            from ENGINE.telemetry import get_campaign_telemetry_summary, read_campaign_telemetry
            query = parse_qs(urlparse(self.path).query)
            campaign = query.get("campaign", ["template_campaign"])[0]
            summary = get_campaign_telemetry_summary(ROOT_DIR, campaign)
            records = read_campaign_telemetry(ROOT_DIR, campaign)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "campaign": campaign,
                "summary": summary,
                "records": records
            }).encode("utf-8"))
        elif self.path.startswith("/calibration") or self.path.startswith("/api/calibration"):
            from urllib.parse import urlparse, parse_qs
            from ENGINE.calibration import get_calibration_advisory
            query = parse_qs(urlparse(self.path).query)
            campaign = query.get("campaign", ["template_campaign"])[0]
            advisory = get_calibration_advisory(ROOT_DIR, campaign)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "campaign": campaign,
                "calibration": advisory.to_dict()
            }).encode("utf-8"))
        elif self.path.startswith("/api/channel"):
            from urllib.parse import urlparse, parse_qs
            from ENGINE.agent_channel import AgentChannelManager
            query = parse_qs(urlparse(self.path).query)
            campaign = query.get("campaign", ["template_campaign"])[0]
            role = query.get("role", [None])[0]
            mode = query.get("mode", [None])[0]

            campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", campaign)
            if not os.path.isdir(campaign_dir):
                campaign_dir = os.path.join(os.path.dirname(ROOT_DIR), "whimsy-campaigns", campaign)

            manager = AgentChannelManager(campaign_dir, channel_mode=mode)
            messages = manager.load_messages()
            if role:
                from ENGINE.agent_channel import normalize_sender
                norm_role = normalize_sender(role)
                messages = [m for m in messages if normalize_sender(m.get("recipient", "")) == norm_role]

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "campaign": campaign,
                "channel_mode": manager.channel_mode,
                "file_fallback": True,
                "file_path": manager.md_path,
                "messages": messages
            }).encode("utf-8"))
        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

    def do_POST(self):
        if self.path in ["/generate", "/v1/chat/completions", "/api/turn"]:
            t_gen_start = time.time()
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

            should_commit = payload.get("commit", True)
            if campaign == "template_campaign" and "campaign_dir" not in payload and not payload.get("commit"):
                should_commit = False

            # Idempotency token generation & early check for retries (skipped when commit is False)
            idempotency_token = TransactionManager.generate_transaction_id(turn_num, player_action)
            committed_record = None
            if should_commit and campaign_dir and os.path.isdir(campaign_dir):
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

            # =============================================================
            # STEP 1: RESOLVE (Core.resolve — Pure Deterministic Headless Engine)
            # =============================================================
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

            # Assemble state for pure functional Core resolution
            core_state = None
            if isinstance(payload.get("state"), dict):
                core_state = copy.deepcopy(payload["state"])
            elif campaign_dir and os.path.exists(os.path.join(campaign_dir, "GAMEPLAY", "status.json")):
                try:
                    with open(os.path.join(campaign_dir, "GAMEPLAY", "status.json"), "r", encoding="utf-8") as f:
                        core_state = json.load(f)
                except Exception:
                    pass
            if not core_state:
                core_state = {
                    "schema_version": 2,
                    "campaign_id": campaign or "template_campaign",
                    "turn": turn_num,
                    "timeline": "Act I",
                    "progression": {"checkpoint_tokens": 5, "checkpoint_max": 5},
                    "purse": {"display": "500 credits"},
                    "clocks": [],
                    "scene_anchor": {"location": "Starting Area", "context": "Beginning turn", "time": "Day 1, 08:00"},
                    "pacing_state": pacing_state,
                    "public_state": {"flags": {}, "conditions": [], "open_threads": []}
                }
            core_state["turn"] = turn_num
            core_state["pacing_state"] = pacing_state

            # Resolve offered choices if not present in state
            if "offered_choices" not in core_state:
                core_state["offered_choices"] = ModeValidator.extract_offered_choices(campaign, workspace_root)

            resolve_config = {
                "operational_mode": mode,
                "proposed_zoom": proposed_zoom,
                "proposed_time_skip_minutes": proposed_time_skip,
                "proposed_intensity": proposed_intensity,
                "proposed_location": proposed_location,
                "causal_justification": causal_justification,
                "explicit_permission": explicit_permission
            }

            try:
                outcome = Core.resolve(core_state, player_action, config=resolve_config)
            except ActionValidationError as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "error": "INVALID_ACTION",
                    "message": str(e),
                    "mode": mode
                }).encode("utf-8"))
                return
            except TransitionRejectedError as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "error": "TRANSITION_REJECTED",
                    "message": str(e),
                    "zoom_level": pacing_state.get("zoom_level"),
                    "pacing_state": pacing_state
                }).encode("utf-8"))
                return

            updated_pacing = outcome.next_state.get("pacing_state", pacing_state)
            triggered_events = outcome.events

            # Update engine diagnostic state
            EngineRequestHandler.current_mode = mode
            EngineRequestHandler.current_zoom = updated_pacing.get("zoom_level", proposed_zoom)
            EngineRequestHandler.current_elapsed_time = updated_pacing.get("elapsed_time_minutes", 0)

            # =============================================================
            # STEP 2: NARRATE (LLM or deterministic narrator describing the outcome)
            # =============================================================
            assembler = PromptAssembler(workspace_root)
            system_prompt = assembler.build_system_prompt(campaign) if campaign else ""

            response_text = self._call_model(
                campaign, player_action, pacing, turn_num, payload,
                system_prompt=system_prompt, outcome=outcome
            )

            # =============================================================
            # STEP 3: VALIDATE (StyleContract + fourth-wall seal vs outcome)
            # =============================================================
            style_validator = StyleContractValidator.from_campaign(campaign, workspace_root)
            is_style_valid, violations, style_score = style_validator.validate_prose(
                response_text, outcome=outcome
            )

            # Style enforcement configuration with payload overrides
            strict_style_enforcement = (
                payload.get("strict_style_enforcement")
                if payload.get("strict_style_enforcement") is not None
                else style_validator.config.get("strict_style_enforcement", True)
            )
            strict_style_enforcement = bool(strict_style_enforcement)

            max_style_retries = (
                payload.get("max_style_retries")
                if payload.get("max_style_retries") is not None
                else style_validator.config.get("max_style_retries", 2)
            )
            try:
                max_style_retries = int(max_style_retries)
            except (ValueError, TypeError):
                max_style_retries = 2

            if not is_style_valid:
                # Step A: Attempt deterministic remediation first:
                # Strip formulaic turn closings (e.g. "What will you do?", "The choice is yours") using regex/string cleaning.
                cleaned_text = StyleContractValidator.strip_formulaic_closings(response_text)
                if cleaned_text != response_text:
                    valid_a, vios_a, score_a = style_validator.validate_prose(
                        cleaned_text, outcome=outcome
                    )
                    if valid_a:
                        response_text = cleaned_text
                        is_style_valid = True
                        violations = vios_a
                        style_score = score_a

                # Step B: If still invalid and strict_style_enforcement is enabled:
                if not is_style_valid and strict_style_enforcement:
                    current_prompt = system_prompt or ""
                    for _ in range(max_style_retries):
                        remediation_instruction = (
                            f"\n\n[STYLE CONTRACT CORRECTION REQUIRED]\n"
                            f"Your previous draft failed style contract validation with the following violations:\n- "
                            + "\n- ".join(violations)
                            + "\n\nRewrite the response resolving the player action while strictly complying with the style contract."
                        )
                        retry_prompt = current_prompt + remediation_instruction
                        retry_response = self._call_model(
                            campaign, player_action, pacing, turn_num, payload,
                            system_prompt=retry_prompt, outcome=outcome
                        )
                        valid_b, vios_b, score_b = style_validator.validate_prose(
                            retry_response, outcome=outcome
                        )
                        if not valid_b:
                            cleaned_retry = StyleContractValidator.strip_formulaic_closings(retry_response)
                            if cleaned_retry != retry_response:
                                valid_b_clean, vios_b_clean, score_b_clean = style_validator.validate_prose(
                                    cleaned_retry, outcome=outcome
                                )
                                if valid_b_clean:
                                    retry_response = cleaned_retry
                                    valid_b = True
                                    vios_b = vios_b_clean
                                    score_b = score_b_clean

                        response_text = retry_response
                        is_style_valid = valid_b
                        violations = vios_b
                        style_score = score_b

                        if is_style_valid:
                            break

                # Step C: If retries are exhausted and is_style_valid is still False:
                if not is_style_valid:
                    if strict_style_enforcement:
                        # DO NOT commit state (do not call execute_narrative_turn, do not mutate status.json or write turn_XXXX.md)
                        # Log telemetry event with style_commit_aborted=True
                        try:
                            from ENGINE.telemetry import record_turn_telemetry
                            gen_latency = (time.time() - t_gen_start) * 1000
                            pmt_tokens = int(len(system_prompt.split()) * 1.3) if system_prompt else 0
                            cmp_tokens = int(len(response_text.split()) * 1.3) if response_text else 0
                            record_turn_telemetry(
                                root_dir=workspace_root,
                                campaign_id=campaign or "template_campaign",
                                turn=turn_num,
                                latency_ms=gen_latency,
                                model=payload.get("model") or "local-heuristic",
                                operational_mode=mode,
                                zoom_level=updated_pacing.get("zoom_level", proposed_zoom),
                                narrative_intensity=updated_pacing.get("narrative_intensity", proposed_intensity),
                                prompt_tokens=pmt_tokens,
                                completion_tokens=cmp_tokens,
                                retrieval_hits=len(triggered_events) if triggered_events else 0,
                                style_violations=violations if violations else [],
                                outcome_state_delta=outcome.to_dict() if outcome else {},
                                style_commit_aborted=True
                            )
                        except Exception:
                            pass

                        self._set_cors_headers(422)
                        self.wfile.write(json.dumps({
                            "error": "Style contract validation failed after retries",
                            "violations": violations,
                            "style_score": style_score,
                            "prose": response_text
                        }).encode("utf-8"))
                        return
                    else:
                        # If not strict: log warning in telemetry and proceed as before
                        try:
                            from ENGINE.telemetry import record_turn_telemetry
                        except Exception:
                            pass

            # Validate progression pacing against Zero Micro-Scene Rule
            progression_data = StateParser.parse_progression_resolution(response_text)
            progression_valid = True
            progression_warning = None
            if progression_data and "delta" in progression_data:
                scene_type = updated_pacing.get("scene_type", "exploration")
                progression_valid, progression_warning = pacing_ctrl.validate_progression_pacing(
                    zoom_level=updated_pacing.get("zoom_level", proposed_zoom),
                    scene_type=scene_type,
                    delta=progression_data["delta"]
                )

            # =============================================================
            # STEP 4: PERSIST (TransactionManager stages mutations and commits atomically)
            # =============================================================
            should_commit = payload.get("commit", True)
            if campaign == "template_campaign" and "campaign_dir" not in payload and not payload.get("commit"):
                should_commit = False

            idempotency_token = TransactionManager.generate_transaction_id(turn_num, player_action)

            committed_record = None
            if should_commit and campaign_dir and os.path.isdir(campaign_dir):
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

                if campaign_dir and os.path.isdir(campaign_dir) and should_commit:
                    # Stage authoritative post-resolution next_state into status.json
                    status_json_rel = "GAMEPLAY/status.json"
                    tx_mgr.stage(status_json_rel, outcome.next_state)

                    tx_result = tx_mgr.execute_narrative_turn(
                        campaign_dir=campaign_dir,
                        turn=turn_num,
                        action=player_action,
                        gm_output=response_text,
                        metadata={
                            "outcome": outcome.to_dict(),
                            "pacing_state": updated_pacing,
                            "zoom_level": updated_pacing.get("zoom_level", proposed_zoom),
                            "narrative_intensity": updated_pacing.get("narrative_intensity", proposed_intensity),
                            "idempotency_token": idempotency_token
                        }
                    )

            # Record telemetry event
            try:
                from ENGINE.telemetry import record_turn_telemetry
                gen_latency = (time.time() - t_gen_start) * 1000
                pmt_tokens = int(len(system_prompt.split()) * 1.3) if 'system_prompt' in locals() and system_prompt else 0
                cmp_tokens = int(len(response_text.split()) * 1.3) if response_text else 0
                record_turn_telemetry(
                    root_dir=workspace_root,
                    campaign_id=campaign or "template_campaign",
                    turn=turn_num,
                    latency_ms=gen_latency,
                    model=payload.get("model") or "local-heuristic",
                    operational_mode=mode,
                    zoom_level=updated_pacing.get("zoom_level", proposed_zoom),
                    narrative_intensity=updated_pacing.get("narrative_intensity", proposed_intensity),
                    prompt_tokens=pmt_tokens,
                    completion_tokens=cmp_tokens,
                    retrieval_hits=len(triggered_events) if triggered_events else 0,
                    style_violations=violations if violations else [],
                    outcome_state_delta=outcome.to_dict() if outcome else {},
                    style_commit_aborted=False,
                    style_warning="Style contract validation failed but strict enforcement disabled" if not is_style_valid else None
                )
            except Exception as tel_err:
                pass

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "response": response_text,
                "transaction_id": idempotency_token,
                "idempotency_token": idempotency_token,
                "mode": mode,
                "zoom_level": updated_pacing.get("zoom_level", proposed_zoom),
                "narrative_intensity": updated_pacing.get("narrative_intensity", proposed_intensity),
                "pacing_state": updated_pacing,
                "triggered_events": triggered_events,
                "style_score": style_score,
                "style_valid": is_style_valid,
                "progression_valid": progression_valid,
                "progression_warning": progression_warning,
                "committed": (tx_result is not None or committed_record is not None),
                "outcome": outcome.to_dict()
            }).encode("utf-8"))
        elif self.path in ["/api/channel", "/api/channel/message"]:
            from ENGINE.agent_channel import AgentChannelManager
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
                return

            campaign = payload.get("campaign", "template_campaign")
            sender = payload.get("sender", "SHADOW")
            content = payload.get("content", "")
            turn = payload.get("turn")
            recipient = payload.get("recipient")
            mode = payload.get("mode")

            campaign_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", campaign)
            if not os.path.isdir(campaign_dir):
                campaign_dir = os.path.join(os.path.dirname(ROOT_DIR), "whimsy-campaigns", campaign)

            manager = AgentChannelManager(campaign_dir, channel_mode=mode)
            updated_messages = manager.post_message(
                sender=sender,
                content=content,
                turn=turn,
                recipient=recipient
            )

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "status": "success",
                "campaign": campaign,
                "channel_mode": manager.channel_mode,
                "file_fallback": True,
                "file_path": manager.md_path,
                "messages": updated_messages
            }).encode("utf-8"))
        elif self.path in ["/init_campaign", "/api/campaign/init", "/campaigns/create"]:
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {str(e)}"}).encode("utf-8"))
                return

            try:
                from ENGINE.campaign_builder import scaffold_campaign
                result = scaffold_campaign(ROOT_DIR, payload)
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"status": "created", **result}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": f"Failed to scaffold campaign: {str(e)}"}).encode("utf-8"))

        elif self.path in ["/evaluate/turn", "/api/evaluate/turn"]:
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {str(e)}"}).encode("utf-8"))
                return

            campaign = payload.get("campaign", payload.get("campaign_id", "template_campaign"))
            turn_num = payload.get("turn_num", payload.get("turn", 1))
            action = payload.get("action", "")
            response = payload.get("response", payload.get("gm_response", ""))

            try:
                from ENGINE.evaluator import Evaluator
                evaluator = Evaluator(ROOT_DIR)
                report = evaluator.evaluate_turn(
                    campaign_id=campaign,
                    turn_num=int(turn_num),
                    action=action,
                    response=response
                )
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(report.to_dict()).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": f"Evaluation error: {str(e)}"}).encode("utf-8"))

        elif self.path in ["/shadow/consult", "/api/shadow/consult"]:
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {str(e)}"}).encode("utf-8"))
                return

            campaign = payload.get("campaign", payload.get("campaign_id", "template_campaign"))
            query = payload.get("query", "")
            llm_cfg = resolve_llm_config(payload)
            post_to_channel = bool(payload.get("post_to_channel", False))
            apply_recal = bool(payload.get("apply_recal", False))
            try:
                from ENGINE.campaign_builder import consult_shadow_narrator
                result = consult_shadow_narrator(
                    ROOT_DIR,
                    campaign,
                    query,
                    api_key=llm_cfg.get("api_key") or None,
                    provider=llm_cfg.get("provider") or None,
                    model=llm_cfg.get("model") or None,
                    api_base_url=llm_cfg.get("api_base") or None,
                    post_to_channel=post_to_channel,
                    apply_recal=apply_recal,
                )
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(result).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": f"Shadow consultation error: {str(e)}"}).encode("utf-8"))
        elif self.path in ["/api/test_connection", "/test_connection"]:
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len)
            try:
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception as e:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"ok": False, "error": f"Invalid JSON payload: {str(e)}"}).encode("utf-8"))
                return

            llm_cfg = resolve_llm_config(payload)
            if llm_cfg.get("credential_error"):
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "ok": False,
                    "provider": llm_cfg["provider"],
                    "error": llm_cfg["credential_error"]
                }).encode("utf-8"))
                return
            if not llm_cfg["api_key"]:
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "ok": True,
                    "mode": "offline_deterministic",
                    "provider": "local-antigravity",
                    "message": "Local engine online (no cloud key supplied; deterministic fallback active)."
                }).encode("utf-8"))
                return

            try:
                reply = self._ping_llm(llm_cfg)
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "ok": True,
                    "provider": llm_cfg["provider"],
                    "model": llm_cfg["model"],
                    "message": f"Connected to {llm_cfg['provider']} ({llm_cfg['model']}): {reply[:80]}"
                }).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(502)
                self.wfile.write(json.dumps({
                    "ok": False,
                    "provider": llm_cfg["provider"],
                    "model": llm_cfg["model"],
                    "error": str(e)
                }).encode("utf-8"))
        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown POST route"}).encode("utf-8"))

    def _call_model(
        self, campaign: str, action: str, pacing: str, turn: int, payload: dict,
        system_prompt: str = "", outcome: Outcome = None
    ) -> str:
        llm_cfg = resolve_llm_config(payload)
        api_key = llm_cfg["api_key"]
        model = llm_cfg["model"]
        provider = llm_cfg["provider"]
        api_base = llm_cfg["api_base"]

        outcome_context = ""
        if outcome:
            outcome_context = (
                "\n\n[AUTHORITATIVE CORE OUTCOME (DO NOT MUTATE STATE BEYOND THIS)]:\n"
                f"{outcome.to_json()}\n"
                "\n[NARRATION OUTPUT FORMAT]:\n"
                "- Write 1 to 3 crisp, grounded sensory paragraphs (<=35 words per sentence).\n"
                "- Respect any active SHADOW -> ACTIVE directives from agent_channel.md.\n"
                "- Do NOT include formulaic endings like 'What will you do?' or 'The choice is yours'.\n"
                "- End with `### [OPTIONS & TYPABLE REFERENCE]` followed by 3 to 5 numbered choices, "
                "and finish with `[SYS: Turn <next_turn> | ... | Checkpoints: 5/5]`."
            )

        if api_key:
            full_system_prompt = (system_prompt + outcome_context) if system_prompt else outcome_context
            if provider == "fastrouter":
                try:
                    return self._call_fastrouter(api_key, campaign, action, pacing, turn, full_system_prompt, model=model, api_base=api_base)
                except Exception as e:
                    print(f"[Engine] FastRouter call failed: {e}. Falling back to rule-based simulation.")
            elif provider == "openrouter":
                try:
                    return self._call_openrouter(api_key, campaign, action, pacing, turn, full_system_prompt, model=model)
                except Exception as e:
                    print(f"[Engine] OpenRouter call failed: {e}. Falling back to rule-based simulation.")
            elif provider == "custom" and api_base:
                try:
                    return self._call_openai_compatible(api_base, api_key, campaign, action, pacing, turn, full_system_prompt, model=model)
                except Exception as e:
                    print(f"[Engine] Custom endpoint call failed: {e}. Falling back to rule-based simulation.")
            else:
                try:
                    return self._call_cloud_gemini(api_key, campaign, action, pacing, turn, full_system_prompt, model=model)
                except Exception as e:
                    print(f"[Engine] Cloud Gemini call failed: {e}. Falling back to rule-based simulation.")

        # Local Engine Simulation adhering strictly to CORE-002, CORE-003 receipts & numbered choices
        next_turn = turn + 1
        state = payload.get("state") if isinstance(payload.get("state"), dict) else (outcome.next_state if outcome else None)
        summary = self._metric_summary(campaign, state)
        sys_line = f"[SYS: Turn {next_turn}" + (f" | {summary}" if summary else "") + " | Checkpoints: 5/5]"

        if outcome and outcome.offered_choices:
            options_lines = [f"{c.get('index', i+1)}. {c.get('text', '')}" for i, c in enumerate(outcome.offered_choices)]
            options_str = "\n".join(options_lines)
        else:
            options_str = (
                "1. Press forward along your primary path.\n"
                "2. Inspect your immediate environment for hidden clues or resources.\n"
                "3. Confer with your companions to consolidate strategy.\n"
                "4. Rest and recover your somatic vitals before proceeding."
            )

        # Generic rule-based fallback (campaign-agnostic, deterministic).
        return (
            "Your action resolves cleanly amidst the shifting currents of the adventure. "
            "Taking stock of your surroundings, you observe the immediate ripple effects of your choice.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            f"{options_str}\n\n"
            f"{sys_line}"
        )

    def generate_turn(
        self, campaign: str, action: str, pacing: str, turn: int, payload: dict,
        system_prompt: str = "", outcome: Outcome = None
    ) -> str:
        return self._call_model(
            campaign, action, pacing, turn, payload,
            system_prompt=system_prompt, outcome=outcome
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

    def _ping_llm(self, llm_cfg: dict) -> str:
        """Minimal connectivity check for /api/test_connection."""
        provider = llm_cfg["provider"]
        api_key = llm_cfg["api_key"]
        model = llm_cfg["model"]
        api_base = llm_cfg["api_base"]

        if provider == "gemini":
            clean_model = (model or "gemini-2.5-flash").split("/")[-1]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
            body = {"contents": [{"role": "user", "parts": [{"text": "Reply with OK."}]}]}
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        url = api_base or (FASTROUTER_CHAT_URL if provider == "fastrouter" else OPENROUTER_CHAT_URL)
        target_model = model or ("openai/gpt-4o-mini" if provider == "fastrouter" else "anthropic/claude-3.5-sonnet")
        for prefix in ("openrouter/", "fastrouter/"):
            if target_model.startswith(prefix):
                target_model = target_model[len(prefix):]

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "Whimsy Local CYOA Engine"
        body = {
            "model": target_model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 16,
            "temperature": 0.0,
        }
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()

    def _call_cloud_gemini(
        self, api_key: str, campaign: str, action: str, pacing: str, turn: int, system_prompt: str = "", model: str = ""
    ) -> str:
        if not system_prompt:
            assembler = PromptAssembler(ROOT_DIR)
            system_prompt = assembler.build_system_prompt(campaign)
        clean_model = (model or "gemini-2.5-flash").split("/")[-1]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"

        body = {
            "contents": [{"role": "user", "parts": [{"text": f"Player Action for Turn {turn} (pacing={pacing}): {action}"}]}],
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

    def _call_openai_compatible(
        self, url: str, api_key: str, campaign: str, action: str, pacing: str, turn: int,
        system_prompt: str = "", model: str = "", extra_headers: dict = None
    ) -> str:
        if not system_prompt:
            assembler = PromptAssembler(ROOT_DIR)
            system_prompt = assembler.build_system_prompt(campaign)

        target_model = model or "anthropic/claude-3.5-sonnet"
        for prefix in ("openrouter/", "fastrouter/"):
            if target_model.startswith(prefix):
                target_model = target_model[len(prefix):]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"Player Action for Turn {turn} (pacing={pacing}): {action}"})

        body = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.7
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]

    def _call_fastrouter(
        self, api_key: str, campaign: str, action: str, pacing: str, turn: int,
        system_prompt: str = "", model: str = "", api_base: str = ""
    ) -> str:
        url = api_base or FASTROUTER_CHAT_URL
        target_model = model or os.environ.get("FASTROUTER_MODEL") or "openai/gpt-4o-mini"
        return self._call_openai_compatible(
            url, api_key, campaign, action, pacing, turn,
            system_prompt=system_prompt, model=target_model
        )

    def _call_openrouter(
        self, api_key: str, campaign: str, action: str, pacing: str, turn: int, system_prompt: str = "", model: str = ""
    ) -> str:
        target_model = model or os.environ.get("OPENROUTER_MODEL") or "anthropic/claude-3.5-sonnet"
        return self._call_openai_compatible(
            OPENROUTER_CHAT_URL,
            api_key,
            campaign,
            action,
            pacing,
            turn,
            system_prompt=system_prompt,
            model=target_model,
            extra_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Whimsy Local CYOA Engine"
            }
        )


def main():
    server = HTTPServer((DEFAULT_BIND_HOST, PORT), EngineRequestHandler)
    print(f"==================================================")
    print(f" Antigravity Local Engine Server Running on {DEFAULT_BIND_HOST}:{PORT}")
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
