"""Unit tests for VerificationAdequacyGate."""

import pytest
from layer.verification_gate import VerificationAdequacyGate

SRC_CODE = """def is_authorized(user, role):
    if user.is_admin:
        return True
    return user.role == role
"""

CLEAN_PATCH = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,4 +1,4 @@
 def is_authorized(user, role):
-    if user.is_admin:
+    if user.is_super or user.is_admin:
         return True
     return user.role == role
"""

WEAKENED_TEST_PATCH = """diff --git a/tests/test_auth.py b/tests/test_auth.py
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -10,2 +10,1 @@
-    assert is_authorized(user, "editor") == True
"""

def test_veto_weakened_test_patch():
    gate = VerificationAdequacyGate()
    outcome = gate.verify(patch_text=WEAKENED_TEST_PATCH)
    assert not outcome.allow
    assert outcome.stage == "test_diff_audit"
    assert "ASSERTION_DELETED" in outcome.reason

def test_mutation_probe_passes_when_mutants_killed():
    gate = VerificationAdequacyGate(min_mutation_kill_ratio=0.50)
    # Simulated test runner: returns True (mutant killed) for all mutants
    test_runner = lambda mutant: True

    outcome = gate.verify(
        patch_text=CLEAN_PATCH,
        source_files_content={"src/auth.py": SRC_CODE},
        test_runner=test_runner,
    )
    assert outcome.allow
    assert outcome.stage == "verified"
    assert outcome.mutation_result is not None
    assert outcome.mutation_result.kill_ratio == 1.0

def test_mutation_probe_fails_when_tests_are_blind():
    gate = VerificationAdequacyGate(min_mutation_kill_ratio=0.50)
    # Simulated test runner: returns False (mutant survived / tests didn't catch bug)
    test_runner = lambda mutant: False

    outcome = gate.verify(
        patch_text=CLEAN_PATCH,
        source_files_content={"src/auth.py": SRC_CODE},
        test_runner=test_runner,
    )
    assert not outcome.allow
    assert outcome.stage == "mutation_probe"
    assert "Verification Inadequate" in outcome.reason
    assert outcome.mutation_result.kill_ratio == 0.0


def test_format_agent_feedback():
    gate = VerificationAdequacyGate(min_mutation_kill_ratio=0.50)

    # 1. Tampering feedback
    outcome_tamper = gate.verify(patch_text=WEAKENED_TEST_PATCH)
    fb_tamper = outcome_tamper.format_agent_feedback()
    assert "TEST TAMPERING DETECTED" in fb_tamper
    assert "DIRECTIVE: You are strictly forbidden" in fb_tamper

    # 2. Hollow test feedback
    test_runner_blind = lambda mutant: False
    outcome_hollow = gate.verify(
        patch_text=CLEAN_PATCH,
        source_files_content={"src/auth.py": SRC_CODE},
        test_runner=test_runner_blind,
    )
    fb_hollow = outcome_hollow.format_agent_feedback()
    assert "HOLLOW TESTS DETECTED" in fb_hollow
    assert "The following implementation mutations SURVIVED" in fb_hollow
    assert "DIRECTIVE: Your test suite is too permissive" in fb_hollow

    # 3. Passed feedback
    test_runner_sharp = lambda mutant: True
    outcome_pass = gate.verify(
        patch_text=CLEAN_PATCH,
        source_files_content={"src/auth.py": SRC_CODE},
        test_runner=test_runner_sharp,
    )
    fb_pass = outcome_pass.format_agent_feedback()
    assert "VERIFICATION PASSED" in fb_pass

