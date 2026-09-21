"""
Unit tests for ARMA Harness Runner (layer/runner.py).
"""

import sys
import tempfile
import unittest
from layer.evidence_db import EvidenceDB
from layer.runner import HarnessRunner


class TestHarnessRunner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = EvidenceDB(db_path=f"{self.temp_dir.name}/test_runner.db")
        # Use an alternate port so it doesn't conflict with any active proxy
        self.runner = HarnessRunner(port=4048, db=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_runner_execution_and_summary(self):
        cmd = [sys.executable, "-c", "print('hello from arma harness test')"]
        exit_code = self.runner.run(command=cmd, repo_path=self.temp_dir.name)
        self.assertEqual(exit_code, 0)

        # Verify session was recorded in EvidenceDB
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT harness, final_status FROM sessions ORDER BY started_at DESC LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["final_status"], "resolved")


if __name__ == "__main__":
    unittest.main()
