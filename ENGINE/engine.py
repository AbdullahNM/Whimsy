#!/usr/bin/env python3
"""
Antigravity Local CYOA Engine Server
===================================
A standalone local orchestration server for running CYOA turns locally.
Connects with the PWA frontend (running on port 3000) and exposes:
- POST /generate: Processes player choices and generates GM responses with choice options and receipts
- GET /health: Status and active campaign diagnostics

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
sys.path.insert(0, ROOT_DIR)

from ENGINE.prompt_assembler import PromptAssembler
from ENGINE.state_parser import StateParser

PORT = int(os.environ.get("ANTIGRAVITY_PORT", 8000))

class EngineRequestHandler(BaseHTTPRequestHandler):
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
                "version": "1.0.0"
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
            turn_num = payload.get("currentTurn", 1)

            response_text = self.generate_turn(campaign, player_action, pacing, turn_num, payload)

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({"response": response_text}).encode("utf-8"))
        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown POST route"}).encode("utf-8"))

    def generate_turn(self, campaign: str, action: str, pacing: str, turn: int, payload: dict) -> str:
        # Check if environment or payload has a Gemini key to perform direct LLM generation
        api_key = payload.get("apiKey") or payload.get("api_key") or os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                return self._call_cloud_gemini(api_key, campaign, action, pacing, turn)
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

    def _call_cloud_gemini(self, api_key: str, campaign: str, action: str, pacing: str, turn: int) -> str:
        assembler = PromptAssembler(ROOT_DIR)
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
