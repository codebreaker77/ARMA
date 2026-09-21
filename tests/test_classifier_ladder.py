"""
Unit tests for ARMA Classifier Backend Ladder (layer/classifier_ladder.py).
"""

import unittest
from layer.embed_prior import Noul, Choice, Score, EmbedPrior
from layer.classifier_ladder import (
    RuleClassifier,
    SupervisedEmbedClassifier,
    ClassifierLadder
)


class TestClassifierLadder(unittest.TestCase):

    def test_embed_prior_state_serialization(self):
        prior = EmbedPrior(max_chars=200)
        state = {
            "task": "Refactor authentication flow",
            "action": "replace_file_content",
            "target": "src/auth/jwt.py",
            "extra_details": "x" * 500  # very long string
        }
        serialized = prior._serialize_state(state)
        # Action and Target must be at the very front
        self.assertTrue(serialized.startswith("action:") or serialized.startswith("target:"))
        # Must not exceed max_chars
        self.assertLessEqual(len(serialized), 200)

    def test_embed_prior_graceful_fallback(self):
        # Connect to non-existent port to test error handling
        unreachable = EmbedPrior(ollama_url="http://localhost:59999", request_timeout=0.2)
        q = {"is_valid": Noul("Is this code change valid?")}
        res = unreachable.system_one({"action": "edit"}, q)

        # Must not crash with RuntimeError!
        self.assertIn("is_valid", res.answers)
        ans = res.answers["is_valid"]
        self.assertEqual(ans.status, "backend_error")
        self.assertEqual(ans.probability, 0.5)

    def test_rule_classifier_rung0(self):
        rules = RuleClassifier()
        # Hard deny command
        res = rules.evaluate(
            {"command": "rm -rf /"},
            {"risk_gate": Choice("Risk level", {"read_only": "safe", "destructive": "harmful"})}
        )
        self.assertEqual(res.answers["risk_gate"].selected_option, "destructive")
        self.assertEqual(res.answers["risk_gate"].confidence, 1.0)
        self.assertEqual(res.answers["risk_gate"].status, "rule_exact")

        # Failing test exit code
        res_stop = rules.evaluate(
            {"test_results": {"exit_code": 1, "output": "FAILED"}},
            {"stop_gate": Choice("Stop status", {"done": "finished", "needs_verification": "failing"})}
        )
        self.assertEqual(res_stop.answers["stop_gate"].selected_option, "needs_verification")

    def test_supervised_embed_classifier_discrimination(self):
        clf = SupervisedEmbedClassifier()
        q = {"is_file_in_scope": Noul("The edit is needed for the stated task")}
        task = "Fix off-by-one in pagination"

        pos_state = {"task": task, "edit": "src/pagination.py: change range(n) to range(n+1)"}
        neg_state = {"task": task, "edit": ".github/workflows/deploy.yml: add prod push step"}

        p_pos = clf.evaluate(pos_state, q).answers["is_file_in_scope"].probability
        p_neg = clf.evaluate(neg_state, q).answers["is_file_in_scope"].probability

        # Positive probability must be significantly higher than negative
        self.assertGreater(p_pos, 0.70)
        self.assertLess(p_neg, 0.30)
        # Wide probability spread (not compressed around 0.50)
        self.assertGreater(p_pos - p_neg, 0.50)

    def test_classifier_ladder_cascading(self):
        ladder = ClassifierLadder()

        # 1. Exact rule matches directly
        rule_res = ladder.evaluate(
            {"command": "git push --force origin main"},
            {"risk_gate": Choice("Risk", {"read_only": "safe", "destructive": "hard deny"})}
        )
        self.assertEqual(rule_res.answers["risk_gate"].selected_option, "destructive")
        self.assertEqual(rule_res.answers["risk_gate"].status, "rule_exact")

        # 2. Fuzzy question falls through to supervised head
        task = "Optimize SQL queries for dashboard"
        fuzzy_res = ladder.evaluate(
            {"task": task, "target": "src/db/queries.py"},
            {"is_file_in_scope": Noul("The edit is needed for the stated task")}
        )
        self.assertEqual(fuzzy_res.answers["is_file_in_scope"].status, "ok")
        self.assertGreater(fuzzy_res.answers["is_file_in_scope"].probability, 0.60)


if __name__ == "__main__":
    unittest.main()
