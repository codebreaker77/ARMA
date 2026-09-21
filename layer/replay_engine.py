"""
ARMA Trace Replay Simulator (layer/replay_engine.py)
Replays historical agent sessions through candidate decision policies
to compute counterfactual accuracy, false-alarm reduction, and policy lift
before modules are promoted to higher enforcement levels.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine
from layer.calibrator import TemperatureScaler, CalibrationStore


@dataclass
class ReplayDecisionDiff:
    decision_id: str
    session_id: str
    turn: int
    module: str
    original_action: str
    candidate_action: str
    ground_truth: Optional[str]
    original_prob: Optional[float]
    candidate_prob: Optional[float]
    was_improvement: bool
    explanation: str


@dataclass
class ReplaySummary:
    total_replayed: int
    original_correct: int
    candidate_correct: int
    original_accuracy: float
    candidate_accuracy: float
    counterfactual_lift: float
    original_false_stops: int
    candidate_false_stops: int
    net_false_alarms_eliminated: int
    diffs: List[ReplayDecisionDiff] = field(default_factory=list)


class ReplayEngine:
    """
    Simulates historical traces recorded in EvidenceDB against
    candidate DecisionEngine policies or calibrated parameter sets.
    """

    def __init__(self, db: Optional[EvidenceDB] = None):
        self.db = db or EvidenceDB()

    def replay_session(
        self,
        session_id: str,
        candidate_config: Optional[Dict[str, Any]] = None
    ) -> ReplaySummary:
        """Replay all decisions within a specific session."""
        query = """
            SELECT d.id, d.event_id, d.module, d.question_text, d.probability,
                   d.threshold, d.action_taken, d.counterfactual_action,
                   e.session_id, e.turn, e.raw_payload_summary, o.label
            FROM decisions d
            JOIN events e ON d.event_id = e.id
            LEFT JOIN outcomes o ON d.id = o.decision_id
            WHERE e.session_id = ?
            ORDER BY e.turn ASC, d.created_at ASC
        """
        with self.db._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(query, (session_id,)).fetchall()]

        return self._evaluate_rows(rows, candidate_config)

    def replay_all(
        self,
        module: Optional[str] = None,
        candidate_config: Optional[Dict[str, Any]] = None
    ) -> ReplaySummary:
        """Replay all labeled decisions recorded across all historical sessions."""
        query = """
            SELECT d.id, d.event_id, d.module, d.question_text, d.probability,
                   d.threshold, d.action_taken, d.counterfactual_action,
                   e.session_id, e.turn, e.raw_payload_summary, o.label
            FROM decisions d
            JOIN events e ON d.event_id = e.id
            LEFT JOIN outcomes o ON d.id = o.decision_id
            WHERE 1=1
        """
        params = []
        if module:
            query += " AND d.module = ?"
            params.append(module)

        query += " ORDER BY d.created_at ASC"

        with self.db._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        return self._evaluate_rows(rows, candidate_config)

    def _evaluate_rows(
        self,
        rows: List[Dict[str, Any]],
        candidate_config: Optional[Dict[str, Any]] = None
    ) -> ReplaySummary:
        """Evaluate historical rows against candidate calibration configuration."""
        config = candidate_config or CalibrationStore.load()

        total = len(rows)
        if total == 0:
            return ReplaySummary(
                total_replayed=0,
                original_correct=0,
                candidate_correct=0,
                original_accuracy=0.0,
                candidate_accuracy=0.0,
                counterfactual_lift=0.0,
                original_false_stops=0,
                candidate_false_stops=0,
                net_false_alarms_eliminated=0
            )

        orig_correct = 0
        cand_correct = 0
        orig_false_stops = 0
        cand_false_stops = 0
        diffs: List[ReplayDecisionDiff] = []

        for r in rows:
            mod = r["module"]
            mod_cfg = config.get(mod, {})
            cand_t = mod_cfg.get("temperature", 1.0)
            cand_b = mod_cfg.get("bias", 0.0)
            cand_tau = mod_cfg.get("threshold", 0.5)

            orig_p = r["probability"]
            orig_action = r["action_taken"]
            label = r["label"]

            # Ground truth determination:
            # For Stop Gate: test_pass / user_approved -> should allow ('pass')
            #                test_fail / unhandled_error -> should block ('block')
            is_positive_truth = label in ("test_pass", "user_approved", "diff_survived", "task_resolved")

            # Determine original correctness
            orig_passed = (orig_action == "pass")
            if orig_passed == is_positive_truth:
                orig_correct += 1
            if orig_passed and not is_positive_truth and mod == "stop_gate":
                orig_false_stops += 1

            # Candidate re-evaluation
            if orig_p is not None:
                cand_p = TemperatureScaler.scale_probability(orig_p, cand_t, cand_b)
                cand_action = "pass" if cand_p >= cand_tau else "block"
            else:
                cand_p = None
                cand_action = orig_action

            cand_passed = (cand_action == "pass")
            if cand_passed == is_positive_truth:
                cand_correct += 1
            if cand_passed and not is_positive_truth and mod == "stop_gate":
                cand_false_stops += 1

            # Check if candidate differed from original
            if cand_action != orig_action:
                was_imp = (cand_passed == is_positive_truth) and (orig_passed != is_positive_truth)
                diff = ReplayDecisionDiff(
                    decision_id=r["id"],
                    session_id=r["session_id"],
                    turn=r["turn"],
                    module=mod,
                    original_action=orig_action,
                    candidate_action=cand_action,
                    ground_truth=label,
                    original_prob=orig_p,
                    candidate_prob=cand_p,
                    was_improvement=was_imp,
                    explanation=(
                        f"Candidate threshold {cand_tau} (T={cand_t}) flipped action "
                        f"from {orig_action} to {cand_action} (truth: {label})"
                    )
                )
                diffs.append(diff)

        orig_acc = round(orig_correct / total, 4)
        cand_acc = round(cand_correct / total, 4)
        lift = round(cand_acc - orig_acc, 4)
        eliminated_false_alarms = orig_false_stops - cand_false_stops

        return ReplaySummary(
            total_replayed=total,
            original_correct=orig_correct,
            candidate_correct=cand_correct,
            original_accuracy=orig_acc,
            candidate_accuracy=cand_acc,
            counterfactual_lift=lift,
            original_false_stops=orig_false_stops,
            candidate_false_stops=cand_false_stops,
            net_false_alarms_eliminated=eliminated_false_alarms,
            diffs=diffs
        )
