"""
ARMA Turnkey Harness Runner (layer/runner.py)
Enables zero-config execution for coding agents (Claude Code, Aider, OpenCode).
Automatically:
1. Spins up the Universal Interceptor Proxy in the background.
2. Injects proxy environment variables (ANTHROPIC_BASE_URL, OPENAI_BASE_URL).
3. Attaches EvidenceDB session telemetry and lifecycle monitoring.
4. Cleans up background proxies on exit and emits an execution summary card.
"""

import os
import sys
import time
import socket
import urllib.request
import subprocess
import threading
from typing import List, Optional, Dict, Any

from layer.evidence_db import EvidenceDB
from layer.interceptor_proxy import run_proxy, DEFAULT_PORT


def is_port_in_use(port: int) -> bool:
    """Check if a port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_proxy_health(port: int, timeout_sec: float = 3.0) -> bool:
    """Wait until the interceptor proxy answers the health check endpoint."""
    url = f"http://127.0.0.1:{port}/health"
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


class HarnessRunner:
    """
    Manages the lifecycle of an intercepted agent harness execution.
    """

    def __init__(self, port: int = DEFAULT_PORT, db: Optional[EvidenceDB] = None):
        self.port = port
        self.db = db or EvidenceDB()
        self.proxy_thread: Optional[threading.Thread] = None

    def ensure_proxy_running(self):
        """Starts background interceptor proxy thread if not already running."""
        if is_port_in_use(self.port):
            # Already active
            return

        self.proxy_thread = threading.Thread(
            target=run_proxy,
            kwargs={"port": self.port},
            daemon=True
        )
        self.proxy_thread.start()

        healthy = wait_for_proxy_health(self.port)
        if not healthy:
            print(f"[ARMA Runner Warning] Proxy did not respond on port {self.port} within timeout. Proceeding...")

    def run(self, command: List[str], repo_path: Optional[str] = None) -> int:
        """
        Executes the agent command with injected ARMA proxy bindings.
        """
        cwd = repo_path or os.getcwd()
        harness_name = os.path.basename(command[0])
        task_summary = " ".join(command)

        # 1. Start Evidence session
        session_id = self.db.start_session(
            repo_path=cwd,
            harness=harness_name,
            task_text=task_summary
        )

        # 2. Ensure Interceptor Proxy is active
        self.ensure_proxy_running()

        # 3. Configure environment variables
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{self.port}/v1"
        env["OPENAI_BASE_URL"] = f"http://127.0.0.1:{self.port}/v1"
        env["ARMA_INTERCEPT_ACTIVE"] = "1"
        env["ARMA_SESSION_ID"] = session_id
        env["ARMA_PROXY_PORT"] = str(self.port)

        print("=" * 70)
        print("ARMA HARNESS RUNNER")
        print("=" * 70)
        print(f"Harness Command  : {task_summary}")
        print(f"Working Directory: {cwd}")
        print(f"Session ID       : {session_id}")
        print(f"Intercept Proxy  : http://127.0.0.1:{self.port}/v1")
        print("-" * 70)

        t0 = time.time()
        return_code = 1

        try:
            # Spawn the agent harness
            proc = subprocess.Popen(command, env=env, cwd=cwd)
            return_code = proc.wait()
        except KeyboardInterrupt:
            print("\n[ARMA Runner] Interrupted by user. Terminating harness...")
            if 'proc' in locals():
                proc.terminate()
            return_code = 130
        except Exception as e:
            print(f"[ARMA Runner Error] Failed to execute harness: {e}")
            return_code = 1
        finally:
            elapsed = round(time.time() - t0, 2)
            status = "resolved" if return_code == 0 else "failed"
            self.db.end_session(session_id=session_id, final_status=status)
            self._print_session_summary(session_id, harness_name, elapsed, return_code)

        return return_code

    def _print_session_summary(self, session_id: str, harness: str, elapsed: float, return_code: int):
        """Prints post-execution diagnostic card."""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,))
            events_count = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*), 
                       SUM(CASE WHEN action_taken = 'block' THEN 1 ELSE 0 END),
                       SUM(CASE WHEN action_taken = 'warn' THEN 1 ELSE 0 END)
                FROM decisions d
                JOIN events e ON d.event_id = e.id
                WHERE e.session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            total_decisions = row[0] or 0
            blocked_decisions = row[1] or 0
            warned_decisions = row[2] or 0

        print("\n" + "=" * 70)
        print("ARMA SESSION EXECUTION SUMMARY")
        print("=" * 70)
        print(f"Session ID           : {session_id}")
        print(f"Harness              : {harness}")
        print(f"Elapsed Time         : {elapsed}s")
        print(f"Exit Code            : {return_code}")
        print(f"Events Intercepted   : {events_count}")
        print(f"Decisions Evaluated  : {total_decisions}")
        print(f"Actions Blocked/Warn : {blocked_decisions} blocked, {warned_decisions} warned")
        print(f"Evidence DB Record   : {self.db.db_path}")
        print("=" * 70)
