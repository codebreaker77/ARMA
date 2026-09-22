"""Tests for live mutation probe runner in VerificationAdequacyGate."""

import os
import sys
import tempfile
import pytest

from layer.verification_gate import VerificationAdequacyGate


def test_live_mutation_probe_kills_mutants_and_passes():
    """Verify that effective tests kill AST mutants and the gate passes."""
    gate = VerificationAdequacyGate(min_mutation_kill_ratio=0.50, mutant_budget=3)

    with tempfile.TemporaryDirectory() as tmpdir:
        calc_path = os.path.join(tmpdir, "calc.py")
        test_path = os.path.join(tmpdir, "test_calc.py")

        with open(calc_path, "w", encoding="utf-8") as f:
            f.write(
                "def compute(x: int) -> int:\n"
                "    if x > 10:\n"
                "        return x * 2\n"
                "    return x + 1\n"
            )

        with open(test_path, "w", encoding="utf-8") as f:
            f.write(
                "from calc import compute\n"
                "def test_compute():\n"
                "    assert compute(15) == 30\n"
                "    assert compute(5) == 6\n"
            )

        diff = (
            "diff --git a/calc.py b/calc.py\n"
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -2,3 +2,3 @@\n"
            "+    if x > 10:\n"
            "+        return x * 2\n"
            "+    return x + 1\n"
        )

        test_cmd = f'"{sys.executable}" -m pytest test_calc.py'
        outcome = gate.verify_repository(
            repo_path=tmpdir,
            patch_text=diff,
            test_command=test_cmd,
            timeout_seconds=10
        )

        assert outcome.allow is True
        assert outcome.stage == "verified"
        assert outcome.mutation_result is not None
        assert outcome.mutation_result.mutants_killed > 0
        assert outcome.mutation_result.kill_ratio >= 0.50

        # Verify atomic restoration: calc.py must be unchanged on disk
        with open(calc_path, "r", encoding="utf-8") as f:
            final_src = f.read()
        assert "if x > 10:" in final_src
        assert "return x * 2" in final_src


def test_live_mutation_probe_blocks_hollow_tests():
    """Verify that tests which pass on mutated code (placebo tests) are blocked."""
    gate = VerificationAdequacyGate(min_mutation_kill_ratio=0.50, mutant_budget=3)

    with tempfile.TemporaryDirectory() as tmpdir:
        calc_path = os.path.join(tmpdir, "calc.py")
        test_path = os.path.join(tmpdir, "test_calc.py")

        with open(calc_path, "w", encoding="utf-8") as f:
            f.write(
                "def compute(x: int) -> int:\n"
                "    if x > 10:\n"
                "        return x * 2\n"
                "    return x + 1\n"
            )

        # Placebo test that doesn't assert anything about the return value
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(
                "from calc import compute\n"
                "def test_compute():\n"
                "    compute(15)\n"
                "    assert True\n"
            )

        diff = (
            "diff --git a/calc.py b/calc.py\n"
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -2,3 +2,3 @@\n"
            "+    if x > 10:\n"
            "+        return x * 2\n"
            "+    return x + 1\n"
        )

        test_cmd = f'"{sys.executable}" -m pytest test_calc.py'
        outcome = gate.verify_repository(
            repo_path=tmpdir,
            patch_text=diff,
            test_command=test_cmd,
            timeout_seconds=10
        )

        assert outcome.allow is False
        assert outcome.stage == "mutation_probe"
        assert "Verification Inadequate" in outcome.reason
        assert outcome.mutation_result.kill_ratio < 0.50

        # Verify atomic restoration
        with open(calc_path, "r", encoding="utf-8") as f:
            final_src = f.read()
        assert "if x > 10:" in final_src


def test_live_mutation_probe_blocks_test_tampering():
    """Verify that test-diff tampering is immediately vetoed before mutation probes run."""
    gate = VerificationAdequacyGate()

    with tempfile.TemporaryDirectory() as tmpdir:
        diff = (
            "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
            "--- a/tests/test_foo.py\n"
            "+++ b/tests/test_foo.py\n"
            "@@ -5,2 +5,1 @@\n"
            "-    assert result == 42\n"
        )

        outcome = gate.verify_repository(
            repo_path=tmpdir,
            patch_text=diff,
            test_command="pytest tests/"
        )

        assert outcome.allow is False
        assert outcome.stage == "test_diff_audit"
        assert "Test weakening detected" in outcome.reason
