"""
Unit tests for ARMA Decision Plane (DecisionEngine).
"""

import os
import tempfile
import unittest
from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine


class TestDecisionEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_engine.db")
        self.db = EvidenceDB(db_path=self.db_path)
        self.engine = DecisionEngine(evidence_db=self.db, default_mode="shadow")
        self.session_id = self.db.start_session("/test/repo", "test_harness", "Fix issue")
        self.event_id = self.db.record_event(self.session_id, 1, "test_event")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_risk_gate_deterministic_veto(self):
        # 1. Test in shadow mode: hard deny is recorded as counterfactual="block", but allow=True
        res = self.engine.evaluate_risk(
            session_id=self.session_id,
            event_id=self.event_id,
            command="rm -rf /"
        )
        self.assertEqual(res.counterfactual_action, "block")
        self.assertTrue(res.allow)  # in shadow mode

        # 2. Promote risk_gate to enforce mode
        self.engine.set_module_mode("risk_gate", "enforce")
        res_enforce = self.engine.evaluate_risk(
            session_id=self.session_id,
            event_id=self.event_id,
            command="git push --force origin main"
        )
        self.assertEqual(res_enforce.action_taken, "block")
        self.assertFalse(res_enforce.allow)
        self.assertIn("Deterministic Veto", res_enforce.reason)

    def test_stop_gate_deterministic_test_failure(self):
        # Promote to enforce mode
        self.engine.set_module_mode("stop_gate", "enforce")

        # Simulate agent attempting to stop when pytest had a non-zero exit code
        res = self.engine.evaluate_stop(
            session_id=self.session_id,
            event_id=self.event_id,
            task_text="Implement user login",
            test_results={"exit_code": 1, "output": "AssertionError: expected 200 got 401"}
        )
        self.assertFalse(res.allow)
        self.assertEqual(res.action_taken, "block")
        self.assertIn("Test suite failed with exit code 1", res.reason)

    def test_scope_gate_impact_set(self):
        self.engine.set_module_mode("scope_gate", "enforce")

        # File inside impact set
        res_in = self.engine.evaluate_scope(
            session_id=self.session_id,
            event_id=self.event_id,
            task_text="Refactor auth",
            target_file="src/auth.py",
            impact_set=["src/auth.py", "src/user.py"]
        )
        self.assertTrue(res_in.allow)

        # File outside impact set
        res_out = self.engine.evaluate_scope(
            session_id=self.session_id,
            event_id=self.event_id,
            task_text="Refactor auth",
            target_file="src/database/billing_migrations.py",
            impact_set=["src/auth.py", "src/user.py"]
        )
        self.assertFalse(res_out.allow)
        self.assertEqual(res_out.action_taken, "block")
        self.assertIn("outside Fullerenes impact set", res_out.reason)


if __name__ == "__main__":
    unittest.main()
