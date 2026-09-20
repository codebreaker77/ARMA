"""
ARMA Promotion Ladder: Module State Machine & Statistical Advancement Engine
Evaluates empirical precision, false-block rates, and Expected Calibration Error (ECE)
from the Evidence Plane to promote gates:
  shadow -> advisory -> confirm -> enforce
"""

import json
from typing import Dict, Any, Optional
from layer.evidence_db import EvidenceDB


# Formal mathematical thresholds for advancing along the promotion ladder
PROMOTION_STANDARDS = {
    "shadow_to_advisory": {
        "min_labeled": 15,
        "min_precision": 0.88,
        "max_ece": 0.12,
    },
    "advisory_to_confirm": {
        "min_labeled": 30,
        "min_precision": 0.93,
        "max_ece": 0.08,
    },
    "confirm_to_enforce": {
        "min_labeled": 45,
        "min_precision": 0.96,
        "max_false_stop_rate": 0.04,
        "max_ece": 0.05,
    }
}

VALID_MODES = ("shadow", "advisory", "confirm", "enforce")


class PromotionLadder:
    """Manages lifecycle promotion states for all ARMA Decision Gates."""

    def __init__(self, db: Optional[EvidenceDB] = None):
        self.db = db or EvidenceDB()
        self._modes: Dict[str, str] = {
            "stop_gate": "shadow",
            "scope_gate": "shadow",
            "risk_gate": "shadow",
            "loop_detector": "shadow"
        }

    def get_mode(self, module: str) -> str:
        return self._modes.get(module, "shadow")

    def set_mode(self, module: str, mode: str):
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of {VALID_MODES}")
        if module not in self._modes:
            raise ValueError(f"Unknown module '{module}'.")
        self._modes[module] = mode

    def evaluate_promotion(self, module: str) -> Dict[str, Any]:
        """
        Calculates empirical metrics from the Evidence Plane and checks
        if the module meets the criteria for promotion to the next tier.
        """
        current_mode = self.get_mode(module)
        metrics = self.db.calculate_calibration_metrics(module=module)

        total_labeled = metrics.get("total_labeled", 0)
        precision = metrics.get("precision", 0.0)
        ece = metrics.get("ece", 1.0)

        # Check for false-stop rate specifically for stop_gate
        false_stop_rate = 0.0
        if module == "stop_gate" and total_labeled > 0:
            with self.db._get_connection() as conn:
                # Count instances where model blocked but tests/user proved it was actually valid
                row = conn.execute("""
                    SELECT COUNT(*) FROM decisions d
                    JOIN outcomes o ON d.id = o.decision_id
                    WHERE d.module = 'stop_gate'
                      AND d.counterfactual_action = 'block'
                      AND o.label IN ('test_pass', 'user_approved', 'task_resolved')
                """).fetchone()
                false_blocks = row[0] if row else 0
                false_stop_rate = round(false_blocks / total_labeled, 4)

        next_mode = current_mode
        eligible = False
        reasons = []

        if current_mode == "shadow":
            target = PROMOTION_STANDARDS["shadow_to_advisory"]
            if total_labeled >= target["min_labeled"] and precision >= target["min_precision"] and ece <= target["max_ece"]:
                eligible = True
                next_mode = "advisory"
            else:
                reasons.append(f"Requires N>={target['min_labeled']} (current: {total_labeled}), "
                               f"Precision>={target['min_precision']} (current: {precision:.2f}), "
                               f"ECE<={target['max_ece']} (current: {ece:.2f})")

        elif current_mode == "advisory":
            target = PROMOTION_STANDARDS["advisory_to_confirm"]
            if total_labeled >= target["min_labeled"] and precision >= target["min_precision"] and ece <= target["max_ece"]:
                eligible = True
                next_mode = "confirm"
            else:
                reasons.append(f"Requires N>={target['min_labeled']} (current: {total_labeled}), "
                               f"Precision>={target['min_precision']} (current: {precision:.2f}), "
                               f"ECE<={target['max_ece']} (current: {ece:.2f})")

        elif current_mode == "confirm":
            target = PROMOTION_STANDARDS["confirm_to_enforce"]
            passes_fsr = (false_stop_rate <= target["max_false_stop_rate"]) if module == "stop_gate" else True
            if (total_labeled >= target["min_labeled"] and precision >= target["min_precision"]
                    and ece <= target["max_ece"] and passes_fsr):
                eligible = True
                next_mode = "enforce"
            else:
                reasons.append(f"Requires N>={target['min_labeled']} (current: {total_labeled}), "
                               f"Precision>={target['min_precision']} (current: {precision:.2f}), "
                               f"ECE<={target['max_ece']} (current: {ece:.2f}), "
                               f"False-Stop Rate<={target['max_false_stop_rate']} (current: {false_stop_rate:.2f})")

        return {
            "module": module,
            "current_mode": current_mode,
            "next_mode": next_mode,
            "eligible": eligible,
            "metrics": {
                "total_labeled": total_labeled,
                "precision": precision,
                "ece": ece,
                "false_stop_rate": false_stop_rate
            },
            "reasons": reasons
        }

    def check_and_promote(self, module: str) -> Dict[str, Any]:
        """Automatically promote the module if eligible."""

        eval_res = self.evaluate_promotion(module)
        if eval_res["eligible"]:
            new_mode = eval_res["next_mode"]
            self.set_mode(module, new_mode)
            eval_res["promoted"] = True
            eval_res["new_mode"] = new_mode
        else:
            eval_res["promoted"] = False
            eval_res["new_mode"] = eval_res["current_mode"]
        return eval_res

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get promotion status and metrics across all 4 gates."""
        return {mod: self.evaluate_promotion(mod) for mod in self._modes}
