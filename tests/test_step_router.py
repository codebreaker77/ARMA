"""
Unit tests for ARMA CacheAwareStepRouter (layer/step_router.py).
"""

import unittest
from layer.step_router import CacheAwareStepRouter, StepTier, StepCategory


class TestStepRouter(unittest.TestCase):

    def setUp(self):
        self.router = CacheAwareStepRouter()

    def test_intent_classification(self):
        # Trivial read
        cat = self.router.classify_intent("view_file", {"path": "src/models.py"})
        self.assertEqual(cat, StepCategory.TRIVIAL_READ)

        cat_bash = self.router.classify_intent("bash", {"command": "cat app/utils.py"})
        self.assertEqual(cat_bash, StepCategory.TRIVIAL_READ)

        # Test execution
        cat_test = self.router.classify_intent("bash", {"command": "pytest tests/test_core.py"})
        self.assertEqual(cat_test, StepCategory.TEST_VERIFICATION)

        # Code modification
        cat_mod = self.router.classify_intent("replace_file_content", {"TargetFile": "src/app.py"})
        self.assertEqual(cat_mod, StepCategory.CODE_MODIFICATION)

        # Planning
        cat_plan = self.router.classify_intent("", {})
        self.assertEqual(cat_plan, StepCategory.PLANNING_REASONING)

    def test_cache_hysteresis_cold_start(self):
        # On cold start (no warm frontier cache), trivial read routes to cheap model
        decision = self.router.route_step("view_file", {"path": "README.md"})
        self.assertEqual(decision.tier, StepTier.CHEAP)
        self.assertEqual(decision.category, StepCategory.TRIVIAL_READ)

    def test_cache_hysteresis_warm_cache_guard(self):
        # First execute a modification (warms frontier cache)
        d1 = self.router.route_step("replace_file_content", {"TargetFile": "src/core.py"})
        self.assertEqual(d1.tier, StepTier.FRONTIER)
        self.assertTrue(self.router.is_frontier_cache_warm)

        # 1st isolated read: Cache Hysteresis Guard should keep it on FRONTIER to avoid $3.45/M cache write penalty!
        d2 = self.router.route_step("view_file", {"path": "src/core.py"})
        self.assertEqual(d2.tier, StepTier.FRONTIER)
        self.assertIn("Cache Hysteresis Guard", d2.reason)

        # 2nd read: still guarded
        d3 = self.router.route_step("view_file", {"path": "src/core.py"})
        self.assertEqual(d3.tier, StepTier.FRONTIER)

        # 3rd read: still guarded
        d4 = self.router.route_step("view_file", {"path": "src/core.py"})
        self.assertEqual(d4.tier, StepTier.FRONTIER)

        # 4th consecutive read: now batched enough to justify switching to cheap tier!
        d5 = self.router.route_step("view_file", {"path": "src/core.py"})
        self.assertEqual(d5.tier, StepTier.CHEAP)
        self.assertIn("offsets cache invalidation penalty", d5.reason)
