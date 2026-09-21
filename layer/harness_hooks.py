"""
ARMA Native Lifecycle Hooks
Provides direct programmatic hooks for harnesses like OpenCode, Claude Code,
and custom Python agent loops.
"""

from typing import Dict, Any, List, Optional, Set
from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine, DecisionGateResult
from layer.context_plane import ToolOutputPruner, PinnedFactsManager
from layer.code_graph import CodeGraph
from layer.remediator import CheckpointManager, LoopBreaker


class ArmaHooks:
    """Standardized hook controller for coding harnesses."""

    def __init__(
        self,
        db: Optional[EvidenceDB] = None,
        engine: Optional[DecisionEngine] = None,
        code_graph: Optional[CodeGraph] = None,
        checkpoint_mgr: Optional[CheckpointManager] = None,
        loop_breaker: Optional[LoopBreaker] = None
    ):
        self.db = db or EvidenceDB()
        self.ckpt_mgr = checkpoint_mgr or CheckpointManager()
        self.loop_breaker = loop_breaker or LoopBreaker(checkpoint_mgr=self.ckpt_mgr)
        self.engine = engine or DecisionEngine(evidence_db=self.db, loop_breaker=self.loop_breaker)
        self.code_graph = code_graph
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def on_session_start(self, repo_path: str, harness: str, task_text: str, checklist: Optional[List[str]] = None) -> str:
        """Called when an agent session begins."""
        session_id = self.db.start_session(
            repo_path=repo_path,
            harness=harness,
            task_text=task_text
        )
        pinned = PinnedFactsManager(task_checklist=checklist or [task_text])
        if self.code_graph:
            # Predict initial impact if task references files
            pinned.set_impact_set(set(self.code_graph.indexed_files))

        # Record initial clean state anchor
        try:
            self.loop_breaker.record_green_state(
                session_id=session_id,
                repo_path=repo_path,
                label="Session Initial State"
            )
        except Exception:
            pass

        self.active_sessions[session_id] = {
            "turn": 0,
            "recent_actions": [],
            "task_text": task_text,
            "pinned_facts": pinned,
            "repo_path": repo_path,
            "last_error": None
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

        pinned: Optional[PinnedFactsManager] = sess.get("pinned_facts")
        test_status = pinned.test_status if pinned else "UNTESTED"
        task_text = sess.get("task_text", "")
        repo_path = sess.get("repo_path", ".")
        last_error = sess.get("last_error")

        # 1. Autonomous Remediation & Loop Breaker Evaluation
        thrashing_detected, ckpt_id, pivot_text = self.loop_breaker.check_and_remediate(
            session_id=session_id,
            repo_path=repo_path,
            task_text=task_text,
            recent_actions=recent,
            test_status=test_status,
            last_error=last_error
        )
        if thrashing_detected and pivot_text:
            if pinned:
                pinned.set_pivot_guidance(pivot_text)

            mode = self.engine.ladder.get_mode("loop_detector")
            action = "pass" if mode == "shadow" else ("warn" if mode == "advisory" else "intervene")
            allow = (mode == "shadow")

            dec_id = self.db.record_decision(
                event_id=event_id,
                module="loop_detector",
                question_type="choice",
                question_text="remediation_status",
                answer_raw="thrashing_remediated",
                probability=0.0,
                confidence=1.0,
                backend="loop_breaker",
                model_version="1.0.0",
                threshold=0.70,
                mode=mode,
                action_taken=action,
                counterfactual_action="rollback"
            )

            return DecisionGateResult(
                module="loop_detector",
                allow=allow,
                mode=mode,
                action_taken=action,
                counterfactual_action="rollback",
                reason=f"Edit-fail loop broken: rolled back to {ckpt_id}. Pivot guidance injected into context.",
                confidence=1.0,
                probability=0.0,
                decision_id=dec_id,
                raw_decision={"pivot_text": pivot_text, "checkpoint_id": ckpt_id}
            )

        # Standard classifier loop evaluation
        loop_res = self.engine.evaluate_loop(session_id, event_id, recent)
        if loop_res.counterfactual_action == "intervene" or not loop_res.allow:
            return loop_res


        # 2. Evaluate Risk Gate for bash / shell commands
        if tool_name in ("bash", "run_command", "execute_command", "terminal"):
            cmd = tool_args.get("command") or tool_args.get("cmd") or str(tool_args)
            return self.engine.evaluate_risk(session_id, event_id, command=cmd)

        # 3. Evaluate Scope Gate for file write / edit operations
        if tool_name in ("write_to_file", "replace_file_content", "edit_file"):
            target = tool_args.get("TargetFile") or tool_args.get("path") or tool_args.get("file") or ""
            target_str = str(target)
            pinned: Optional[PinnedFactsManager] = sess.get("pinned_facts")
            if pinned and target_str:
                pinned.record_file_touched(target_str)

            return self.engine.evaluate_scope(
                session_id=session_id,
                event_id=event_id,
                task_text=sess.get("task_text", ""),
                target_file=target_str
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

    def on_tool_output(self, session_id: str, tool_name: str, raw_output: str, exit_code: int = 0) -> str:
        """
        Prunes verbose tool output (test logs, diffs, compiler errors)
        and updates session invariants in PinnedFactsManager.
        """
        sess = self.active_sessions.get(session_id, {})
        pinned: Optional[PinnedFactsManager] = sess.get("pinned_facts")

        # Check if output is from a test runner
        is_test = any(kw in raw_output for kw in ("pytest", "unittest", "FAILED", "PASSED", "Ran "))
        if is_test and pinned:
            passed = exit_code == 0 and ("FAILED" not in raw_output and "FAILURES" not in raw_output)
            pinned.update_test_status(passed=passed, exit_code=exit_code)
            if passed:
                repo_p = sess.get("repo_path", ".")
                self.loop_breaker.record_green_state(
                    session_id=session_id,
                    repo_path=repo_p,
                    label=f"Turn {sess.get('turn', 0)} Tests Passed"
                )
                sess["last_error"] = None
                pinned.set_pivot_guidance(None)
            else:
                sess["last_error"] = raw_output[:300]

        # Prune output using ARMA ToolOutputPruner
        pruned = ToolOutputPruner.prune(raw_output)
        return pruned

    def on_prepare_prompt(self, session_id: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Injects pinned invariants (checklist, test status, blast radius)
        at the context tail right before the LLM generates a response.
        """
        sess = self.active_sessions.get(session_id, {})
        pinned: Optional[PinnedFactsManager] = sess.get("pinned_facts")
        if not pinned:
            return messages

        return pinned.inject_into_messages(messages)

    def on_outcome_observed(self, decision_id: str, label: str, source: str = "test_runner"):
        """Record ground truth (e.g. test_pass, git_reverted, user_approved)."""
        self.db.record_outcome(decision_id=decision_id, label=label, source=source)

