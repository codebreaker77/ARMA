"""
ARMA Native Lifecycle Hooks
Provides direct programmatic hooks for harnesses like OpenCode, Claude Code,
and custom Python agent loops.
"""

from typing import Dict, Any, List, Optional
from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine, DecisionGateResult


class ArmaHooks:
    """Standardized hook controller for coding harnesses."""

    def __init__(self, db: Optional[EvidenceDB] = None, engine: Optional[DecisionEngine] = None):
        self.db = db or EvidenceDB()
        self.engine = engine or DecisionEngine(evidence_db=self.db)
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def on_session_start(self, repo_path: str, harness: str, task_text: str) -> str:
        """Called when an agent session begins."""
        session_id = self.db.start_session(
            repo_path=repo_path,
            harness=harness,
            task_text=task_text
        )
        self.active_sessions[session_id] = {
            "turn": 0,
            "recent_actions": [],
            "task_text": task_text
        }
        return session_id

    def on_session_end(self, session_id: str, final_status: str = "resolved"):
        """Called when an agent session concludes."""
        self.db.end_session(session_id=session_id, final_status=final_status)
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]

    def on_stop_requested(
        self,
        session_id: str,
        test_results: Optional[Dict[str, Any]] = None,
        diff_stat: Optional[str] = None
    ) -> DecisionGateResult:
        """
        Called when the agent attempts to stop or declare task completion.
        Returns DecisionGateResult with allow=True/False and diagnostic reason.
        """
        sess = self.active_sessions.get(session_id, {})
        turn = sess.get("turn", 0) + 1
        sess["turn"] = turn

        event_id = self.db.record_event(
            session_id=session_id,
            turn=turn,
            kind="stop_requested",
            raw_payload_summary=f"Tests: {bool(test_results)}, Diff: {diff_stat}"
        )

        return self.engine.evaluate_stop(
            session_id=session_id,
            event_id=event_id,
            task_text=sess.get("task_text", "Unknown Task"),
            test_results=test_results,
            diff_stat=diff_stat
        )

    def on_pre_tool_use(
        self,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any]
    ) -> DecisionGateResult:
        """
        Called immediately before an agent executes a tool (e.g. bash, edit_file).
        Enforces RiskGate on commands and ScopeGate on file modifications.
        """
        sess = self.active_sessions.get(session_id, {})
        turn = sess.get("turn", 0) + 1
        sess["turn"] = turn

        event_id = self.db.record_event(
            session_id=session_id,
            turn=turn,
            kind="pre_tool_use",
            tool_name=tool_name,
            raw_payload_summary=str(tool_args)[:200]
        )

        # Track recent actions for loop detection
        recent = sess.get("recent_actions", [])
        recent.append({"tool": tool_name, "args": tool_args})
        sess["recent_actions"] = recent[-10:]

        # 1. Evaluate Loop Detector
        loop_res = self.engine.evaluate_loop(session_id, event_id, recent)
        if not loop_res.allow:
            return loop_res

        # 2. Evaluate Risk Gate for bash / shell commands
        if tool_name in ("bash", "run_command", "execute_command", "terminal"):
            cmd = tool_args.get("command") or tool_args.get("cmd") or str(tool_args)
            return self.engine.evaluate_risk(session_id, event_id, command=cmd)

        # 3. Evaluate Scope Gate for file write / edit operations
        if tool_name in ("write_to_file", "replace_file_content", "edit_file"):
            target = tool_args.get("TargetFile") or tool_args.get("path") or tool_args.get("file") or ""
            return self.engine.evaluate_scope(
                session_id=session_id,
                event_id=event_id,
                task_text=sess.get("task_text", ""),
                target_file=str(target)
            )

        # Default pass for benign read tools
        return DecisionGateResult(
            module="pre_tool_pass",
            allow=True,
            mode="pass",
            action_taken="pass",
            counterfactual_action="pass",
            reason="Benign tool invocation",
            confidence=1.0,
            probability=1.0
        )

    def on_outcome_observed(self, decision_id: str, label: str, source: str = "test_runner"):
        """Record ground truth (e.g. test_pass, git_reverted, user_approved)."""
        self.db.record_outcome(decision_id=decision_id, label=label, source=source)
