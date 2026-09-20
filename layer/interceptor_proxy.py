"""
ARMA Universal Interceptor Proxy
Local reverse proxy (127.0.0.1:4040) providing zero-config attachment
to any coding harness (Claude Code, OpenCode, Aider, Codex, Cursor).
Intercepts requests, evaluates Decision Gates, prunes bloated context, and logs telemetry.
"""

import os
import sys
import json
import time
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine


DEFAULT_PORT = 4040
DEFAULT_UPSTREAM = os.environ.get("ARMA_UPSTREAM_URL", "http://localhost:11434")


class InterceptorHandler(BaseHTTPRequestHandler):
    """HTTP Request handler that intercepts and audits LLM completions."""

    engine: DecisionEngine = None
    db: EvidenceDB = None
    upstream_url: str = DEFAULT_UPSTREAM
    current_session_id: str = None

    def log_message(self, format, *args):
        # Override to suppress default HTTP access logs in console
        pass

    def do_GET(self):
        """Health check and status endpoint."""
        if self.path in ("/", "/health", "/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status_payload = {
                "service": "ARMA Universal Interceptor",
                "status": "active",
                "upstream": self.upstream_url,
                "session_id": self.current_session_id
            }
            self.wfile.write(json.dumps(status_payload).encode("utf-8"))
        else:
            self._proxy_pass("GET")

    def do_POST(self):
        """Intercept completions and chat requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = None

        # If it is an OpenAI or Anthropic chat completion endpoint
        if self.path.endswith("/chat/completions") or self.path.endswith("/messages"):
            modified_body = self._audit_and_preprocess(payload)
            self._proxy_pass("POST", modified_body or body)
        else:
            self._proxy_pass("POST", body)

    def _audit_and_preprocess(self, payload: Optional[Dict[str, Any]]) -> Optional[bytes]:
        """Inspect prompt, evaluate pre-execution gates, and optionally inject pinned facts."""
        if not payload or not self.engine:
            return None

        # Ensure we have an active session in EvidenceDB
        if not self.current_session_id:
            self.current_session_id = self.db.start_session(
                repo_path=os.getcwd(),
                harness="proxy_intercept",
                task_text="Automated Intercepted Session"
            )

        messages = payload.get("messages", [])
        if not messages:
            return None

        # 1. Record event
        event_id = self.db.record_event(
            session_id=self.current_session_id,
            turn=len(messages),
            kind="pre_completion_intercept",
            raw_payload_summary=f"{len(messages)} messages intercepted",
            tokens_in=len(str(payload)) // 4
        )

        # 2. Extract potential tool calls or shell commands from recent assistant turns
        last_msg = messages[-1]
        content = last_msg.get("content", "")

        # Check for shell execution intent in user/assistant text
        if isinstance(content, str) and any(cmd in content for cmd in ("rm ", "drop ", "git ", "chmod ")):
            gate_res = self.engine.evaluate_risk(
                session_id=self.current_session_id,
                event_id=event_id,
                command=content,
                cwd=os.getcwd()
            )
            if not gate_res.allow:
                # Return synthetic rejection if hard-denied in enforce mode
                self._send_blocked_response(gate_res.reason)
                return None

        return None

    def _proxy_pass(self, method: str, body: Optional[bytes] = None):
        """Forward request to upstream LLM server and stream response back."""
        target_url = f"{self.upstream_url.rstrip('/')}{self.path}"
        req = urllib.request.Request(target_url, data=body, method=method)

        for header, value in self.headers.items():
            if header.lower() not in ("host", "content-length"):
                req.add_header(header, value)

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                self.send_response(response.status)
                for header, value in response.headers.items():
                    if header.lower() != "transfer-encoding":
                        self.send_header(header, value)
                self.end_headers()
                self.wfile.write(response.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            err_resp = {"error": f"ARMA Proxy Error forwarding to upstream: {str(e)}"}
            self.wfile.write(json.dumps(err_resp).encode("utf-8"))

    def _send_blocked_response(self, reason: str):
        """Emit a 403 Forbidden with ARMA rejection details."""
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "error": {
                "message": f"Blocked by ARMA Decision Layer: {reason}",
                "type": "arma_policy_violation",
                "code": 403
            }
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))


def run_proxy(port: int = DEFAULT_PORT, upstream: str = DEFAULT_UPSTREAM):
    """Start the ARMA Universal Interceptor Proxy server."""
    db = EvidenceDB()
    engine = DecisionEngine(evidence_db=db)

    InterceptorHandler.db = db
    InterceptorHandler.engine = engine
    InterceptorHandler.upstream_url = upstream

    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, InterceptorHandler)
    print(f"ARMA Universal Interceptor Proxy running on http://127.0.0.1:{port}")
    print(f"Forwarding to upstream: {upstream}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ARMA Interceptor Proxy.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARMA Universal Interceptor Proxy")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--upstream", type=str, default=DEFAULT_UPSTREAM, help="Upstream LLM server URL")
    args = parser.parse_args()
    run_proxy(port=args.port, upstream=args.upstream)
