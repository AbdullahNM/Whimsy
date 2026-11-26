#!/usr/bin/env python3
"""
Unit and integration tests for ENGINE/engine.py HTTP server.
Tests HTTP handlers, CORS headers, OPTIONS preflight, /health endpoint,
and /generate POST payload processing using in-memory streams.
"""

import os
import sys
import io
import json
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.engine import EngineRequestHandler


class MockSocket:
    """In-memory mock socket allowing BaseHTTPRequestHandler to run without OS TCP bindings."""
    def __init__(self, raw_input: bytes):
        self.rfile = io.BytesIO(raw_input)
        self.wfile = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs):
        if 'b' in mode:
            return self.rfile if 'r' in mode else self.wfile
        return io.TextIOWrapper(self.rfile if 'r' in mode else self.wfile)

    def sendall(self, data: bytes):
        self.wfile.write(data)


class DummyServer:
    server_address = ("127.0.0.1", 8000)


def execute_request(method: str, path: str, body: bytes = b"", headers: dict = None) -> tuple[int, dict, bytes]:
    """Simulates an HTTP request against EngineRequestHandler in-memory."""
    if headers is None:
        headers = {}
    if body and "Content-Length" not in headers:
        headers["Content-Length"] = str(len(body))

    header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    raw_http = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n{header_lines}\r\n".encode("utf-8") + body

    sock = MockSocket(raw_http)
    # Suppress server log messages during tests
    EngineRequestHandler.log_message = lambda self, format, *args: None
    EngineRequestHandler(sock, ("127.0.0.1", 54321), DummyServer())

    raw_response = sock.wfile.getvalue()
    parts = raw_response.split(b"\r\n\r\n", 1)
    header_block = parts[0].decode("utf-8", errors="replace")
    body_bytes = parts[1] if len(parts) > 1 else b""

    lines = header_block.split("\r\n")
    status_line = lines[0]
    status_code = int(status_line.split(" ")[1])

    resp_headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()

    return status_code, resp_headers, body_bytes


class TestEngineServer(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._cleanup_telemetry()

    def setUp(self):
        super().setUp()
        self._cleanup_telemetry()

    def tearDown(self):
        super().tearDown()
        self._cleanup_telemetry()

    @staticmethod
    def _cleanup_telemetry():
        telemetry_path = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign", "GAMEPLAY", "telemetry.jsonl")
        if os.path.exists(telemetry_path):
            try:
                os.remove(telemetry_path)
            except OSError:
                pass

    def test_health_endpoint(self):
        status, headers, body = execute_request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "*")
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "online")
        self.assertIn("Antigravity", data.get("engine", ""))

    def test_status_alias_endpoint(self):
        status, headers, body = execute_request("GET", "/status")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "online")

    def test_root_endpoint(self):
        status, headers, body = execute_request("GET", "/")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "online")

    def test_cors_options_preflight(self):
        status, headers, body = execute_request("OPTIONS", "/generate")
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("access-control-allow-origin"), "*")
        self.assertIn("post", headers.get("access-control-allow-methods", "").lower())
        self.assertIn("content-type", headers.get("access-control-allow-headers", "").lower())

    def test_generate_post_valid_payload(self):
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "pacing": "standard",
            "currentTurn": 245,
            "state": {
                "turn": 245,
                "progression": {
                    "energy": 100,
                    "energy_max": 100,
                    "stress": 10,
                    "stress_max": 100
                },
                "purse": {"display": "500 credits"}
            }
        }
        body = json.dumps(payload).encode("utf-8")
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=body,
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("access-control-allow-origin"), "*")
        data = json.loads(resp_body.decode("utf-8"))
        self.assertIn("response", data)
        text = data["response"]

        # Verify deterministic SYS receipts and fallback choices
        self.assertIn("[SYS: Turn 246", text)
        self.assertIn("Energy: 95 / 100", text)
        self.assertIn("Stress: 10 / 100", text)
        self.assertIn("Funds: 500 credits", text)
        self.assertIn("### [OPTIONS & TYPABLE REFERENCE]", text)
        self.assertIn("1. ", text)
        self.assertIn("2. ", text)
        self.assertIn("3. ", text)
        self.assertIn("4. ", text)

    def test_generate_post_invalid_json(self):
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=b"{not valid json",
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertIn("error", data)

    def test_not_found_get(self):
        status, headers, resp_body = execute_request("GET", "/unmapped_route")
        self.assertEqual(status, 404)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertIn("error", data)

    def test_not_found_post(self):
        status, headers, resp_body = execute_request(
            "POST",
            "/unmapped_post_route",
            body=b"{}",
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 404)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertIn("error", data)

    def test_generate_post_with_openrouter_key_mock(self):
        from unittest.mock import patch
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "currentTurn": 1,
            "apiKey": "sk-or-v1-dummy-openrouter-key",
            "model": "openrouter/anthropic/claude-3.5-sonnet"
        }
        with patch.object(EngineRequestHandler, "_call_openrouter", return_value="The shadow recedes as you step into the lower annex.\n\n### [OPTIONS & TYPABLE REFERENCE]\n1. Advance.\n2. Retreat.\n3. Hold.\n4. Scan.\n\n[SYS: Turn 2 | Checkpoints: 5/5]"):
            status, headers, resp_body = execute_request(
                "POST",
                "/generate",
                body=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            data = json.loads(resp_body.decode("utf-8"))
            self.assertIn("The shadow recedes", data["response"])

    def test_generate_post_with_fastrouter_mock(self):
        from unittest.mock import patch
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "currentTurn": 1,
            "provider": "fastrouter",
            "apiKey": "fr-dummy-fastrouter-key",
            "model": "fastrouter/openai/gpt-4o-mini"
        }
        with patch.object(EngineRequestHandler, "_call_fastrouter", return_value="Cold drizzle dampens your collar by the hatch.\n\n### [OPTIONS & TYPABLE REFERENCE]\n1. Advance.\n2. Retreat.\n3. Hold.\n4. Scan.\n\n[SYS: Turn 2 | Checkpoints: 5/5]") as mock_fr:
            status, headers, resp_body = execute_request(
                "POST",
                "/generate",
                body=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            data = json.loads(resp_body.decode("utf-8"))
            self.assertIn("Cold drizzle dampens", data["response"])
            self.assertEqual(mock_fr.call_count, 1)

    def test_campaigns_and_campaign_bundle_endpoints(self):
        status, _, body = execute_request("GET", "/api/campaigns")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("template_campaign", data.get("campaigns", []))
        self.assertIn("template_campaign", data.get("configs", {}))

        status2, _, body2 = execute_request("GET", "/api/campaign?campaign=template_campaign")
        self.assertEqual(status2, 200)
        bundle = json.loads(body2.decode("utf-8"))
        self.assertEqual(bundle.get("campaign_id"), "template_campaign")
        self.assertIn("status_json", bundle)
        self.assertIn("active_turns", bundle)

    def test_test_connection_offline_mode(self):
        with patch.dict(os.environ, {
            "WHIMSY_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "FASTROUTER_API_KEY": "",
            "GEMINI_API_KEY": "",
        }):
            status, _, body = execute_request(
                "POST",
                "/api/test_connection",
                body=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            data = json.loads(body.decode("utf-8"))
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("mode"), "offline_deterministic")

    def test_caller_endpoint_cannot_use_env_secret_and_mocked_http_binds_trusted_hosts(self):
        from ENGINE.engine import resolve_llm_config, OPENROUTER_CHAT_URL, FASTROUTER_CHAT_URL

        captured = []

        class FakeResponse:
            def __init__(self, payload_obj):
                self._data = json.dumps(payload_obj).encode("utf-8")

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        def fake_urlopen(req, timeout=45):
            captured.append((req.full_url, dict(req.header_items())))
            return FakeResponse({
                "choices": [{
                    "message": {
                        "content": (
                            "Rain beads along the shuttered sill.\n\n"
                            "### [OPTIONS & TYPABLE REFERENCE]\n"
                            "1. Check the ledger.\n2. Bar the door.\n3. Wait.\n\n"
                            "[SYS: Turn 2 | Checkpoints: 5/5]"
                        )
                    }
                }]
            })

        env_vars = {
            "WHIMSY_API_KEY": "",
            "WHIMSY_PROVIDER": "",
            "WHIMSY_API_BASE": "",
            "WHIMSY_MODEL": "",
            "OPENROUTER_API_KEY": "sk-or-server-secret",
            "FASTROUTER_API_KEY": "fr-server-secret",
            "GEMINI_API_KEY": "",
        }
        with patch.dict(os.environ, env_vars), patch("urllib.request.urlopen", side_effect=fake_urlopen) as mock_open:
            # 1) Caller-selected apiBaseUrl WITHOUT caller apiKey MUST fail closed (400 on test_connection, no outbound HTTP)
            status_err, _, body_err = execute_request(
                "POST",
                "/api/test_connection",
                body=json.dumps({
                    "provider": "custom",
                    "apiBaseUrl": "https://evil.example/collect",
                    "model": "attacker/model"
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status_err, 400)
            self.assertFalse(json.loads(body_err.decode("utf-8")).get("ok"))
            self.assertEqual(mock_open.call_count, 0)

            # /generate with caller-selected apiBaseUrl and NO caller apiKey falls back offline without calling urlopen
            status_gen_err, _, _ = execute_request(
                "POST",
                "/generate",
                body=json.dumps({
                    "action": "1",
                    "campaign": "template_campaign",
                    "currentTurn": 1,
                    "apiBaseUrl": "https://evil.example/collect",
                    "commit": False,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status_gen_err, 200)
            self.assertEqual(mock_open.call_count, 0)

            # 2) Mismatched caller provider without env key for that provider must NOT borrow another provider's env key
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-only-secret", "FASTROUTER_API_KEY": ""}):
                cfg_mismatch = resolve_llm_config({"provider": "fastrouter"})
                self.assertEqual(cfg_mismatch["api_key"], "")

            # 3) Server-side OpenRouter key pairs strictly with trusted OPENROUTER_CHAT_URL
            captured.clear()
            status_or, _, body_or = execute_request(
                "POST",
                "/api/test_connection",
                body=json.dumps({"provider": "openrouter"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status_or, 200)
            self.assertTrue(json.loads(body_or.decode("utf-8")).get("ok"))
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][0], OPENROUTER_CHAT_URL)
            self.assertEqual(captured[0][1].get("Authorization"), "Bearer sk-or-server-secret")

            # 4) Server-side FastRouter key pairs strictly with trusted FASTROUTER_CHAT_URL
            captured.clear()
            status_fr, _, body_fr = execute_request(
                "POST",
                "/api/test_connection",
                body=json.dumps({"provider": "fastrouter"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status_fr, 200)
            self.assertTrue(json.loads(body_fr.decode("utf-8")).get("ok"))
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][0], FASTROUTER_CHAT_URL)
            self.assertEqual(captured[0][1].get("Authorization"), "Bearer fr-server-secret")

            # 5) Caller-supplied apiKey + apiBaseUrl uses ONLY caller key (never env key)
            captured.clear()
            status_custom, _, _ = execute_request(
                "POST",
                "/generate",
                body=json.dumps({
                    "action": "1",
                    "campaign": "template_campaign",
                    "currentTurn": 1,
                    "provider": "custom",
                    "apiBaseUrl": "https://custom.example/v1/chat/completions",
                    "apiKey": "caller-own-key",
                    "model": "custom/test",
                    "commit": False,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status_custom, 200)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0][0], "https://custom.example/v1/chat/completions")
            self.assertEqual(captured[0][1].get("Authorization"), "Bearer caller-own-key")

    def test_private_campaign_bundles_restricted_and_commit_false_skips_idempotency(self):
        import tempfile
        from ENGINE.campaign_builder import scaffold_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            scaffold_campaign(tmpdir, {"campaign_id": "template_campaign", "title": "Template"})
            scaffold_campaign(tmpdir, {"campaign_id": "private_diary", "title": "Secret Lore"})

            with patch("ENGINE.engine.ROOT_DIR", tmpdir), patch.dict(os.environ, {"WHIMSY_ALLOW_PRIVATE_CAMPAIGN_API": ""}):
                status_list, _, body_list = execute_request("GET", "/api/campaigns")
                self.assertEqual(status_list, 200)
                c_list = json.loads(body_list.decode("utf-8")).get("campaigns", [])
                self.assertIn("template_campaign", c_list)
                self.assertNotIn("private_diary", c_list)

                status_priv, _, _ = execute_request("GET", "/api/campaign?campaign=private_diary")
                self.assertEqual(status_priv, 403)

                # commit:false must not return cached retry=True even after commit:true recorded same turn+action
                priv_dir = os.path.join(tmpdir, "CAMPAIGNS", "private_diary")
                status_c1, _, body_c1 = execute_request(
                    "POST",
                    "/generate",
                    body=json.dumps({
                        "action": "1",
                        "campaign": "private_diary",
                        "campaign_dir": priv_dir,
                        "root_dir": tmpdir,
                        "currentTurn": 1,
                        "commit": True,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                self.assertEqual(status_c1, 200, body_c1.decode("utf-8"))
                self.assertTrue(json.loads(body_c1.decode("utf-8")).get("committed"))

                status_preview, _, body_preview = execute_request(
                    "POST",
                    "/generate",
                    body=json.dumps({
                        "action": "1",
                        "campaign": "private_diary",
                        "campaign_dir": priv_dir,
                        "root_dir": tmpdir,
                        "currentTurn": 1,
                        "commit": False,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                self.assertEqual(status_preview, 200, body_preview.decode("utf-8"))
                preview_data = json.loads(body_preview.decode("utf-8"))
                self.assertFalse(preview_data.get("committed"))
                self.assertNotIn("retry", preview_data)

                # Second commit:true call DOES replay committed record idempotently
                status_replay, _, body_replay = execute_request(
                    "POST",
                    "/generate",
                    body=json.dumps({
                        "action": "1",
                        "campaign": "private_diary",
                        "campaign_dir": priv_dir,
                        "root_dir": tmpdir,
                        "currentTurn": 1,
                        "commit": True,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                self.assertEqual(status_replay, 200, body_replay.decode("utf-8"))
                replay_data = json.loads(body_replay.decode("utf-8"))
                self.assertTrue(replay_data.get("retry"))

    def test_nontemplate_turn5_stat_change_and_distinctive_next_choice(self):
        import tempfile
        from ENGINE.campaign_builder import scaffold_campaign

        with tempfile.TemporaryDirectory() as tmpdir:
            cid = "harbor_chronicle"
            scaffold_campaign(tmpdir, {"campaign_id": cid, "title": "Harbor Chronicle"})
            cdir = os.path.join(tmpdir, "CAMPAIGNS", cid)
            cfg_path = os.path.join(cdir, "campaign_config.json")
            with open(cfg_path, "r", encoding="utf-8") as cf:
                cfg = json.load(cf)
            cfg["rules"] = [
                {
                    "match": {"choice_index": 1},
                    "progression_delta": {"energy": -10},
                    "next_choices": [
                        {"index": 1, "text": "Unseal the brine-stained harbor ledger"},
                        {"index": 2, "text": "Signal the customs skiff from the jetty"},
                    ],
                }
            ]
            with open(cfg_path, "w", encoding="utf-8") as cf:
                json.dump(cfg, cf, indent=2)

            pre_turn5_state = {
                "schema_version": 2,
                "campaign_id": cid,
                "turn": 5,
                "timeline": "Act II",
                "progression": {
                    "energy": 80,
                    "energy_max": 100,
                    "stress": 15,
                    "stress_max": 100,
                    "checkpoint_tokens": 5,
                    "checkpoint_max": 5,
                },
                "purse": {"credits": 500, "display": "500 credits"},
                "clocks": [],
                "scene_anchor": {"location": "Bellwether Pier", "context": "Rain lashes the timber.", "time": "Day 2, 05:00"},
                "pacing_state": {
                    "elapsed_time_minutes": 40,
                    "narrative_intensity": 2,
                    "scheduled_events": [],
                    "timeline_stamp": "Day 2, 05:00",
                    "zoom_level": "detailed_scene",
                },
                "public_state": {"flags": {}, "conditions": [], "open_threads": []},
            }

            with patch("ENGINE.engine.ROOT_DIR", tmpdir):
                status, _, body = execute_request(
                    "POST",
                    "/generate",
                    body=json.dumps({
                        "action": "1",
                        "campaign": cid,
                        "campaign_dir": cdir,
                        "root_dir": tmpdir,
                        "currentTurn": 5,
                        "state": pre_turn5_state,
                        "commit": True,
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )

            self.assertEqual(status, 200, body.decode("utf-8"))
            data = json.loads(body.decode("utf-8"))
            outcome = data["outcome"]
            self.assertEqual(outcome["next_state"]["turn"], 6)
            self.assertEqual(outcome["next_state"]["progression"]["energy"], 70)
            self.assertEqual(outcome["offered_choices"][0]["text"], "Unseal the brine-stained harbor ledger")
            self.assertIn("Unseal the brine-stained harbor ledger", data["response"])
            self.assertIn("Energy: 70 / 100", data["response"])
            self.assertIn("Turn 6", data["response"])

            # Verify committed disk status.json and status.md advance to Turn 6 (not stuck at Turn 5)
            with open(os.path.join(cdir, "GAMEPLAY", "status.json"), "r", encoding="utf-8") as sf:
                disk_status = json.load(sf)
            with open(os.path.join(cdir, "GAMEPLAY", "status.md"), "r", encoding="utf-8") as smf:
                disk_status_md = smf.read()
            self.assertEqual(disk_status["turn"], 6)
            self.assertRegex(disk_status_md, r"(?i)turn\*{0,2}:\*{0,2}\s*6\b")

    def test_origin_auth_and_filesystem_path_containment(self):
        import tempfile

        # 1) Untrusted Origin rejected with 403 and no Access-Control-Allow-Origin header
        for method, path, body in [
            ("OPTIONS", "/api/campaigns", b""),
            ("GET", "/api/campaigns", b""),
            ("POST", "/generate", json.dumps({"action": "1", "campaign": "template_campaign"}).encode("utf-8")),
        ]:
            status, headers, _ = execute_request(
                method,
                path,
                body=body,
                headers={"Origin": "https://evil.example", "Content-Type": "application/json"},
            )
            self.assertEqual(status, 403)
            self.assertIsNone(headers.get("access-control-allow-origin"))

        # Allowed loopback Origin is echoed with Vary: Origin
        status_ok, headers_ok, _ = execute_request(
            "GET",
            "/api/campaigns",
            headers={"Origin": "http://localhost:3000"},
        )
        self.assertEqual(status_ok, 200)
        self.assertEqual(headers_ok.get("access-control-allow-origin"), "http://localhost:3000")

        # 2) Optional WHIMSY_AUTH_TOKEN protects campaign/engine routes while keeping /health open
        with patch.dict(os.environ, {"WHIMSY_AUTH_TOKEN": "top-secret-token"}):
            st_health, _, _ = execute_request("GET", "/health")
            self.assertEqual(st_health, 200)

            st_unauth, _, _ = execute_request("GET", "/api/campaigns")
            self.assertEqual(st_unauth, 401)

            st_auth, _, _ = execute_request(
                "GET",
                "/api/campaigns",
                headers={"Authorization": "Bearer top-secret-token"},
            )
            self.assertEqual(st_auth, 200)

        # WHIMSY_REQUIRE_AUTH=1 fails closed when no WHIMSY_AUTH_TOKEN is configured
        with patch.dict(os.environ, {"WHIMSY_REQUIRE_AUTH": "1", "WHIMSY_AUTH_TOKEN": ""}):
            st_req_auth, _, _ = execute_request("GET", "/api/campaigns")
            self.assertEqual(st_req_auth, 401)

        # 3) Arbitrary filesystem paths outside configured roots are rejected
        with tempfile.TemporaryDirectory() as outside_dir:
            st_bad_root, _, body_bad_root = execute_request(
                "POST",
                "/generate",
                body=json.dumps({
                    "action": "1",
                    "campaign": "template_campaign",
                    "root_dir": outside_dir,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(st_bad_root, 400)
            self.assertEqual(json.loads(body_bad_root.decode("utf-8")).get("error"), "INVALID_PATH")

            st_bad_cdir, _, body_bad_cdir = execute_request(
                "POST",
                "/generate",
                body=json.dumps({
                    "action": "1",
                    "campaign": "outside",
                    "campaign_dir": os.path.join(outside_dir, "CAMPAIGNS", "outside"),
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(st_bad_cdir, 400)
            self.assertEqual(json.loads(body_bad_cdir.decode("utf-8")).get("error"), "INVALID_PATH")

        # 4) Traversal and private campaign HTTP routes blocked
        st_trav, _, _ = execute_request("GET", "/api/channel?campaign=../../etc")
        self.assertEqual(st_trav, 400)
        with patch.dict(os.environ, {"WHIMSY_ALLOW_PRIVATE_CAMPAIGN_API": ""}):
            st_priv_tel, _, _ = execute_request("GET", "/api/telemetry?campaign=private_camp")
            self.assertEqual(st_priv_tel, 403)
            st_priv_chan, _, _ = execute_request("GET", "/api/channel?campaign=private_camp")
            self.assertEqual(st_priv_chan, 403)

    def test_generate_post_deterministic_remediation_strips_formulaic_closings(self):
        """Verify that formulaic turn closings are deterministically stripped and validated."""
        from unittest.mock import patch
        raw_output_with_closing = (
            "You step through the archway into the grand vault. "
            "Dust settles gently around the pedestals. What will you do?\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Examine relics.\n"
            "2. Turn back.\n\n"
            "[SYS: Turn 2 | Checkpoints: 5/5]"
        )
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "currentTurn": 1,
            "strict_style_enforcement": True,
            "max_style_retries": 2
        }
        with patch.object(EngineRequestHandler, "_call_model", return_value=raw_output_with_closing) as mock_model:
            status, headers, resp_body = execute_request(
                "POST",
                "/generate",
                body=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            data = json.loads(resp_body.decode("utf-8"))
            self.assertTrue(data.get("style_valid"))
            self.assertEqual(data.get("style_score"), 1.0)
            self.assertNotIn("What will you do?", data.get("response", ""))
            self.assertIn("You step through the archway into the grand vault.", data.get("response", ""))
            # Deterministic remediation should succeed on the first attempt without re-calling the model
            self.assertEqual(mock_model.call_count, 1)

    def test_generate_post_strict_style_failure_triggers_reprompt_loop(self):
        """Verify that style violations that cannot be deterministically stripped trigger re-prompt attempts."""
        from unittest.mock import patch
        # 1st call fails due to prohibited STEM jargon (lambda).
        # 2nd call fixes it and returns valid prose.
        first_draft_violating = (
            "The lambda coefficient drifted beyond acceptable limits.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Stabilize the grid.\n"
            "2. Abort.\n\n"
            "[SYS: Turn 2 | Checkpoints: 5/5]"
        )
        second_draft_clean = (
            "The energy readings stabilized as you adjusted the primary dial.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Stabilize the grid.\n"
            "2. Abort.\n\n"
            "[SYS: Turn 2 | Checkpoints: 5/5]"
        )
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "currentTurn": 1,
            "strict_style_enforcement": True,
            "max_style_retries": 2
        }
        with patch.object(EngineRequestHandler, "_call_model", side_effect=[first_draft_violating, second_draft_clean]) as mock_model:
            status, headers, resp_body = execute_request(
                "POST",
                "/generate",
                body=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            data = json.loads(resp_body.decode("utf-8"))
            self.assertTrue(data.get("style_valid"))
            self.assertEqual(data.get("style_score"), 1.0)
            self.assertIn("The energy readings stabilized", data.get("response", ""))
            self.assertEqual(mock_model.call_count, 2)

            # Check that the second call received the correction prompt
            second_call_kwargs = mock_model.call_args_list[1][1]
            remediated_prompt = second_call_kwargs.get("system_prompt", "")
            self.assertIn("[STYLE CONTRACT CORRECTION REQUIRED]", remediated_prompt)
            self.assertIn("lambda", remediated_prompt)

    def test_generate_post_persistent_style_failure_aborts_commit_and_returns_422(self):
        """Verify that persistent style violations after retries prevent state commit, log telemetry, and return 422."""
        import tempfile
        import shutil
        from unittest.mock import patch

        temp_workspace = tempfile.mkdtemp()
        try:
            # Create a mock campaign directory inside temp_workspace
            camp_dir = os.path.join(temp_workspace, "CAMPAIGNS", "test_style_camp")
            gameplay_dir = os.path.join(camp_dir, "GAMEPLAY")
            os.makedirs(gameplay_dir, exist_ok=True)
            status_json_path = os.path.join(gameplay_dir, "status.json")
            initial_status = {
                "turn": 1,
                "character": {"name": "Hero"},
                "progression": {"energy": 100, "energy_max": 100, "stress": 0, "stress_max": 100},
                "pacing_state": {"zoom_level": "detailed_scene", "narrative_intensity": 1, "elapsed_time_minutes": 0}
            }
            with open(status_json_path, "w", encoding="utf-8") as f:
                json.dump(initial_status, f)

            camp_cfg_path = os.path.join(camp_dir, "campaign_config.json")
            with open(camp_cfg_path, "w", encoding="utf-8") as f:
                json.dump({
                    "id": "test_style_camp",
                    "operational_mode": "classic_cyoa",
                    "style_contract": {
                        "strict_style_enforcement": True,
                        "max_style_retries": 2,
                        "ban_stem_calculus_jargon": True
                    }
                }, f)

            violating_prose = (
                "The lambda coefficient surged across the terminal.\n\n"
                "### [OPTIONS & TYPABLE REFERENCE]\n"
                "1. Override.\n"
                "2. Cut power.\n\n"
                "[SYS: Turn 2 | Checkpoints: 5/5]"
            )

            payload = {
                "action": "1",
                "campaign": "test_style_camp",
                "campaign_dir": camp_dir,
                "currentTurn": 1,
                "root_dir": temp_workspace,
                "commit": True,
                "strict_style_enforcement": True,
                "max_style_retries": 2
            }

            with patch("ENGINE.engine.ROOT_DIR", temp_workspace), patch.object(EngineRequestHandler, "_call_model", return_value=violating_prose) as mock_model:
                status, headers, resp_body = execute_request(
                    "POST",
                    "/generate",
                    body=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                self.assertEqual(status, 422)
                data = json.loads(resp_body.decode("utf-8"))
                self.assertIn("error", data)
                self.assertEqual(data["error"], "Style contract validation failed after retries")
                self.assertIn("violations", data)
                self.assertTrue(len(data["violations"]) > 0)
                self.assertIn("lambda", str(data["violations"]))
                self.assertIn("style_score", data)
                self.assertIn("prose", data)

                # Initial generation + 2 retries = 3 calls
                self.assertEqual(mock_model.call_count, 3)

                # Verify state was NOT committed:
                # 1. status.json should remain at turn 1
                with open(status_json_path, "r", encoding="utf-8") as f:
                    persisted_status = json.load(f)
                self.assertEqual(persisted_status["turn"], 1)

                # 2. turn_0002.md or turn_0001.md should NOT exist
                turn_files = [f for f in os.listdir(gameplay_dir) if f.startswith("turn_")]
                self.assertEqual(len(turn_files), 0)

                # 3. Telemetry log should record style_commit_aborted=True
                from ENGINE.telemetry import read_campaign_telemetry
                tel_records = read_campaign_telemetry(temp_workspace, "test_style_camp")
                self.assertTrue(len(tel_records) > 0)
                last_tel = tel_records[-1]
                self.assertTrue(last_tel.get("style_commit_aborted"))
        finally:
            shutil.rmtree(temp_workspace, ignore_errors=True)

    def test_generate_post_non_strict_style_failure_commits_and_returns_200(self):
        """Verify that style failures with strict_style_enforcement=False commit state and return 200 with warning."""
        from unittest.mock import patch
        violating_prose = (
            "The lambda coefficient drifted.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Advance.\n\n"
            "[SYS: Turn 2 | Checkpoints: 5/5]"
        )
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "currentTurn": 1,
            "strict_style_enforcement": False
        }
        with patch.object(EngineRequestHandler, "_call_model", return_value=violating_prose) as mock_model:
            status, headers, resp_body = execute_request(
                "POST",
                "/generate",
                body=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            data = json.loads(resp_body.decode("utf-8"))
            self.assertFalse(data.get("style_valid"))
            # When strict enforcement is False, no re-prompts are made
            self.assertEqual(mock_model.call_count, 1)


    def test_channel_api_endpoints(self):
        # Backup existing channel file
        ideas_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign", "IDEAS")
        md_file = os.path.join(ideas_dir, "agent_channel.md")
        json_file = os.path.join(ideas_dir, "agent_channel.json")
        orig_md = None
        if os.path.exists(md_file):
            with open(md_file, "r", encoding="utf-8") as f:
                orig_md = f.read()

        try:
            # GET /api/channel
            status, headers, resp_body = execute_request("GET", "/api/channel?campaign=template_campaign")
            self.assertEqual(status, 200)
            data = json.loads(resp_body.decode("utf-8"))
            self.assertEqual(data["channel_mode"], "file")
            self.assertTrue(data["file_fallback"])
            self.assertIn("messages", data)

            # POST /api/channel
            post_payload = {
                "campaign": "template_campaign",
                "sender": "SHADOW",
                "content": "API test directive",
                "turn": 1
            }
            status, headers, resp_body = execute_request(
                "POST",
                "/api/channel",
                body=json.dumps(post_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(status, 200)
            post_data = json.loads(resp_body.decode("utf-8"))
            self.assertEqual(post_data["status"], "success")
            self.assertTrue(post_data["file_fallback"])
        finally:
            if orig_md is not None:
                with open(md_file, "w", encoding="utf-8") as f:
                    f.write(orig_md)
            if os.path.exists(json_file):
                try:
                    os.remove(json_file)
                except OSError:
                    pass

    def test_telemetry_get_endpoint(self):
        status, headers, resp_body = execute_request("GET", "/telemetry?campaign=template_campaign")
        self.assertEqual(status, 200)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertEqual(data["campaign"], "template_campaign")
        self.assertIn("summary", data)
        self.assertIn("records", data)

    def test_calibration_get_endpoint(self):
        status, headers, resp_body = execute_request("GET", "/calibration?campaign=template_campaign")
        self.assertEqual(status, 200)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertEqual(data["campaign"], "template_campaign")
        self.assertIn("calibration", data)
        self.assertIn("health_status", data["calibration"])

    def test_evaluate_turn_post_endpoint(self):
        eval_payload = {
            "campaign": "template_campaign",
            "turn_num": 1,
            "action": "Inspect the terminal",
            "response": "You inspect the terminal carefully. 1. Press button. 2. Leave."
        }
        status, headers, resp_body = execute_request(
            "POST",
            "/evaluate/turn",
            body=json.dumps(eval_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 200)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertEqual(data["campaign_id"], "template_campaign")
        self.assertIn("overall_score", data)
        self.assertIn("dimension_scores", data)
        self.assertIn("evidence", data)
        self.assertIn("critique", data)
        self.assertIn("remedy", data)
        self.assertIn("bias_adjustments", data)


if __name__ == "__main__":
    unittest.main()
