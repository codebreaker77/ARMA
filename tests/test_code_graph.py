"""
Unit tests for ARMA Code Graph Engine (layer/code_graph.py).
"""

import os
import tempfile
import unittest
from layer.code_graph import CodeGraph


class TestCodeGraph(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name

        # Create a mock repository layout:
        # a.py -> imports b.py
        # b.py -> imports c.py
        # test_a.py -> imports a.py
        # unrelated.py -> standalone
        os.makedirs(os.path.join(self.root, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "tests"), exist_ok=True)

        with open(os.path.join(self.root, "src", "c.py"), "w") as f:
            f.write("def helper_func():\n    return 42\n")

        with open(os.path.join(self.root, "src", "b.py"), "w") as f:
            f.write("from src import c\ndef intermediate():\n    return c.helper_func()\n")

        with open(os.path.join(self.root, "src", "a.py"), "w") as f:
            f.write("from src import b\ndef main_app():\n    return b.intermediate()\n")

        with open(os.path.join(self.root, "tests", "test_a.py"), "w") as f:
            f.write("from src import a\ndef test_app():\n    assert a.main_app() == 42\n")

        with open(os.path.join(self.root, "src", "unrelated.py"), "w") as f:
            f.write("def billing():\n    pass\n")

        self.graph = CodeGraph(root_dir=self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_graph_indexing(self):
        self.assertIn("src/a.py", self.graph.indexed_files)
        self.assertIn("src/b.py", self.graph.indexed_files)
        self.assertIn("src/c.py", self.graph.indexed_files)
        self.assertIn("tests/test_a.py", self.graph.indexed_files)

        # Check symbols
        self.assertIn("main_app", self.graph.file_symbols.get("src/a.py", set()))
        self.assertIn("helper_func", self.graph.file_symbols.get("src/c.py", set()))

    def test_predict_impact_transitive_closure(self):
        # Modifying c.py should impact: c.py -> b.py -> a.py -> test_a.py
        impact = self.graph.predict_impact("src/c.py")
        self.assertIn("src/c.py", impact)
        # Unrelated file must NOT be in the blast radius
        self.assertNotIn("src/unrelated.py", impact)

    def test_symbol_lookup(self):
        candidates = self.graph.find_relevant_symbols("helper_func", top_k=5)
        self.assertTrue(any(sym == "helper_func" for _, sym in candidates))


if __name__ == "__main__":
    unittest.main()
