"""
Unit tests for ARMA Context Plane (layer/context_plane.py).
"""

import unittest
from layer.context_plane import ToolOutputPruner, PinnedFactsManager, CompactionScorer


class TestContextPlane(unittest.TestCase):

    def test_tool_output_pruner_short(self):
        short_text = "All 5 tests passed successfully."
        pruned = ToolOutputPruner.prune(short_text, max_chars=1200)
        self.assertEqual(pruned, short_text)

    def test_tool_output_pruner_test_failures(self):
        # Generate 200 lines of pytest output
        lines = ["pytest version 7.4.0"]
        for i in range(150):
            lines.append(f"tests/test_module_{i}.py . [ {i}%]")
        lines.append("=" * 20 + " FAILURES " + "=" * 20)
        lines.append("____ test_auth_token ____")
        lines.append("    def test_auth_token():")
        lines.append(">       assert token.is_valid() == True")
        lines.append("E       AssertionError: assert False == True")
        lines.append("tests/test_auth.py:45: AssertionError")
        lines.append("=" * 20 + " short test summary info " + "=" * 20)
        lines.append("FAILED tests/test_auth.py::test_auth_token - AssertionError: assert False == True")
        lines.append("= 1 failed, 150 passed in 4.23s =")

        raw_output = "\n".join(lines)
        pruned = ToolOutputPruner.prune(raw_output)

        self.assertIn("[ARMA PRUNED TEST LOG", pruned)
        self.assertIn("AssertionError", pruned)
        self.assertIn("FAILED tests/test_auth.py::test_auth_token", pruned)
        # Verify significant compression
        self.assertLess(len(pruned), len(raw_output) * 0.4)

    def test_tool_output_pruner_compiler_errors(self):
        lines = [
            "Building target 'arma_core'...",
            "Compiling src/engine.cpp...",
            "src/engine.cpp:42:10: error: 'Noul' is not a member of 'Jev'",
            "   42 |     Jev::Noul decision;",
            "      |          ^~~~",
            "src/engine.cpp:88:5: warning: unused variable 'flags'",
            "Build failed with 1 error, 1 warning."
        ]
        raw_output = "\n".join(lines * 10)  # make it large
        pruned = ToolOutputPruner.prune(raw_output, max_chars=100)

        self.assertIn("[ARMA PRUNED COMPILER ERRORS]", pruned)
        self.assertIn("error: 'Noul' is not a member of 'Jev'", pruned)

    def test_pinned_facts_manager(self):
        manager = PinnedFactsManager(task_checklist=[
            "Resolve foreign key constraint in SQLite",
            "Maintain test exit code invariant"
        ])
        manager.record_file_touched("layer/evidence_db.py")
        manager.update_test_status(passed=True, exit_code=0)
        manager.set_impact_set({"layer/evidence_db.py", "layer/decision_engine.py"})

        formatted = manager.format_pinned_facts()
        self.assertIn("ARMA PINNED FACTS", formatted)
        self.assertIn("PASSED (exit code 0)", formatted)
        self.assertIn("layer/evidence_db.py", formatted)
        self.assertIn("Resolve foreign key constraint", formatted)
        self.assertIn("2 files permitted", formatted)

        # Test message injection
        messages = [
            {"role": "system", "content": "You are a senior coding assistant."},
            {"role": "user", "content": "Fix the database schema."}
        ]
        injected = manager.inject_into_messages(messages)
        self.assertEqual(len(injected), 2)
        self.assertIn("ARMA PINNED FACTS", injected[-1]["content"])
        self.assertTrue(injected[-1]["content"].startswith("Fix the database schema."))

    def test_compaction_scorer(self):
        # User message: critical
        self.assertEqual(CompactionScorer.score_turn(role="user", content="hello"), 5)

        # Test failure: high
        self.assertEqual(
            CompactionScorer.score_turn(role="assistant", content="AssertionError: Expected 1 got 2"),
            4
        )

        # File write: high
        self.assertEqual(
            CompactionScorer.score_turn(role="assistant", content="Updated file content", tool_name="write_to_file"),
            4
        )

        # File read: medium
        self.assertEqual(
            CompactionScorer.score_turn(role="assistant", content="class CodeGraph: ...", tool_name="view_file"),
            3
        )

        # Low importance / disposable
        self.assertEqual(
            CompactionScorer.score_turn(role="assistant", content="file1\nfile2\nfile3", tool_name="list_dir"),
            1
        )


if __name__ == "__main__":
    unittest.main()
