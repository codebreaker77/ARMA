"""
ARMA Decision Plane: Core Engine and Decision Gates
Implements the hybrid invariant:
Deterministic checks execute first with hard veto;
Classifier evaluates the fuzzy middle with calibrated confidence.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from micro_jev import MicroJevClient, Noul, Choice, Score
from layer.evidence_db import EvidenceDB
from layer.promotion_ladder import PromotionLadder
from layer.gate_specs import StopGateSpec, ScopeGateSpec, RiskGateSpec, LoopDetectorSpec
from layer.calibrator import CalibrationStore, TemperatureScaler



# Hard-coded destructive command patterns for instant deterministic veto
HARD_DENY_COMMAND_PATTERNS = [
    r"\brm\s+-(?:rf|fr|r\s+-f|f\s+-r)\s+[/~]",   # rm -rf / or rm -rf ~
    r"\bDROP\s+DATABASE\b",                     # Drop database
    r"\bDROP\s+TABLE\b",                        # Drop table
    r"\bTRUNCATE\s+TABLE\b",                    # Truncate table
    r"\bgit\s+push\s+(?:--force|-f)\b",         # Force push
    r"\bchmod\s+777\b",                         # Insecure permissions
    r"\bcurl\b.*\|\s*(?:bash|sh)\b",            # Piping curl to bash
    r"\bmkfs\b",                                # Format filesystem
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",   # Fork bomb
]


class DecisionGateResult:
    """Standardized evaluation outcome from a Decision Gate."""
    def __init__(
        self,
        module: str,
        allow: bool,
        mode: str,
        action_taken: str,
        counterfactual_action: str,
        reason: str,
        confidence: float,
        probability: Optional[float] = None,
        raw_decision: Optional[Dict[str, Any]] = None,
        decision_id: Optional[str] = None
    ):
        self.module = module
        self.allow = allow
        self.mode = mode
        self.action_taken = action_taken
        self.counterfactual_action = counterfactual_action
        self.reason = reason
        self.confidence = confidence
        self.probability = probability
        self.raw_decision = raw_decision or {}
        self.decision_id = decision_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "module": self.module,
            "allow": self.allow,
            "mode": self.mode,
            "action_taken": self.action_taken,
            "counterfactual_action": self.counterfactual_action,
            "reason": self.reason,
            "confidence": self.confidence,
            "probability": self.probability,
            "raw_decision": self.raw_decision
        }



class DecisionEngine:
    """
    Central coordinator for ARMA Decision Gates.
    Evaluates actions against deterministic rules and calibrated classifiers.
    Logs all decisions and counterfactuals to the Evidence Plane.
    """

    def __init__(
        self,
        evidence_db: Optional[EvidenceDB] = None,
        classifier_client: Optional[MicroJevClient] = None,
        default_mode: str = "shadow",
        calibration_path: Optional[str] = None,
        loop_breaker: Optional[Any] = None
    ):
        self.db = evidence_db or EvidenceDB()
        self.classifier = classifier_client or MicroJevClient()
        self.ladder = PromotionLadder(db=self.db)
        self.calibration_path = calibration_path
        self.calibration = CalibrationStore.load(self.calibration_path)
        self.loop_breaker = loop_breaker
        for mod in ("stop_gate", "scope_gate", "risk_gate", "loop_detector"):
            self.ladder.set_mode(mod, default_mode)

    def reload_calibration(self, calibration_path: Optional[str] = None):
        """Reload temperature scaling and threshold parameters from disk."""
        if calibration_path:
            self.calibration_path = calibration_path
        self.calibration = CalibrationStore.load(self.calibration_path)

    def get_module_calibration(self, module: str) -> Dict[str, Any]:
        """Fetch active temperature and threshold for a module."""
        return self.calibration.get(module, {"temperature": 1.0, "threshold": 0.5})

    @property
    def module_modes(self) -> Dict[str, str]:
        return self.ladder._modes

    def set_module_mode(self, module: str, mode: str):
        """Set the promotion mode for a specific module."""
        self.ladder.set_mode(module, mode)

    def get_module_mode(self, module: str) -> str:
        """Get the current promotion mode for a module."""
        return self.ladder.get_mode(module)

    def check_promotion(self, module: str) -> Dict[str, Any]:
        """Evaluate and apply automated promotion for a module."""
        return self.ladder.check_and_promote(module)


    # -----------------------------------------------------------------------
    # 1. Stop Gate
    # -----------------------------------------------------------------------
    def evaluate_stop(
        self,
        session_id: str,
        event_id: str,
        task_text: str,
        test_results: Optional[Dict[str, Any]] = None,
        diff_stat: Optional[str] = None,
        checklist_status: Optional[str] = None
    ) -> DecisionGateResult:
        """
        Stop Gate: Evaluates whether the agent should be allowed to exit.
        Prevents premature exits when tests are failing or tasks remain incomplete.
        """
        mode = self.module_modes["stop_gate"]

        # 1. Deterministic Check: If test suite failed with non-zero exit code
        if test_results and test_results.get("exit_code", 0) != 0:
            reason = f"Deterministic Block: Test suite failed with exit code {test_results['exit_code']}."
            action_taken = "pass" if mode == "shadow" else "block"
            counterfactual = "block"
            dec_id = self.db.record_decision(
                event_id=event_id,
                module="stop_gate",
                question_type="deterministic",
                question_text="exit_code == 0",
                answer_raw="FAILED",
                probability=0.0,
                confidence=1.0,
                backend="deterministic_rule",
                model_version="1.0",
                threshold=0.5,
                mode=mode,
                action_taken=action_taken,
                counterfactual_action=counterfactual
            )
            return DecisionGateResult(
                module="stop_gate",
                allow=(action_taken == "pass"),
                mode=mode,
                action_taken=action_taken,
                counterfactual_action=counterfactual,
                reason=reason,
                confidence=1.0,
                probability=0.0,
                decision_id=dec_id
            )


        # 2. Classifier Evaluation on the Fuzzy Middle
        state = {
            "task_requirements": task_text,
            "test_summary": str(test_results) if test_results else "No tests reported",
            "git_diffstat": diff_stat or "No diff recorded",
            "checklist": checklist_status or "Not provided"
        }

        eval_res = self.classifier.system_one(
            state=state,
            questions={
                "requirements_satisfied": Noul(
                    instructions="Does the code change and test evidence satisfy all requirements of the stated task?"
                ),
                "completion_state": Choice(
                    instructions="Classify the overall state of the task.",
                    criteria={
                        "done": "All requirements verified with passing tests",
                        "needs_verification": "Changes made but unverified with tests or syntax checks",
                        "incomplete": "Key requirements unaddressed or partially implemented",
                        "blocked": "Agent is blocked on missing tools or environment issues"
                    }
                )
            }
        )

        noul = eval_res.answers["requirements_satisfied"]
        choice = eval_res.answers["completion_state"]
        raw_prob = noul.probability
        conf = choice.confidence

        stop_cal = self.get_module_calibration("stop_gate")
        temp = stop_cal.get("temperature", 1.0)
        bias = stop_cal.get("bias", 0.0)
        tau = stop_cal.get("threshold", 0.70)
        prob = TemperatureScaler.scale_probability(raw_prob, temp, bias)

        tests_passed = bool(test_results and test_results.get("exit_code") == 0)
        is_complete = (
            (tests_passed and choice.selected_option in ("done", "needs_verification")) or
            (prob >= tau and choice.selected_option == "done")
        )
        counterfactual = "pass" if is_complete else "block"


        if mode == "enforce":
            action = "pass" if is_complete else "block"
            allow = is_complete
        elif mode == "advisory":
            action = "pass" if is_complete else "warn"
            allow = True
        else:  # shadow
            action = "pass"
            allow = True

        reason = (
            "Task verified as complete." if is_complete
            else f"Incomplete task state: {choice.selected_option} (prob_satisfied={prob:.2f})."
        )

        dec_id = self.db.record_decision(
            event_id=event_id,
            module="stop_gate",
            question_type="noul+choice",
            question_text="requirements_satisfied & completion_state",
            answer_raw=f"{choice.selected_option} (p={prob})",
            probability=prob,
            confidence=conf,
            backend="micro_jev",
            model_version="0.1.0",
            threshold=0.70,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual
        )

        return DecisionGateResult(
            module="stop_gate",
            allow=allow,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual,
            reason=reason,
            confidence=conf,
            probability=prob,
            decision_id=dec_id,
            raw_decision={
                "noul": noul.model_dump() if hasattr(noul, "model_dump") else noul.dict(),
                "choice": choice.model_dump() if hasattr(choice, "model_dump") else choice.dict()
            }
        )




    # -----------------------------------------------------------------------
    # 2. Risk Gate
    # -----------------------------------------------------------------------
    def evaluate_risk(
        self,
        session_id: str,
        event_id: str,
        command: str,
        cwd: Optional[str] = None
    ) -> DecisionGateResult:
        """
        Risk Gate: Evaluates whether a proposed shell command is safe to execute.
        Blocks destructive or exfiltrating operations.
        """
        mode = self.module_modes["risk_gate"]

        # 1. Deterministic Hard Veto
        for pattern in HARD_DENY_COMMAND_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Deterministic Veto: Command matches destructive pattern: {pattern}"
                action_taken = "pass" if mode == "shadow" else "block"
                counterfactual = "block"
                dec_id = self.db.record_decision(
                    event_id=event_id,
                    module="risk_gate",
                    question_type="deterministic_regex",
                    question_text=pattern,
                    answer_raw="HARD_DENY",
                    probability=0.0,
                    confidence=1.0,
                    backend="deterministic_rule",
                    model_version="1.0",
                    threshold=0.5,
                    mode=mode,
                    action_taken=action_taken,
                    counterfactual_action=counterfactual
                )
                return DecisionGateResult(
                    module="risk_gate",
                    allow=(action_taken == "pass"),
                    mode=mode,
                    action_taken=action_taken,
                    counterfactual_action=counterfactual,
                    reason=reason,
                    confidence=1.0,
                    probability=0.0,
                    decision_id=dec_id
                )


        # 2. Classifier Judgment for Ambiguous Commands
        eval_res = self.classifier.system_one(
            state={"command": command, "cwd": cwd or "current_directory"},
            questions={
                "safety_tier": Choice(
                    instructions="Classify the risk level of this shell command.",
                    criteria={
                        "read_only": "Listing, reading, grep, status, diff, inspect",
                        "recoverable": "Standard file edits, git commit, compiling, installing packages",
                        "destructive": "Deleting directories, dropping data, rewriting git history, killing processes",
                        "exfiltrating": "Sending environment secrets or internal source code to external servers"
                    }
                )
            }
        )

        tier_choice = eval_res.answers["safety_tier"]
        tier = tier_choice.selected_option
        conf = tier_choice.confidence

        is_safe = tier in ("read_only", "recoverable")
        counterfactual = "pass" if is_safe else "block"

        if mode == "enforce":
            action = "pass" if is_safe else "block"
            allow = is_safe
        elif mode == "advisory":
            action = "pass" if is_safe else "warn"
            allow = True
        else:  # shadow
            action = "pass"
            allow = True

        reason = f"Command evaluated as {tier} (conf={conf:.2f})"

        dec_id = self.db.record_decision(
            event_id=event_id,
            module="risk_gate",
            question_type="choice",
            question_text="safety_tier",
            answer_raw=tier,
            probability=(1.0 if is_safe else 0.0),
            confidence=conf,
            backend="micro_jev",
            model_version="0.1.0",
            threshold=0.75,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual
        )

        return DecisionGateResult(
            module="risk_gate",
            allow=allow,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual,
            reason=reason,
            confidence=conf,
            probability=(1.0 if is_safe else 0.0),
            decision_id=dec_id,
            raw_decision={"choice": tier_choice.model_dump() if hasattr(tier_choice, "model_dump") else tier_choice.dict()}
        )



    # -----------------------------------------------------------------------
    # 3. Scope Gate
    # -----------------------------------------------------------------------
    def evaluate_scope(
        self,
        session_id: str,
        event_id: str,
        task_text: str,
        target_file: str,
        impact_set: Optional[List[str]] = None
    ) -> DecisionGateResult:
        """
        Scope Gate: Evaluates whether editing target_file is within the task scope.
        Leverages Fullerenes impact set when available.
        """
        mode = self.module_modes["scope_gate"]

        # Deterministic check: If Fullerenes impact set is provided
        if impact_set is not None:
            in_impact = target_file in impact_set
            action_taken = "pass" if (in_impact or mode == "shadow") else ("warn" if mode == "advisory" else "block")
            counterfactual = "pass" if in_impact else "block"
            allow = True if mode in ("shadow", "advisory") else in_impact
            reason = (
                f"Scope Gate: File {target_file} is verified inside Fullerenes impact set."
                if in_impact
                else f"Scope Gate: File {target_file} is outside Fullerenes impact set ({len(impact_set)} files)."
            )
            dec_id = self.db.record_decision(
                event_id=event_id,
                module="scope_gate",
                question_type="impact_set_membership",
                question_text="target_file in impact_set",
                answer_raw="INSIDE_BLAST_RADIUS" if in_impact else "OUTSIDE_BLAST_RADIUS",
                probability=(1.0 if in_impact else 0.0),
                confidence=1.0,
                backend="fullerenes_graph",
                model_version="1.0",
                threshold=0.5,
                mode=mode,
                action_taken=action_taken,
                counterfactual_action=counterfactual
            )
            return DecisionGateResult(
                module="scope_gate",
                allow=allow,
                mode=mode,
                action_taken=action_taken,
                counterfactual_action=counterfactual,
                reason=reason,
                confidence=1.0,
                probability=(1.0 if in_impact else 0.0),
                decision_id=dec_id
            )

        # Classifier fallback check for semantic relevance when no graph impact set is available
        eval_res = self.classifier.system_one(
            state={"task": task_text, "file_to_edit": target_file},
            questions={
                "is_file_in_scope": Noul(
                    instructions="Is modifying this target file necessary and justifiable for the stated task?"
                )
            }
        )

        noul = eval_res.answers["is_file_in_scope"]
        raw_prob = noul.probability
        conf = noul.confidence

        scope_cal = self.get_module_calibration("scope_gate")
        temp = scope_cal.get("temperature", 1.0)
        bias = scope_cal.get("bias", 0.0)
        tau = scope_cal.get("threshold", 0.50)
        prob = TemperatureScaler.scale_probability(raw_prob, temp, bias)

        in_scope = prob >= tau
        counterfactual = "pass" if in_scope else "block"

        action = "pass" if (in_scope or mode == "shadow") else ("warn" if mode == "advisory" else "block")
        allow = True if mode in ("shadow", "advisory") else in_scope

        dec_id = self.db.record_decision(
            event_id=event_id,
            module="scope_gate",
            question_type="noul",
            question_text="is_file_in_scope",
            answer_raw=str(in_scope),
            probability=prob,
            confidence=conf,
            backend="micro_jev",
            model_version="0.1.0",
            threshold=0.50,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual
        )

        raw_dump = noul.model_dump() if hasattr(noul, "model_dump") else noul.dict()
        return DecisionGateResult(
            module="scope_gate",
            allow=allow,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual,
            reason=f"Scope check: p_in_scope={prob:.2f}",
            confidence=conf,
            probability=prob,
            decision_id=dec_id,
            raw_decision={"noul": raw_dump}
        )



    # -----------------------------------------------------------------------
    # 4. Loop Detector
    # -----------------------------------------------------------------------
    def evaluate_loop(
        self,
        session_id: str,
        event_id: str,
        recent_actions: List[Dict[str, Any]],
        repo_path: str = ".",
        task_text: str = "",
        test_status: str = "UNTESTED",
        last_error: Optional[str] = None
    ) -> DecisionGateResult:
        """
        Loop Detector: Identifies thrashing and circular actions in a rolling window.
        """
        mode = self.module_modes["loop_detector"]

        # Autonomous Remediation if loop_breaker is attached
        if self.loop_breaker:
            remediated, ckpt_id, pivot_text = self.loop_breaker.check_and_remediate(
                session_id=session_id,
                repo_path=repo_path,
                task_text=task_text,
                recent_actions=recent_actions,
                test_status=test_status,
                last_error=last_error
            )
            if remediated and pivot_text:
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
                    reason=f"Edit-fail loop broken: rolled back to {ckpt_id}. Pivot guidance synthesized.",
                    confidence=1.0,
                    probability=0.0,
                    decision_id=dec_id,
                    raw_decision={"pivot_text": pivot_text, "checkpoint_id": ckpt_id}
                )

        if len(recent_actions) < 3:
            return DecisionGateResult(
                module="loop_detector",
                allow=True,
                mode=mode,
                action_taken="pass",
                counterfactual_action="pass",
                reason="Insufficient history (<3 actions)",
                confidence=1.0,
                probability=1.0
            )

        history_summary = "\n".join(
            f"Turn {i}: {a.get('tool', 'action')} on {a.get('target', 'unknown')}"
            for i, a in enumerate(recent_actions[-5:])
        )

        eval_res = self.classifier.system_one(
            state={"recent_history": history_summary},
            questions={
                "progress_state": Choice(
                    instructions="Evaluate whether the agent is making progress or stuck in a loop.",
                    criteria={
                        "progressing": "New files inspected, new approaches tested, forward momentum",
                        "thrashing": "Reverting previous changes, editing same lines repeatedly, circular testing",
                        "blocked": "Repeating failed commands with identical error messages"
                    }
                )
            }
        )

        choice = eval_res.answers["progress_state"]
        conf = choice.confidence
        is_looping = choice.selected_option in ("thrashing", "blocked")
        counterfactual = "intervene" if is_looping else "pass"

        action = "pass" if (not is_looping or mode == "shadow") else ("warn" if mode == "advisory" else "intervene")
        allow = not (is_looping and mode == "enforce")

        dec_id = self.db.record_decision(
            event_id=event_id,
            module="loop_detector",
            question_type="choice",
            question_text="progress_state",
            answer_raw=choice.selected_option,
            probability=(0.0 if is_looping else 1.0),
            confidence=conf,
            backend="micro_jev",
            model_version="0.1.0",
            threshold=0.70,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual
        )

        return DecisionGateResult(
            module="loop_detector",
            allow=allow,
            mode=mode,
            action_taken=action,
            counterfactual_action=counterfactual,
            reason=f"Loop check: {choice.selected_option} (conf={conf:.2f})",
            confidence=conf,
            probability=(0.0 if is_looping else 1.0),
            decision_id=dec_id,
            raw_decision={"choice": choice.model_dump() if hasattr(choice, "model_dump") else choice.dict()}
        )



