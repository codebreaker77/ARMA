"""Unit tests for OpenHands tool call action taxonomy parser."""

import pytest
from experiments.offline.parser import (
    classify_tool_call,
    classify_bash_command,
    clean_bash_command,
    extract_step_action,
)

def test_clean_bash_command():
    assert clean_bash_command("cd /workspace/repo && ls -la") == "ls -la"
    assert clean_bash_command("cd /workspace/repo ; find .") == "find ."
    assert clean_bash_command("export PYTHONPATH=. && pytest") == "pytest"
    assert clean_bash_command("FOO=1 BAR=2 pytest") == "pytest"

def test_read_only_bash():
    read_cmds = [
        "cat file.py",
        "head -n 20 file.py",
        "tail -n 10 file.py",
        "ls -la /workspace",
        "find . -name '*.py'",
        "grep -rn 'def foo' .",
        "rg 'foo' src/",
        "sed -n '1,10p' file.py",
        "git diff",
        "git status",
        "git log -n 5",
        "git show HEAD",
        "cd /workspace/repo && find . -name '*.py' | head -10",
        "cd /workspace/repo && grep -rn 'bar' .",
    ]
    for cmd in read_cmds:
        assert classify_bash_command(cmd) == "read_only", f"Failed on: {cmd}"

def test_read_only_editor():
    cls, _ = classify_tool_call("str_replace_editor", {"command": "view", "path": "/workspace/file.py"})
    assert cls == "read_only"
    cls, _ = classify_tool_call("str_replace_editor", {"command": "view_range", "path": "/workspace/file.py"})
    assert cls == "read_only"

def test_test_run_bash():
    test_cmds = [
        "pytest",
        "pytest tests/test_basic.py -v",
        "python -m pytest lib/tests/",
        "python3 -m pytest -k 'test_one'",
        "tox -e py39",
        "python -m unittest discover",
        "python reproduce_issue.py",
        "python test_fix_verification.py",
        "python simple_reproduce.py",
        "python debug_circular.py",
        "python final_verification.py",
        "cd /workspace/repo && python reproduce_issue.py",
        "cd /workspace/repo && python -m pytest tests/",
    ]
    for cmd in test_cmds:
        assert classify_bash_command(cmd) == "test_run", f"Failed on: {cmd}"

def test_edit_editor():
    for edit_cmd in ["str_replace", "create", "insert", "undo_edit"]:
        cls, _ = classify_tool_call("str_replace_editor", {"command": edit_cmd, "path": "file.py"})
        assert cls == "edit", f"Failed on editor:{edit_cmd}"

def test_edit_bash():
    edit_cmds = [
        "sed -i 's/foo/bar/g' file.py",
        "patch -p1 < fix.patch",
        "git apply fix.patch",
        "echo 'foo' > file.py",
        "cat << 'EOF' > script.py\nprint(1)\nEOF",
        "cd /workspace && sed -i 's/1/2/' test.py",
    ]
    for cmd in edit_cmds:
        assert classify_bash_command(cmd) == "edit", f"Failed on: {cmd}"

def test_other_commands():
    other_cmds = [
        "pip install docutils",
        "python setup.py install",
        "git stash pop",
        "git commit -m 'wip'",
        "git checkout -b new-branch",
        "sleep 2",
    ]
    for cmd in other_cmds:
        assert classify_bash_command(cmd) == "other", f"Failed on: {cmd}"

    cls, _ = classify_tool_call("think", {"thought": "analyzing the bug"})
    assert cls == "other"
    cls, _ = classify_tool_call("finish", {})
    assert cls == "other"
    cls, _ = classify_tool_call("task_tracker", {"command": "add_task"})
    assert cls == "other"

def test_extract_step_action():
    msg = {
        "role": "assistant",
        "tool_calls": [
            {
                "function": {
                    "name": "execute_bash",
                    "arguments": '{"command": "python -m pytest tests/test_core.py"}'
                }
            }
        ]
    }
    action = extract_step_action(msg)
    assert action is not None
    assert action[0] == "test_run"
    assert "pytest" in action[1]
