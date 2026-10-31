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
            "action": "Accept the contract and head to the staging bay",
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
        self.assertIn("Energy: 100 / 100", text)
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


if __name__ == "__main__":
    unittest.main()
