"""Tests for ARMA RepoWatcher."""

import os
from unittest.mock import MagicMock
from arma.watcher import RepoWatcher
from arma.guard import GuardVerdict


def test_repo_watcher_initialization():
    watcher = RepoWatcher()
    assert watcher.repo_path is not None
    assert watcher.guard is not None


def test_repo_watcher_check_once_no_change():
    watcher = RepoWatcher()
    # Mock get_current_diff returning empty
    watcher.get_current_diff = MagicMock(return_value="")
    v1 = watcher.check_once()
    assert v1 is not None
    assert v1.allowed is True

    # Subsequent check with same hash returns None (no changes)
    v2 = watcher.check_once()
    assert v2 is None


def test_repo_watcher_callback_on_verdict():
    callback_records = []
    def on_verdict(v: GuardVerdict):
        callback_records.append(v)

    watcher = RepoWatcher(on_verdict=on_verdict)
    watcher.get_current_diff = MagicMock(return_value="""
diff --git a/tests/test_foo.py b/tests/test_foo.py
--- a/tests/test_foo.py
+++ b/tests/test_foo.py
@@ -1,3 +1,3 @@
-def test_bar():
-    assert True
+def test_bar():
+    pass
""")
    verdict = watcher.check_once()
    assert verdict is not None
    assert len(callback_records) == 1
    assert callback_records[0] == verdict
