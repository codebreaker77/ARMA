"""
ARMA Autonomous Self-Healing & Remediation Engine (layer/remediator.py)
Provides:
1. CheckpointManager: Captures lightweight, non-destructive snapshots of clean states.
2. LoopBreaker: Detects circular edit-fail thrashing and triggers automated surgical rollbacks.
3. AlternativeStrategySynthesizer: Formulates actionable pivot guidance for the agent.
"""

import os
import json
import time
import uuid
import shutil
from typing import Dict, Any, List, Optional, Tuple, Set


class CheckpointManager:
    """
    Manages non-destructive shadow checkpoints for codebases.
    Captures file contents when tests pass and restores them when thrashing occurs.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir or os.path.join(os.path.expanduser("~"), ".arma", "checkpoints")
        self.stash_dir = os.path.join(os.path.expanduser("~"), ".arma", "recovery_stash")
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.stash_dir, exist_ok=True)

    def create_checkpoint(
        self,
        session_id: str,
        repo_path: str,
        label: str,
        files: Optional[List[str]] = None
    ) -> str:
        """
        Creates a snapshot of modified or specified files in the repo.
        Returns unique checkpoint_id.
        """
        checkpoint_id = f"ckpt_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        ckpt_meta_path = os.path.join(self.storage_dir, f"{checkpoint_id}.json")

        target_files = files or self._discover_modified_files(repo_path)
        snapshots: Dict[str, str] = {}

        for f_path in target_files:
            abs_path = f_path if os.path.isabs(f_path) else os.path.join(repo_path, f_path)
            rel_path = os.path.relpath(abs_path, repo_path).replace("\\", "/")
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        snapshots[rel_path] = f.read()
                except Exception:
                    pass

        metadata = {
            "checkpoint_id": checkpoint_id,
            "session_id": session_id,
            "repo_path": os.path.abspath(repo_path),
            "label": label,
            "created_at": time.time(),
            "file_count": len(snapshots),
            "files": list(snapshots.keys()),
            "snapshots": snapshots
        }

        with open(ckpt_meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return checkpoint_id

    def rollback(
        self,
        checkpoint_id: str,
        target_files: Optional[List[str]] = None
    ) -> bool:
        """
        Surgically restores files from the checkpoint.
        Saves current state to recovery stash before overwriting.
        """
        ckpt_meta_path = os.path.join(self.storage_dir, f"{checkpoint_id}.json")
        if not os.path.exists(ckpt_meta_path):
            return False

        try:
            with open(ckpt_meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            repo_path = metadata["repo_path"]
            snapshots = metadata["snapshots"]

            # Normalize files to restore
            if target_files:
                normalized_targets = []
                for f in target_files:
                    if os.path.isabs(f):
                        rel = os.path.relpath(f, repo_path).replace("\\", "/")
                    else:
                        rel = f.replace("\\", "/")
                    normalized_targets.append(rel)
                files_to_restore = normalized_targets
            else:
                files_to_restore = list(snapshots.keys())

            # 1. Non-destructive safety stash of current state before rollback
            stash_id = f"stash_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            current_snapshots: Dict[str, str] = {}
            for rel_path in files_to_restore:
                abs_path = os.path.join(repo_path, rel_path)
                if os.path.isfile(abs_path):
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        current_snapshots[rel_path] = f.read()

            stash_meta_path = os.path.join(self.stash_dir, f"{stash_id}.json")
            with open(stash_meta_path, "w", encoding="utf-8") as f:
                json.dump({
                    "stash_id": stash_id,
                    "reverted_from_checkpoint": checkpoint_id,
                    "repo_path": repo_path,
                    "created_at": time.time(),
                    "snapshots": current_snapshots
                }, f, indent=2)

            # 2. Restore file contents from checkpoint
            for rel_path in files_to_restore:
                if rel_path in snapshots:
                    abs_path = os.path.join(repo_path, rel_path)
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    with open(abs_path, "w", encoding="utf-8") as f:
                        f.write(snapshots[rel_path])

            return True

        except Exception as e:
            print(f"[ARMA Rollback Error] {e}")
            return False

    def list_checkpoints(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all available checkpoints ordered by creation time descending."""
        checkpoints = []
        if not os.path.exists(self.storage_dir):
            return checkpoints

        for fname in os.listdir(self.storage_dir):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(self.storage_dir, fname), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not session_id or data.get("session_id") == session_id:
                            checkpoints.append({
                                "checkpoint_id": data["checkpoint_id"],
                                "session_id": data.get("session_id"),
                                "label": data.get("label"),
                                "created_at": data.get("created_at"),
                                "file_count": data.get("file_count", 0),
                                "files": data.get("files", [])
                            })
                except Exception:
                    pass

        checkpoints.sort(key=lambda x: x["created_at"], reverse=True)
        return checkpoints

    def _discover_modified_files(self, repo_path: str) -> List[str]:
        """Discover tracked source files to snapshot."""
        # Try git ls-files if inside a git repository
        try:
            import subprocess
            res = subprocess.run(
                ["git", "ls-files"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=3
            )
            if res.returncode == 0 and res.stdout.strip():
                tracked = [l.strip().replace("\\", "/") for l in res.stdout.splitlines() if l.strip()]
                filtered = [f for f in tracked if f.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".json", ".md"))]
                if filtered:
                    return filtered[:100]
        except Exception:
            pass

        # Fallback to directory scan
        discovered = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in (".git", ".arma", "venv", ".env", "__pycache__", "node_modules", ".pytest_cache")]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".json")):
                    rel = os.path.relpath(os.path.join(root, f), repo_path)
                    discovered.append(rel.replace("\\", "/"))
        return discovered[:100]


class AlternativeStrategySynthesizer:
    """
    Synthesizes concrete, high-signal pivot guidance when an agent is thrashing.
    """

    @staticmethod
    def synthesize_pivot(
        thrashed_file: str,
        failure_count: int,
        checkpoint_label: str,
        task_text: str,
        last_error: Optional[str] = None
    ) -> str:
        """Constructs high-density strategic recommendation for the agent."""
        advice = [
            "<!-- ARMA AUTONOMOUS SELF-HEALING & STRATEGIC PIVOT -->",
            "[CRITICAL INTERVENTION: EDIT-FAIL LOOP DETECTED]",
            f"1. Target File '{thrashed_file}' failed consecutive test evaluations ({failure_count} times).",
            f"2. Automated Surgical Action: Working state has been ROLLED BACK to '{checkpoint_label}'.",
            "3. STRATEGIC PIVOT DIRECTIVE:",
            f"   - Cease repeating modifications directly to '{thrashed_file}'.",
            f"   - The previous approach repeatedly triggered: {last_error or 'Assertion / verification failure'}.",
            "   - Re-evaluate upstream caller modules or interfaces rather than re-attempting identical logic edits.",
            f"   - Core Task Requirement to refocus on: {task_text[:120]}...",
            "Rule: You must inspect alternative files or change implementation strategy before retrying."
        ]
        return "\n".join(advice)

    @staticmethod
    def synthesize_exact_loop_pivot(
        loop_type: str,
        details: str,
        suggested_action: str
    ) -> str:
        """Constructs high-density recovery directives for exact loop states."""
        advice = [
            "<!-- ARMA CONTROLLER: STUCK INTERVENTION & RECOVERY -->",
            f"[CRITICAL INTERVENTION: EXACT LOOP DETECTED - {loop_type.upper()}]",
            f"1. Diagnosis: {details}",
            "2. Action Invariant: You are strictly forbidden from re-executing this exact command or repeating this output.",
            "3. STRATEGIC RECOVERY & RE-PLANNING DIRECTIVE:",
            f"   - {suggested_action}",
            "   - Step back and formulate a new approach. Do NOT retry the same edit or command.",
            "   - Recommend model escalation if current tier cannot resolve the deadlock."
        ]
        return "\n".join(advice)


class LoopBreaker:
    """
    Monitors turn history, detects exact loops and circular thrashing, and executes self-healing rollbacks.
    Implements the 5 canonical OpenHands stuck patterns + semantic edit-fail loop detection.
    """

    def __init__(self, checkpoint_mgr: Optional[CheckpointManager] = None):
        self.ckpt_mgr = checkpoint_mgr or CheckpointManager()
        self.file_attempt_counts: Dict[str, int] = {}
        self.last_green_checkpoint: Optional[str] = None
        self.last_green_label: Optional[str] = None

    def record_green_state(self, session_id: str, repo_path: str, label: str) -> str:
        """Called when tests pass; creates a recovery anchor."""
        ckpt_id = self.ckpt_mgr.create_checkpoint(
            session_id=session_id,
            repo_path=repo_path,
            label=label
        )
        self.last_green_checkpoint = ckpt_id
        self.last_green_label = label
        self.file_attempt_counts.clear()
        return ckpt_id

    @staticmethod
    def check_identical_action_obs(pairs: List[Tuple[str, str]], threshold: int = 4) -> bool:
        """Detect identical action-observation pairs repeating consecutively."""
        if len(pairs) < threshold:
            return False
        last_pair = pairs[-1]
        return all(p == last_pair for p in pairs[-threshold:])

    @staticmethod
    def check_repeated_errors(errors: List[str], threshold: int = 3) -> bool:
        """Detect identical/similar error messages repeating consecutively."""
        if len(errors) < threshold:
            return False
        last_err = errors[-1]
        return all(e == last_err for e in errors[-threshold:])

    @staticmethod
    def check_ping_pong(actions: List[str], threshold: int = 6) -> bool:
        """Detect alternating between two actions A -> B -> A -> B for >= threshold cycles (2*threshold steps)."""
        window = 2 * threshold
        if len(actions) < window:
            return False
        sub = actions[-window:]
        a, b = sub[0], sub[1]
        if a == b:
            return False
        for i in range(0, window, 2):
            if sub[i] != a or sub[i+1] != b:
                return False
        return True

    @staticmethod
    def check_monologue(turn_signatures: List[str], threshold: int = 3) -> bool:
        """Detect assistant sending text messages without invoking any tools."""
        if len(turn_signatures) < threshold:
            return False
        return all(s.startswith("ASSISTANT_TEXT:") for s in turn_signatures[-threshold:])

    def check_and_remediate(
        self,
        session_id: str,
        repo_path: str,
        task_text: str,
        recent_actions: List[Dict[str, Any]],
        test_status: str,
        last_error: Optional[str] = None,
        recent_action_obs_pairs: Optional[List[Tuple[str, str]]] = None,
        recent_errors: Optional[List[str]] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Evaluates whether current action history represents an exact loop or circular thrashing.
        Triggers surgical rollback or strategic recovery guidance without prematurely aborting the session.
        Returns (is_remediated, checkpoint_or_action_id, pivot_text).
        """
        # 1. Check exact loops (OpenHands stuck patterns)
        if recent_action_obs_pairs and self.check_identical_action_obs(recent_action_obs_pairs, threshold=4):
            pivot = AlternativeStrategySynthesizer.synthesize_exact_loop_pivot(
                loop_type="Identical Action-Observation",
                details=f"The exact same command and observation have executed 4 consecutive times: '{recent_action_obs_pairs[-1][0]}'.",
                suggested_action="Execute a diff inspection or check external dependencies instead of retrying."
            )
            return True, "exact_loop_repeat", pivot

        if recent_errors and self.check_repeated_errors(recent_errors, threshold=3):
            pivot = AlternativeStrategySynthesizer.synthesize_exact_loop_pivot(
                loop_type="Repeated Error",
                details=f"The same error signature occurred 3 consecutive times: '{recent_errors[-1]}'.",
                suggested_action="The current hypothesis is disproven. Step back, re-read the issue description, and inspect related caller functions."
            )
            return True, "repeated_error_loop", pivot

        action_sigs = [
            (act.get("tool", "") + ":" + str(act.get("args", ""))[:80])
            for act in (recent_actions or [])
        ]
        if self.check_ping_pong(action_sigs, threshold=6):
            pivot = AlternativeStrategySynthesizer.synthesize_exact_loop_pivot(
                loop_type="Ping-Pong Alternation",
                details="Alternating between two identical actions for 6 consecutive cycles without progress.",
                suggested_action="Break the cycle. Halt automated toggling and check the underlying architectural constraint."
            )
            return True, "ping_pong_loop", pivot

        if not recent_actions:
            return False, None, None

        # 2. Check semantic edit-fail thrashing on files
        target_files = []
        for act in recent_actions[-6:]:
            tool = act.get("tool", "")
            args = act.get("args", {})
            if tool in ("write_to_file", "replace_file_content", "edit_file"):
                f = args.get("TargetFile") or args.get("path") or args.get("file") or ""
                if f:
                    target_files.append(str(f).replace("\\", "/"))

        if not target_files:
            return False, None, None

        most_recent_file = target_files[-1]
        attempts = sum(1 for f in target_files if f == most_recent_file)
        self.file_attempt_counts[most_recent_file] = attempts

        is_failing = "FAIL" in test_status.upper() or "ERROR" in test_status.upper()
        if attempts >= 3 and is_failing and self.last_green_checkpoint:
            success = self.ckpt_mgr.rollback(
                checkpoint_id=self.last_green_checkpoint,
                target_files=[most_recent_file]
            )
            if success:
                pivot_text = AlternativeStrategySynthesizer.synthesize_pivot(
                    thrashed_file=most_recent_file,
                    failure_count=attempts,
                    checkpoint_label=self.last_green_label or "Initial Green State",
                    task_text=task_text,
                    last_error=last_error
                )
                self.file_attempt_counts[most_recent_file] = 0
                return True, self.last_green_checkpoint, pivot_text

        return False, None, None
