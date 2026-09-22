"""Unit tests for the MutantEngine."""

import pytest
from layer.mutant_engine import MutantEngine

SOURCE_CODE = """def calculate_discount(price, is_member):
    if is_member:
        if price >= 100:
            return price * 0.2
        return price * 0.1
    return 0
"""

DIFF_SAMPLE = """diff --git a/src/shop.py b/src/shop.py
--- a/src/shop.py
+++ b/src/shop.py
@@ -1,5 +1,6 @@
 def calculate_discount(price, is_member):
+    if is_member:
+        if price >= 100:
+            return price * 0.2
"""

def test_generate_mutants_unconstrained():
    engine = MutantEngine(max_mutants_budget=5)
    mutants = engine.generate_mutants_for_source(SOURCE_CODE, "src/shop.py")
    assert len(mutants) > 0
    assert len(mutants) <= 5
    m_types = [m.mutation_type for m in mutants]
    assert any(t in ("NEGATE_CONDITION", "INVERT_COMPARATOR", "RETURN_NONE") for t in m_types)

def test_generate_mutants_targeted_lines():
    engine = MutantEngine(max_mutants_budget=3)
    # Only line 3: "if price >= 100:"
    mutants = engine.generate_mutants_for_source(SOURCE_CODE, "src/shop.py", target_lines=[3])
    assert len(mutants) >= 1
    for m in mutants:
        assert m.line_number == 3
        assert m.mutation_type in ("INVERT_COMPARATOR", "NEGATE_CONDITION", "OFF_BY_ONE")

def test_diff_line_extractor():
    engine = MutantEngine()
    lines_map = engine.extract_modified_lines_by_file(DIFF_SAMPLE)
    assert "src/shop.py" in lines_map
    assert 2 in lines_map["src/shop.py"]
    assert 3 in lines_map["src/shop.py"]
