"""
ARMA Continuous Calibration Engine (layer/calibrator.py)
Provides statistical probability calibration (Temperature Scaling)
and decision threshold optimization to minimize Expected Calibration Error (ECE)
and False Alarm rates across all Decision Gates.
"""

import os
import json
import math
from typing import List, Dict, Any, Tuple, Optional
from layer.evidence_db import EvidenceDB


def sigmoid(z: float) -> float:
    """Numerically stable sigmoid function."""
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    else:
        exp_z = math.exp(z)
        return exp_z / (1.0 + exp_z)


def logit(p: float, eps: float = 1e-6) -> float:
    """Compute logit (inverse sigmoid) clamped for numerical stability."""
    p_clamped = max(eps, min(1.0 - eps, p))
    return math.log(p_clamped / (1.0 - p_clamped))


class TemperatureScaler:
    """
    Applies parametric Temperature & Platt Scaling:
    p_calibrated = sigmoid(logit(p) / T + bias)
    Preserves class rankings while correcting systematic bias and overconfidence.
    """

    @staticmethod
    def scale_probability(prob: float, temperature: float = 1.0, bias: float = 0.0) -> float:
        """Apply temperature and Platt scaling to a probability value."""
        if temperature <= 0:
            temperature = 1.0
        z = (logit(prob) / temperature) + bias
        return round(sigmoid(z), 4)

    @staticmethod
    def compute_ece(probs: List[float], labels: List[int], num_bins: int = 5) -> float:
        """Compute Expected Calibration Error (ECE) across M equal-width bins."""
        if not probs or len(probs) != len(labels):
            return 0.0

        n = len(probs)
        bin_limits = [i / num_bins for i in range(num_bins + 1)]
        ece = 0.0

        for i in range(num_bins):
            low, high = bin_limits[i], bin_limits[i + 1]
            bin_indices = [
                idx for idx, p in enumerate(probs)
                if (low <= p < high) or (i == num_bins - 1 and p == high)
            ]
            if not bin_indices:
                continue

            bin_conf = sum(probs[idx] for idx in bin_indices) / len(bin_indices)
            bin_acc = sum(labels[idx] for idx in bin_indices) / len(bin_indices)
            ece += (len(bin_indices) / n) * abs(bin_acc - bin_conf)

        return round(ece, 4)

    @staticmethod
    def compute_nll(probs: List[float], labels: List[int], eps: float = 1e-7) -> float:
        """Compute Negative Log-Likelihood (cross-entropy loss)."""
        if not probs:
            return 0.0
        loss = 0.0
        for p, y in zip(probs, labels):
            p_c = max(eps, min(1.0 - eps, p))
            loss -= (y * math.log(p_c) + (1 - y) * math.log(1.0 - p_c))
        return loss / len(probs)

    @classmethod
    def fit(cls, raw_probs: List[float], labels: List[int]) -> Tuple[float, float, float, float]:
        """
        Find optimal temperature T* and Platt bias b* that minimizes ECE.
        Returns (optimal_temperature, optimal_bias, initial_ece, calibrated_ece).
        """
        if len(raw_probs) < 5:
            return 1.0, 0.0, 0.0, 0.0

        initial_ece = cls.compute_ece(raw_probs, labels)

        best_t = 1.0
        best_b = 0.0
        best_score = float("inf")

        # 2D search over T in [0.2, 3.0] and bias in [-3.0, 3.0]
        t_values = [round(0.2 + i * 0.1, 2) for i in range(29)]
        b_values = [round(-3.0 + j * 0.1, 2) for j in range(61)]

        for t in t_values:
            for b in b_values:
                calibrated = [cls.scale_probability(p, t, b) for p in raw_probs]
                ece = cls.compute_ece(calibrated, labels)
                nll = cls.compute_nll(calibrated, labels)
                # Primary objective is minimizing ECE with light NLL regularization
                score = (ece * 3.0) + (nll * 0.1)

                if score < best_score:
                    best_score = score
                    best_t = t
                    best_b = b

        calibrated_final = [cls.scale_probability(p, best_t, best_b) for p in raw_probs]
        final_ece = cls.compute_ece(calibrated_final, labels)
        return best_t, best_b, initial_ece, final_ece


class ThresholdOptimizer:
    """
    Finds the optimal decision threshold tau* that maximizes F1 score
    subject to a maximum acceptable False Positive Rate (FPR) constraint.
    """

    @staticmethod
    def optimize(
        probs: List[float],
        labels: List[int],
        max_fpr: float = 0.04
    ) -> Tuple[float, float, float]:
        """
        Search decision thresholds tau in [0.1, 0.9].
        Returns (optimal_threshold, f1_score, empirical_fpr).
        """
        if not probs:
            return 0.5, 0.0, 0.0

        best_tau = 0.5
        best_f1 = -1.0
        best_fpr = 0.0

        for i in range(10, 91, 2):
            tau = i / 100.0
            tp = sum(1 for p, y in zip(probs, labels) if p >= tau and y == 1)
            fp = sum(1 for p, y in zip(probs, labels) if p >= tau and y == 0)
            fn = sum(1 for p, y in zip(probs, labels) if p < tau and y == 1)
            tn = sum(1 for p, y in zip(probs, labels) if p < tau and y == 0)

            fpr = fp / max(fp + tn, 1)
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            f1 = (2 * precision * recall) / max(precision + recall, 1e-6)

            # Enforce FPR constraint if achievable
            if fpr <= max_fpr:
                if f1 > best_f1:
                    best_f1 = f1
                    best_tau = tau
                    best_fpr = fpr
            elif best_f1 < 0:
                # If constraint cannot be strictly satisfied yet, minimize FPR
                best_tau = tau
                best_f1 = f1
                best_fpr = fpr

        return round(best_tau, 2), round(best_f1, 4), round(best_fpr, 4)


class CalibrationStore:
    """
    Persists and loads calibrated temperatures and thresholds
    to/from a local JSON configuration file.
    """

    DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "arma_calibration.json")

    @classmethod
    def save(cls, config: Dict[str, Any], path: Optional[str] = None):
        target = path or cls.DEFAULT_PATH
        with open(target, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    @classmethod
    def load(cls, path: Optional[str] = None) -> Dict[str, Any]:
        target = path or cls.DEFAULT_PATH
        if not os.path.exists(target):
            return {}
        try:
            with open(target, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


class OfflineCalibrator:
    """
    Queries historical labeled decisions from EvidenceDB,
    computes optimal temperatures and thresholds per module,
    and saves the configuration to CalibrationStore.
    """

    def __init__(self, db: Optional[EvidenceDB] = None):
        self.db = db or EvidenceDB()

    def optimize_all_modules(self, save: bool = True) -> Dict[str, Any]:
        """Runs optimization across stop_gate, scope_gate, risk_gate, loop_detector."""
        modules = ["stop_gate", "scope_gate", "risk_gate", "loop_detector"]
        results = {}

        for mod in modules:
            res = self.optimize_module(mod)
            results[mod] = res

        if save:
            CalibrationStore.save(results)

        return results

    def optimize_module(self, module_name: str) -> Dict[str, Any]:
        """Optimize temperature and threshold for a single gate module."""
        query = """
            SELECT d.probability, o.label
            FROM decisions d
            JOIN outcomes o ON d.id = o.decision_id
            WHERE d.module = ? AND d.probability IS NOT NULL
        """
        with self.db._get_connection() as conn:
            rows = conn.execute(query, (module_name,)).fetchall()

        if len(rows) < 3:
            return {
                "module": module_name,
                "samples": len(rows),
                "temperature": 1.0,
                "threshold": 0.5,
                "initial_ece": 0.0,
                "calibrated_ece": 0.0,
                "status": "INSUFFICIENT_DATA"
            }

        probs = [float(r["probability"]) for r in rows]
        labels = [1 if r["label"] in ("test_pass", "user_approved", "diff_survived", "task_resolved") else 0 for r in rows]

        # 1. Fit Temperature & Platt Bias
        opt_t, opt_b, init_ece, cal_ece = TemperatureScaler.fit(probs, labels)

        # 2. Scale probabilities
        calibrated_probs = [TemperatureScaler.scale_probability(p, opt_t, opt_b) for p in probs]

        # 3. Fit Optimal Threshold
        opt_tau, f1, fpr = ThresholdOptimizer.optimize(calibrated_probs, labels)

        return {
            "module": module_name,
            "samples": len(rows),
            "temperature": opt_t,
            "bias": opt_b,
            "threshold": opt_tau,
            "initial_ece": init_ece,
            "calibrated_ece": cal_ece,
            "f1_score": f1,
            "empirical_fpr": fpr,
            "status": "CALIBRATED"
        }
