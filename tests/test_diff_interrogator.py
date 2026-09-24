"""Unit tests for the TestDiffInterrogator."""

import pytest
from layer.test_diff_interrogator import TestDiffInterrogator

def test_clean_impl_diff():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,3 @@
-def foo(): return 1
+def foo(): return 2
"""
    report = interrogator.interrogate_diff(diff)
    assert not report.touches_test_files
    assert report.is_adequate
    assert len(report.violations) == 0

def test_clean_new_test_addition():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -50,0 +51,4 @@
+def test_new_feature():
+    result = foo()
+    assert result == 2
"""
    report = interrogator.interrogate_diff(diff)
    assert report.touches_test_files
    assert report.is_adequate
    assert report.new_tests_count == 1
    assert len(report.violations) == 0

def test_detect_deleted_assertion():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -20,3 +20,1 @@
     val = compute()
-    assert val == 100
-    self.assertEqual(val, 100)
"""
    report = interrogator.interrogate_diff(diff)
    assert report.touches_test_files
    assert not report.is_adequate
    assert report.deleted_assertions_count >= 2
    types = [v.violation_type for v in report.violations]
    assert "ASSERTION_DELETED" in types

def test_detect_skip_injected():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -15,2 +15,3 @@
+@pytest.mark.skip(reason="temporarily skip")
 def test_failing_case():
+    pytest.skip("skipping")
     pass
"""
    report = interrogator.interrogate_diff(diff)
    assert not report.is_adequate
    assert report.injected_skips_count >= 1
    types = [v.violation_type for v in report.violations]
    assert "SKIP_INJECTED" in types

def test_detect_exception_swallowed():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -10,3 +10,6 @@
 def test_something():
+    try:
         assert do_calc() == 5
+    except AssertionError:
+        pass
"""
    report = interrogator.interrogate_diff(diff)
    assert not report.is_adequate
    assert report.swallowed_exceptions_count == 1
    types = [v.violation_type for v in report.violations]
    assert "EXCEPTION_SWALLOWED" in types

def test_detect_loosened_assertion():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -10,2 +10,2 @@
-    assert result == "EXACT_STRING_MATCH"
+    assert "EXACT_STRING_MATCH" in result
"""
    report = interrogator.interrogate_diff(diff)
    assert not report.is_adequate
    assert report.weakened_assertions_count == 1
    types = [v.violation_type for v in report.violations]
    assert "ASSERTION_WEAKENED" in types

def test_detect_deleted_test():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_auth.py b/tests/test_auth.py
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -20,5 +20,0 @@
-def test_strict_token_expiry():
-    token = get_token()
-    assert token.is_valid()
"""
    report = interrogator.interrogate_diff(diff)
    assert not report.is_adequate
    assert report.deleted_tests_count == 1
    types = [v.violation_type for v in report.violations]
    assert "TEST_DELETED" in types
    assert report.has_structural_tampering


def test_ignore_root_reproduction_scratch():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/reproduce_issue.py b/reproduce_issue.py
new file mode 100644
--- /dev/null
+++ b/reproduce_issue.py
@@ -0,0 +1,5 @@
+try:
+    assert False
+except Exception:
+    pass
+"""
    report = interrogator.interrogate_diff(diff)
    assert not report.touches_test_files
    assert report.is_adequate
    assert not report.has_structural_tampering


def test_modified_assertion_vs_structural():
    interrogator = TestDiffInterrogator()
    diff = """diff --git a/tests/test_parser.py b/tests/test_parser.py
--- a/tests/test_parser.py
+++ b/tests/test_parser.py
@@ -12,2 +12,2 @@
-    assert token == "OLD"
+    assert token == "NEW"
"""
    report = interrogator.interrogate_diff(diff)
    assert report.touches_test_files
    assert report.modified_assertions_count == 1
    # Modified assertion is not structural deletion
    assert not report.has_structural_tampering
    assert not report.has_critical_weakening
    assert report.is_adequate


def test_main_cli_clean(capsys):
    from layer.test_diff_interrogator import main_cli
    import io
    import sys

    clean_diff = """diff --git a/src/calc.py b/src/calc.py
--- a/src/calc.py
+++ b/src/calc.py
@@ -1,2 +1,2 @@
-x = 1
+x = 2
"""
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(clean_diff)
    try:
        ret = main_cli([])
        assert ret == 0
    finally:
        sys.stdin = old_stdin


def test_main_cli_tampering_veto(capsys):
    from layer.test_diff_interrogator import main_cli
    import io
    import sys

    bad_diff = """diff --git a/tests/test_foo.py b/tests/test_foo.py
--- a/tests/test_foo.py
+++ b/tests/test_foo.py
@@ -10,3 +10,0 @@
-def test_security():
-    assert verify_pass()
"""
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(bad_diff)
    try:
        ret = main_cli([])
        assert ret == 1
    finally:
        sys.stdin = old_stdin


def test_javascript_typescript_tampering():
    interrogator = TestDiffInterrogator()
    js_diff = """diff --git a/src/__tests__/auth.test.ts b/src/__tests__/auth.test.ts
--- a/src/__tests__/auth.test.ts
+++ b/src/__tests__/auth.test.ts
@@ -10,6 +10,4 @@
-it("should reject expired tokens", async () => {
-    expect(verifyToken(expired)).toBe(false);
-});
+it.skip("temporarily skip", async () => {
+    await doLogin().catch(() => {});
+});
"""
    report = interrogator.interrogate_diff(js_diff)
    assert report.touches_test_files
    assert report.has_structural_tampering
    assert report.deleted_tests_count >= 1
    assert report.injected_skips_count >= 1
    assert report.swallowed_exceptions_count >= 1
    v_types = [v.violation_type for v in report.violations]
    assert "TEST_DELETED" in v_types
    assert "SKIP_INJECTED" in v_types
    assert "EXCEPTION_SWALLOWED" in v_types


def test_go_tampering():
    interrogator = TestDiffInterrogator()
    go_diff = """diff --git a/pkg/service/user_test.go b/pkg/service/user_test.go
--- a/pkg/service/user_test.go
+++ b/pkg/service/user_test.go
@@ -20,5 +20,3 @@
-func TestCriticalSecurityCheck(t *testing.T) {
-    assert.NoError(t, RunCheck())
-}
+func TestExisting(t *testing.T) {
+    t.Skip("skipping on Windows")
 }
"""
    report = interrogator.interrogate_diff(go_diff)
    assert report.touches_test_files
    assert report.has_structural_tampering
    assert report.deleted_tests_count >= 1
    assert report.injected_skips_count >= 1
    v_types = [v.violation_type for v in report.violations]
    assert "TEST_DELETED" in v_types
    assert "SKIP_INJECTED" in v_types


def test_rust_tampering():
    interrogator = TestDiffInterrogator()
    rust_diff = """diff --git a/tests/integration_test.rs b/tests/integration_test.rs
--- a/tests/integration_test.rs
+++ b/tests/integration_test.rs
@@ -15,5 +15,3 @@
-#[test]
-fn test_memory_safety() {
-    assert_eq!(alloc(), 0);
-}
+#[ignore]
+#[test]
+fn test_other() {}
"""
    report = interrogator.interrogate_diff(rust_diff)
    assert report.touches_test_files
    assert report.has_structural_tampering
    assert report.injected_skips_count >= 1
    v_types = [v.violation_type for v in report.violations]
    assert "SKIP_INJECTED" in v_types


