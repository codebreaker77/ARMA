"""Tests for ARMA AgentGuard SDK."""

import pytest
from arma.guard import AgentGuard, GuardVerdict, CommandVerdict


def test_agent_guard_clean_diff():
    guard = AgentGuard()
    diff = """
diff --git a/core/calc.py b/core/calc.py
--- a/core/calc.py
+++ b/core/calc.py
@@ -1,3 +1,4 @@
 def add(a, b):
+    # Add documentation
     return a + b
diff --git a/tests/test_calc.py b/tests/test_calc.py
--- a/tests/test_calc.py
+++ b/tests/test_calc.py
@@ -5,3 +5,6 @@
 def test_add():
     assert add(1, 2) == 3
+
+def test_add_negative():
+    assert add(-1, -1) == -2
"""
    verdict = guard.audit_diff(diff)
    assert verdict.allowed is True
    assert verdict.vetoed is False
    assert len(verdict.violations) == 0


def test_agent_guard_veto_deleted_test():
    guard = AgentGuard()
    diff = """
diff --git a/tests/test_auth.py b/tests/test_auth.py
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -10,4 +10,0 @@
-def test_invalid_jwt_rejected():
-    res = auth_client.get("/protected")
-    assert res.status_code == 401
"""
    verdict = guard.audit_diff(diff)
    assert verdict.allowed is False
    assert verdict.vetoed is True
    assert any(v.violation_type == "TEST_DELETED" for v in verdict.violations)
    assert "TEST TAMPERING DETECTED" in verdict.feedback
    assert "strictly forbidden" in verdict.feedback.lower()


def test_agent_guard_veto_injected_skip():
    guard = AgentGuard()
    diff = """
diff --git a/tests/test_crypto.py b/tests/test_crypto.py
--- a/tests/test_crypto.py
+++ b/tests/test_crypto.py
@@ -1,3 +1,4 @@
+@pytest.mark.skip(reason="Fails under load")
 def test_rsa_keygen():
     assert generate_key() is not None
"""
    verdict = guard.audit_diff(diff)
    assert verdict.allowed is False
    assert verdict.vetoed is True
    assert any(v.violation_type == "SKIP_INJECTED" for v in verdict.violations)


def test_agent_guard_command_safety():
    guard = AgentGuard()
    
    # Safe commands
    safe_1 = guard.audit_command("pytest tests/ -v")
    assert safe_1.allowed is True

    safe_2 = guard.audit_command("git status")
    assert safe_2.allowed is True

    # Dangerous commands
    bad_1 = guard.audit_command("rm -rf /")
    assert bad_1.allowed is False
    assert "Blocked hazardous command" in bad_1.reason

    bad_2 = guard.audit_command("git push origin main --force")
    assert bad_2.allowed is False

    bad_3 = guard.audit_command("DROP DATABASE users;")
    assert bad_3.allowed is False


def test_agent_guard_predict_impact():
    guard = AgentGuard()
    impact = guard.predict_impact("layer/code_graph.py")
    assert "layer/code_graph.py" in impact
    assert any("test_code_graph.py" in f for f in impact)


def test_agent_guard_prompt_guardrails():
    guard = AgentGuard()
    guardrails = guard.get_prompt_guardrails()
    assert "ARMA Reliability Invariants" in guardrails
    assert "Never delete" in guardrails
