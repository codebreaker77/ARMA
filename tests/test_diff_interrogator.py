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
