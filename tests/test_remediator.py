"""
Unit tests for ARMA Autonomous Self-Healing & Remediation Engine (layer/remediator.py).
"""

import os
import shutil
import tempfile
import unittest
from layer.remediator import CheckpointManager, LoopBreaker, AlternativeStrategySynthesizer
from layer.harness_hooks import ArmaHooks
from layer.evidence_db import EvidenceDB


class TestRemediator(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="arma_test_repo_")
        self.storage_dir = tempfile.mkdtemp(prefix="arma_test_ckpt_")
        self.db_path = os.path.join(self.test_dir, "test_evidence.db")
        self.db = EvidenceDB(db_path=self.db_path)

        # Create dummy source files
        self.file_a = os.path.join(self.test_dir, "module_a.py")
        self.file_b = os.path.join(self.test_dir, "module_b.py")

        with open(self.file_a, "w", encoding="utf-8") as f:
            f.write("def calculate():\n    return 42\n")

        with open(self.file_b, "w", encoding="utf-8") as f:
            f.write("def helper():\n    return 'clean'\n")

        self.ckpt_mgr = CheckpointManager(storage_dir=self.storage_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.storage_dir, ignore_errors=True)

    def test_checkpoint_creation_and_listing(self):
        ckpt_id = self.ckpt_mgr.create_checkpoint(
            session_id="sess_123",
            repo_path=self.test_dir,
            label="Initial Baseline",
            files=["module_a.py", "module_b.py"]
        )
        self.assertTrue(ckpt_id.startswith("ckpt_"))

        ckpts = self.ckpt_mgr.list_checkpoints(session_id="sess_123")
        self.assertEqual(len(ckpts), 1)
        self.assertEqual(ckpts[0]["checkpoint_id"], ckpt_id)
        self.assertEqual(ckpts[0]["label"], "Initial Baseline")
        self.assertEqual(ckpts[0]["file_count"], 2)

    def test_surgical_rollback_and_safety_stash(self):
        ckpt_id = self.ckpt_mgr.create_checkpoint(
            session_id="sess_test",
            repo_path=self.test_dir,
            label="Clean Working State",
            files=["module_a.py", "module_b.py"]
        )

        # Break module_a
        with open(self.file_a, "w", encoding="utf-8") as f:
            f.write("def calculate():\n    raise RuntimeError('thrashing syntax error')\n")

        # Modify module_b with unrelated valid work
        with open(self.file_b, "w", encoding="utf-8") as f:
            f.write("def helper():\n    return 'unrelated work'\n")

        # Perform surgical rollback ONLY on module_a
        success = self.ckpt_mgr.rollback(
            checkpoint_id=ckpt_id,
            target_files=["module_a.py"]
        )
        self.assertTrue(success)

        # Verify module_a is restored to clean state
        with open(self.file_a, "r", encoding="utf-8") as f:
            content_a = f.read()
        self.assertIn("return 42", content_a)

        # Verify module_b was NOT rolled back (surgical guarantee)
        with open(self.file_b, "r", encoding="utf-8") as f:
            content_b = f.read()
        self.assertIn("unrelated work", content_b)

        # Verify safety stash was created
        stash_files = os.listdir(self.ckpt_mgr.stash_dir)
        self.assertGreaterEqual(len(stash_files), 1)

    def test_alternative_strategy_synthesizer(self):
        pivot = AlternativeStrategySynthesizer.synthesize_pivot(
            thrashed_file="module_a.py",
            failure_count=3,
            checkpoint_label="Clean Baseline",
            task_text="Refactor calculation engine for precision",
            last_error="AssertionError: 42 != 0"
        )
        self.assertIn("EDIT-FAIL LOOP DETECTED", pivot)
        self.assertIn("module_a.py", pivot)
        self.assertIn("Clean Baseline", pivot)
        self.assertIn("AssertionError: 42 != 0", pivot)
        self.assertIn("Refactor calculation engine", pivot)

    def test_loop_breaker_thrashing_detection(self):
        loop_breaker = LoopBreaker(checkpoint_mgr=self.ckpt_mgr)
        ckpt_id = loop_breaker.record_green_state(
            session_id="sess_loop",
            repo_path=self.test_dir,
            label="Turn 1 Green"
        )

        # Break module_a
        with open(self.file_a, "w", encoding="utf-8") as f:
            f.write("def calculate():\n    return 0 # broken\n")

        actions = [
            {"tool": "replace_file_content", "args": {"TargetFile": "module_a.py"}},
            {"tool": "replace_file_content", "args": {"TargetFile": "module_a.py"}},
            {"tool": "replace_file_content", "args": {"TargetFile": "module_a.py"}},
        ]

        # Trigger loop evaluation with failing test status
        remediated, rolled_ckpt, pivot = loop_breaker.check_and_remediate(
            session_id="sess_loop",
            repo_path=self.test_dir,
            task_text="Fix calculate return value",
            recent_actions=actions,
            test_status="FAILED (exit code 1)",
            last_error="AssertionError: 0 != 42"
        )

        self.assertTrue(remediated)
        self.assertEqual(rolled_ckpt, ckpt_id)
        self.assertIsNotNone(pivot)
        self.assertIn("STRATEGIC PIVOT", pivot)

        # Verify file content was automatically restored
        with open(self.file_a, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("return 42", content)

    def test_arma_hooks_end_to_end_remediation(self):
        hooks = ArmaHooks(db=self.db, checkpoint_mgr=self.ckpt_mgr)
        session_id = hooks.on_session_start(
            repo_path=self.test_dir,
            harness="opencode",
            task_text="Enhance calculate function"
        )

        # Simulate turn 1 passing tests -> creates green checkpoint
        pass_output = "test_calc.py . [100%]\n1 passed in 0.05s"
        hooks.on_tool_output(session_id, "pytest", pass_output, exit_code=0)

        # Break file in repo
        with open(self.file_a, "w", encoding="utf-8") as f:
            f.write("def calculate():\n    return -1\n")

        # Turn 2 fails
        hooks.on_tool_output(session_id, "pytest", "FAILED test_calc: -1 != 42", exit_code=1)

        # Simulate 2 edit attempts
        hooks.on_pre_tool_use(session_id, "replace_file_content", {"TargetFile": "module_a.py"})
        hooks.on_pre_tool_use(session_id, "replace_file_content", {"TargetFile": "module_a.py"})

        # 3rd edit attempt triggers remediation
        res = hooks.on_pre_tool_use(session_id, "replace_file_content", {"TargetFile": "module_a.py"})

        # Verify decision gate result
        self.assertEqual(res.module, "loop_detector")
        self.assertEqual(res.counterfactual_action, "rollback")
        self.assertIn("Edit-fail loop broken", res.reason)

        # Verify pinned facts updated with pivot directive
        sess = hooks.active_sessions[session_id]
        pinned_facts = sess["pinned_facts"].format_pinned_facts()
        self.assertIn("CRITICAL INTERVENTION: EDIT-FAIL LOOP DETECTED", pinned_facts)
        self.assertIn("module_a.py", pinned_facts)

        # Verify file restored
        with open(self.file_a, "r", encoding="utf-8") as f:
            self.assertIn("return 42", f.read())

    def test_openhands_exact_loop_detectors(self):
        # 1. Identical Action-Observation
        pairs_loop = [("cat file.py", "contents")] * 4
        self.assertTrue(LoopBreaker.check_identical_action_obs(pairs_loop, threshold=4))
        self.assertFalse(LoopBreaker.check_identical_action_obs(pairs_loop[:3], threshold=4))

        # 2. Repeated Errors
        errs = ["ZeroDivisionError: division by zero"] * 3
        self.assertTrue(LoopBreaker.check_repeated_errors(errs, threshold=3))
        self.assertFalse(LoopBreaker.check_repeated_errors(errs[:2], threshold=3))

        # 3. Ping-Pong (A -> B -> A -> B for 6 cycles = 12 actions)
        ping_pong = ["act_A", "act_B"] * 6
        self.assertTrue(LoopBreaker.check_ping_pong(ping_pong, threshold=6))
        self.assertFalse(LoopBreaker.check_ping_pong(ping_pong[:10], threshold=6))

        # 4. Monologue (3 assistant messages without tools)
        monologue = ["ASSISTANT_TEXT: hello", "ASSISTANT_TEXT: thinking...", "ASSISTANT_TEXT: still thinking..."]
        self.assertTrue(LoopBreaker.check_monologue(monologue, threshold=3))
        self.assertFalse(LoopBreaker.check_monologue(monologue[:2], threshold=3))

        # 5. Exact loop pivot synthesis
        pivot = AlternativeStrategySynthesizer.synthesize_exact_loop_pivot(
            loop_type="Repeated Error",
            details="ZeroDivisionError occurred 3 times",
            suggested_action="Change denominator check"
        )
        self.assertIn("EXACT LOOP DETECTED - REPEATED ERROR", pivot)
        self.assertIn("Change denominator check", pivot)


if __name__ == "__main__":
    unittest.main()
