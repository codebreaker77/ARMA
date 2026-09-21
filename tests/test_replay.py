"""
Unit tests for ARMA Phase 3: Replay, Calibration, and Distillation Exporter.
"""

import os
import tempfile
import json
import unittest

from layer.evidence_db import EvidenceDB
from layer.calibrator import TemperatureScaler, ThresholdOptimizer, CalibrationStore
from layer.replay_engine import ReplayEngine, ReplaySummary
from layer.distill_exporter import DistillExporter


class TestPhase3ReplayAndCalibration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_evidence.db")
        self.db = EvidenceDB(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_temperature_scaler_mechanics(self):
        # T = 1.0: Probability is unchanged
        p = 0.80
        p_scaled = TemperatureScaler.scale_probability(p, temperature=1.0)
        self.assertAlmostEqual(p_scaled, 0.80, places=2)

        # T = 2.0: Softens probability towards 0.5 (anti-overconfidence)
        p_soft = TemperatureScaler.scale_probability(p, temperature=2.0)
        self.assertLess(p_soft, p)
        self.assertGreater(p_soft, 0.5)

        # T = 0.5: Sharpens probability away from 0.5
        p_sharp = TemperatureScaler.scale_probability(p, temperature=0.5)
        self.assertGreater(p_sharp, p)

    def test_temperature_scaler_fit(self):
        # Overconfident probabilities: model outputs 0.95 or 0.05, but actual accuracy is only 70%
        raw_probs = [0.95] * 14 + [0.05] * 6
        labels = [1] * 10 + [0] * 4 + [0] * 5 + [1] * 1

        best_t, best_b, init_ece, cal_ece = TemperatureScaler.fit(raw_probs, labels)
        self.assertGreater(best_t, 1.0)  # Temperature should increase to soften overconfidence
        self.assertLessEqual(cal_ece, init_ece)

    def test_threshold_optimizer(self):
        probs = [0.1, 0.2, 0.45, 0.65, 0.85, 0.92]
        labels = [0, 0, 0, 1, 1, 1]

        opt_tau, f1, fpr = ThresholdOptimizer.optimize(probs, labels, max_fpr=0.04)
        self.assertGreaterEqual(opt_tau, 0.45)
        self.assertGreater(f1, 0.9)
        self.assertLessEqual(fpr, 0.04)

    def test_calibration_store_roundtrip(self):
        cal_path = os.path.join(self.temp_dir.name, "test_cal.json")
        sample_config = {
            "stop_gate": {"temperature": 1.45, "threshold": 0.72},
            "scope_gate": {"temperature": 0.95, "threshold": 0.55}
        }
        CalibrationStore.save(sample_config, path=cal_path)
        loaded = CalibrationStore.load(path=cal_path)
        self.assertEqual(loaded["stop_gate"]["temperature"], 1.45)
        self.assertEqual(loaded["stop_gate"]["threshold"], 0.72)

    def test_replay_engine_simulation(self):
        # Create a mock session with 2 events and decisions
        sess_id = self.db.start_session("/repo", "test_harness", "Fix token expiry")
        e1 = self.db.record_event(sess_id, turn=1, kind="stop_requested")
        d1 = self.db.record_decision(
            event_id=e1,
            module="stop_gate",
            question_type="noul",
            question_text="satisfies requirements",
            answer_raw="done",
            probability=0.55,  # borderline pass under default 0.50 threshold
            confidence=0.8,
            backend="micro_jev",
            model_version="1.0",
            threshold=0.50,
            mode="shadow",
            action_taken="pass",  # baseline let it pass
            counterfactual_action="pass"
        )
        # But ground truth was actually test failure (premature stop!)
        self.db.record_outcome(decision_id=d1, label="test_fail", source="pytest")

        engine = ReplayEngine(db=self.db)
        # Candidate policy raises threshold to 0.70
        candidate_config = {
            "stop_gate": {"temperature": 1.0, "threshold": 0.70}
        }

        summary = engine.replay_session(sess_id, candidate_config=candidate_config)
        self.assertEqual(summary.total_replayed, 1)
        self.assertEqual(summary.original_accuracy, 0.0)  # Original failed to catch premature stop
        self.assertEqual(summary.candidate_accuracy, 1.0)  # Candidate threshold 0.70 caught it!
        self.assertEqual(summary.counterfactual_lift, 1.0)
        self.assertEqual(summary.net_false_alarms_eliminated, 1)

    def test_distill_exporter_triplets_and_alpaca(self):
        sess_id = self.db.start_session("/repo", "test_harness", "Add retry logic")
        e1 = self.db.record_event(sess_id, turn=1, kind="pre_tool_use", raw_payload_summary="requests/adapters.py")
        d1 = self.db.record_decision(
            event_id=e1,
            module="scope_gate",
            question_type="noul",
            question_text="is_file_in_scope",
            answer_raw="yes",
            probability=0.88,
            confidence=0.9,
            backend="micro_jev",
            model_version="1.0",
            threshold=0.5,
            mode="shadow",
            action_taken="pass",
            counterfactual_action="pass"
        )
        self.db.record_outcome(decision_id=d1, label="test_pass", source="pytest")

        exporter = DistillExporter(db=self.db)
        triplets_path = os.path.join(self.temp_dir.name, "triplets.jsonl")
        count_triplets = exporter.export_contrastive_triplets(output_path=triplets_path)
        self.assertEqual(count_triplets, 1)

        with open(triplets_path, "r", encoding="utf-8") as f:
            line = json.loads(f.readline())
            self.assertIn("anchor", line)
            self.assertIn("positive", line)
            self.assertIn("negative", line)
            self.assertEqual(line["module"], "scope_gate")

        alpaca_path = os.path.join(self.temp_dir.name, "alpaca.jsonl")
        count_alpaca = exporter.export_instruction_tuning(output_path=alpaca_path, format_type="alpaca")
        self.assertEqual(count_alpaca, 1)

        with open(alpaca_path, "r", encoding="utf-8") as f:
            line = json.loads(f.readline())
            self.assertIn("instruction", line)
            self.assertIn("input", line)
            self.assertIn("output", line)


if __name__ == "__main__":
    unittest.main()
