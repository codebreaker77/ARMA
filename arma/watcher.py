"""ARMA Live Workspace Watcher.

Monitors repository changes in real time as an AI coding agent or developer works.
Instantly intercepts test tampering, deleted assertions, and hazardous edits before commit.
"""

import os
import sys
import time
import subprocess
from typing import Optional, Callable
from arma.guard import AgentGuard, GuardVerdict


class RepoWatcher:
    """Live monitor watching repository uncommitted git diffs."""

    def __init__(
        self,
        repo_path: Optional[str] = None,
        strict: bool = False,
        on_verdict: Optional[Callable[[GuardVerdict], None]] = None
    ):
        self.repo_path = os.path.abspath(repo_path or os.getcwd())
        self.guard = AgentGuard(repo_path=self.repo_path, strict=strict)
        self.on_verdict = on_verdict
        self._last_diff_hash: Optional[int] = None

    def get_current_diff(self) -> str:
        """Fetch current uncommitted git diff from repository."""
        try:
            p = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5
            )
            return p.stdout or ""
        except Exception:
            return ""

    def check_once(self) -> Optional[GuardVerdict]:
        """Perform a single check against the current working tree."""
        diff = self.get_current_diff()
        current_hash = hash(diff)
        if current_hash == self._last_diff_hash:
            return None  # No changes since last check

        self._last_diff_hash = current_hash
        verdict = self.guard.audit_diff(diff)

        if self.on_verdict:
            self.on_verdict(verdict)

        return verdict

    def run(self, interval_seconds: float = 1.0, once: bool = False):
        """Run continuous monitoring loop."""
        print("=" * 65)
        print("ARMA Workspace Watcher: Active Supervisor Running")
        print("=" * 65)
        print(f"Monitoring Repository : {self.repo_path}")
        print(f"Polling Interval      : {interval_seconds}s")
        print("Watching for test-tampering, deleted assertions, and reward hacking...")
        print("Press Ctrl+C to stop.\n")

        if once:
            verdict = self.check_once()
            self._display_verdict(verdict)
            return

        try:
            while True:
                verdict = self.check_once()
                if verdict is not None:
                    self._display_verdict(verdict)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nARMA Watcher stopped.")

    def _display_verdict(self, verdict: Optional[GuardVerdict]):
        if verdict is None:
            return

        timestamp = time.strftime("%H:%M:%S")

        if verdict.vetoed:
            print(f"\n[{timestamp}] \033[91m[VETO ENFORCED]\033[0m Test tampering detected!")
            for v in verdict.violations:
                print(f"  \033[91m[{v.violation_type}]\033[0m {v.file_path}:{v.line_number or '?'}")
                print(f"    Snippet: {v.snippet.strip()}")
            print(f"  \033[93mPrompt Directive:\033[0m {verdict.directive}\n")
        else:
            rep = verdict.report
            if rep and rep.touches_test_files:
                print(
                    f"[{timestamp}] \033[92m[CLEAN]\033[0m Test suite intact: "
                    f"{rep.new_tests_count} new tests across {len(rep.test_files_touched)} test files."
                )
            elif rep and rep.impl_files_touched:
                print(f"[{timestamp}] \033[94m[ACTIVE]\033[0m {len(rep.impl_files_touched)} implementation files modified cleanly.")


def main(argv: Optional[list] = None) -> int:
    """CLI entry point for arma watch."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="arma watch",
        description="ARMA Live Workspace Watcher: Monitors workspace in real time and alerts on test tampering."
    )
    parser.add_argument("--repo", default=".", help="Path to repository root (default: current directory)")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    parser.add_argument("--strict", action="store_true", help="Veto on assertion modifications as well as structural tampering")
    parser.add_argument("--once", action="store_true", help="Check once and exit")

    args = parser.parse_args(argv)
    watcher = RepoWatcher(repo_path=args.repo, strict=args.strict)
    watcher.run(interval_seconds=args.interval, once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
