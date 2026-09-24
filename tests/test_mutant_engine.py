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


def test_semantic_mutation_operators():
    code = """def process(x, flag):
    if not flag:
        raise ValueError("Invalid flag")
    total = x + 10
    return {"result": total}
"""
    engine = MutantEngine(max_mutants_budget=10)
    mutants = engine.generate_mutants_for_source(code, "test.py")
    m_types = [m.mutation_type for m in mutants]

    # Verify semantic operators were detected and generated
    assert "STRIP_NOT" in m_types
    assert "REMOVE_RAISE" in m_types
    assert "BIN_OP_SWAP" in m_types
    assert "RETURN_EMPTY_DICT" in m_types

    # Verify REMOVE_RAISE replaced raise with pass
    raise_mutant = next(m for m in mutants if m.mutation_type == "REMOVE_RAISE")
    assert "pass" in raise_mutant.mutated_code
    assert "raise ValueError" not in raise_mutant.mutated_snippet or "pass" in raise_mutant.mutated_snippet

    # Verify BIN_OP_SWAP replaced + with -
    binop_mutant = next(m for m in mutants if m.mutation_type == "BIN_OP_SWAP")
    assert "-" in binop_mutant.mutated_snippet

