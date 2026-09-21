"""
Unit tests for ARMA SpeculativeActionEngine (layer/speculative_runner.py).
"""

import os
import unittest
import tempfile
from layer.speculative_runner import SpeculativeActionEngine


class TestSpeculativeRunner(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.engine = SpeculativeActionEngine(repo_path=self.temp_dir)

    def test_extract_traceback_targets_ordering(self):
        sample_traceback = """
Traceback (most recent call last):
  File "/usr/local/lib/python3.9/site-packages/pytest/runner.py", line 120, in pytest_runtest_protocol
    res = call_runtest_hook(item, nextitem)
  File "django/core/handlers/base.py", line 181, in _get_response
    response = wrapped_callback(request, *callback_args, **callback_kwargs)
  File "django/contrib/auth/models.py", line 45, in check_password
    assert is_valid == True
AssertionError: assert False == True
        """
        targets = SpeculativeActionEngine.extract_traceback_targets(sample_traceback)

        # Bottom-most frame (auth/models.py) must be Top-1
        self.assertGreaterEqual(len(targets), 2)
        self.assertIn("django/contrib/auth/models.py", targets[0])
        self.assertIn("django/core/handlers/base.py", targets[1])
        # Site-packages should be filtered out
        for t in targets:
            self.assertNotIn("site-packages", t)

    def test_pre_fetch_and_lossless_commit(self):
        # Create a sample file
        test_file = os.path.join(self.temp_dir, "models.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("class UserAccount:\n    pass\n")

        # Speculate on it
        self.engine.pre_fetch(["models.py"])

        # Matching tool call commits pre-fetched content
        committed = self.engine.match_and_commit(
            tool_name="view_file",
            tool_args={"path": "models.py"}
        )
        self.assertIsNotNone(committed)
        self.assertIn("class UserAccount:", committed)

        # Subsequent call finds empty cache (cache cleared after turn)
        second_call = self.engine.match_and_commit(
            tool_name="view_file",
            tool_args={"path": "models.py"}
        )
        self.assertIsNone(second_call)

    def test_unmatched_action_discards_silently(self):
        test_file = os.path.join(self.temp_dir, "utils.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("def helper(): return True\n")

        self.engine.pre_fetch(["utils.py"])

        # Agent does something else (e.g. edits another file)
        result = self.engine.match_and_commit(
            tool_name="replace_file_content",
            tool_args={"TargetFile": "unrelated.py"}
        )
        self.assertIsNone(result)
