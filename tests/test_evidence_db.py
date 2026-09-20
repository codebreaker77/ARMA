"""
Unit tests for ARMA Evidence Plane (EvidenceDB).
"""

import os
import tempfile
import unittest
from layer.evidence_db import EvidenceDB


class TestEvidenceDB(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_evidence.db")
        self.db = EvidenceDB(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_session_lifecycle(self):
        sess_id = self.db.start_session(
            repo_path="/test/repo",
            harness="test_harness",
            task_text="Fix issue #123"
        )
        self.assertIsNotNone(sess_id)

        # Record event
        event_id = self.db.record_event(
            session_id=sess_id,
            turn=1,
            kind="stop_requested",
            raw_payload_summary="Test summary"
        )
        self.assertIsNotNone(event_id)

        # Record decision
        dec_id = self.db.record_decision(
            event_id=event_id,
            module="stop_gate",
            question_type="noul",
            question_text="is_complete",
            answer_raw="True",
            probability=0.88,
            confidence=0.88,
            backend="test_backend",
            model_version="1.0",
            threshold=0.7,
            mode="shadow",
            action_taken="pass",
            counterfactual_action="pass"
        )
        self.assertIsNotNone(dec_id)

        # Record outcome
        out_id = self.db.record_outcome(
            decision_id=dec_id,
            label="test_pass",
            source="pytest"
        )
        self.assertIsNotNone(out_id)

        # Verify recent decisions
        recent = self.db.get_recent_decisions(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["module"], "stop_gate")
        self.assertEqual(recent[0]["action_taken"], "pass")

        # End session
        self.db.end_session(sess_id, final_status="resolved")

    def test_calibration_calculation(self):
        sess_id = self.db.start_session("/repo", "test", "task")
        event_id = self.db.record_event(sess_id, 1, "action")

        # Insert 4 decisions with outcomes
        d1 = self.db.record_decision(event_id, "stop_gate", "noul", "q", "true", 0.90, 0.90, "b", "v", 0.7, "shadow", "pass", "pass")
        self.db.record_outcome(d1, "test_pass", "pytest")

        d2 = self.db.record_decision(event_id, "stop_gate", "noul", "q", "true", 0.85, 0.85, "b", "v", 0.7, "shadow", "pass", "pass")
        self.db.record_outcome(d2, "test_pass", "pytest")

        d3 = self.db.record_decision(event_id, "stop_gate", "noul", "q", "false", 0.20, 0.20, "b", "v", 0.7, "shadow", "pass", "block")
        self.db.record_outcome(d3, "test_fail", "pytest")

        metrics = self.db.calculate_calibration_metrics(module="stop_gate")
        self.assertEqual(metrics["total_labeled"], 3)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
