"""Action taxonomy parser for OpenHands trajectories (E0).

Categorizes tool calls into four mutually exclusive classes:
- read_only: cat, head, tail, ls, find, grep, sed -n, view, git diff/log/status, file viewing
- test_run: pytest, unittest, tox, python -m unittest, test runners, repro/verification test scripts
- edit: str_replace_editor (str_replace, insert, create), sed -i, patch, git apply, file redirects
- other: environment setup, package install, git checkout/commit/stash, finish, think, task_tracker
"""

import json
import re
import shlex
from typing import Dict, Any, Optional, Tuple, List, Union

ACTION_CLASSES = ("read_only", "test_run", "edit", "other")

# Regex patterns for bash classification
TEST_COMMAND_PATTERNS = [
    r"\bpytest\b",
    r"\bunittest\b",
    r"\btox\b",
    r"\bnosetests\b",
    r"\bctest\b",
    r"\bcargo\s+test\b",
    r"\bnpm\s+test\b",
    r"\bpython[0-9.]*\s+(-m\s+(pytest|unittest))\b",
    r"\bpython[0-9.]*\s+([^\s]+\/)?([^\s]*?(test|reproduce?|verify|verification|debug|eval|check|demo|solution)[^\s]*?\.py)\b",
    r"\b(bash|sh)\s+([^\s]+\/)?(run_tests?\.sh|test\.sh)\b",
]

READ_ONLY_COMMANDS = {
    "cat", "head", "tail", "ls", "dir", "find", "grep", "egrep", "fgrep", "rg",
    "ack", "wc", "file", "which", "whereis", "type", "pwd", "tree", "nl", "less", "more"
}

EDIT_COMMANDS = {
    "patch", "sed -i", "git apply", "ed", "nano", "vim"
}

def clean_bash_command(raw_cmd: str) -> str:
    """Strip leading cd statements, environment exports, and trailing comments."""
    cmd = raw_cmd.strip()
    # Remove leading cd ... && or cd ... ;
    while True:
        m = re.match(r"^(cd\s+[^&;]+(&&|;)\s*)", cmd)
        if m:
            cmd = cmd[len(m.group(1)):].strip()
        else:
            break
            
    # Remove leading export VAR=... && or env prefixes
    while True:
        m = re.match(r"^((export\s+[A-Za-z0-9_]+=[^&;]*|[A-Za-z0-9_]+=[^\s&;]+)\s*(&&|;|\s)\s*)", cmd)
        if m:
            cmd = cmd[len(m.group(1)):].strip()
        else:
            break
            
    return cmd

def classify_bash_command(cmd_str: str) -> str:
    """Classify a single execute_bash command string."""
    cleaned = clean_bash_command(cmd_str)
    if not cleaned:
        return "other"
        
    # Check for test execution first (running tests or repro scripts)
    for pat in TEST_COMMAND_PATTERNS:
        if re.search(pat, cleaned, re.IGNORECASE):
            return "test_run"
            
    # Check for edits via sed -i, patch, git apply
    if re.search(r"\bsed\s+-[^\s]*i", cleaned):
        return "edit"
    if re.search(r"\b(patch|git\s+apply)\b", cleaned):
        return "edit"
        
    # Check for output redirection to a file (excluding /dev/null)
    # e.g., echo "..." > file.py, cat << 'EOF' > file.py
    if re.search(r"<<\s*['\"]?[A-Za-z0-9_]+['\"]?", cleaned):
        return "edit"
    if re.search(r"(?<![0-9])>\s*(?!\/dev\/null)\S+", cleaned):
        # Redirecting stdout into a file is an edit
        return "edit"
        
    # Check for git read-only operations vs modifying operations
    if cleaned.startswith("git"):
        parts = cleaned.split()
        if len(parts) > 1:
            sub = parts[1].lower()
            if sub in ("diff", "status", "log", "show", "branch"):
                return "read_only"
            if sub in ("checkout", "restore") and ("--" in parts or any(p.endswith((".py", ".c", ".h", ".js", ".ts")) for p in parts)):
                # Reverting / restoring files is an edit
                return "edit"
            if sub in ("commit", "add", "stash", "reset", "rebase", "merge"):
                return "other"
                
    # Check for sed -n (read only)
    if re.search(r"\bsed\s+-[^\s]*n\b", cleaned):
        return "read_only"
        
    # Check pipeline commands
    pipeline_parts = [p.strip() for p in re.split(r"[|;&]", cleaned) if p.strip()]
    if pipeline_parts:
        first_word = pipeline_parts[0].split()[0].lower() if pipeline_parts[0].split() else ""
        if first_word in READ_ONLY_COMMANDS:
            # Check if later part of pipe writes to file
            if not any(re.search(r"(?<![0-9])>\s*(?!\/dev\/null)\S+", p) for p in pipeline_parts):
                return "read_only"
                
    return "other"

def classify_tool_call(tool_name: str, arguments: Union[str, Dict[str, Any]]) -> Tuple[str, str]:
    """
    Classify an OpenHands tool call into (class, summary_text).
    Classes: 'read_only', 'test_run', 'edit', 'other'
    """
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments)
        except Exception:
            args = {}
    elif isinstance(arguments, dict):
        args = arguments
    else:
        args = {}
        
    if tool_name == "str_replace_editor":
        cmd = args.get("command", "")
        path = args.get("path", "")
        summary = f"[str_replace_editor:{cmd}] {path}".strip()
        if cmd in ("view", "view_range"):
            return "read_only", summary
        elif cmd in ("str_replace", "create", "insert", "undo_edit"):
            return "edit", summary
        else:
            return "other", summary
            
    elif tool_name == "execute_bash":
        cmd = args.get("command", "")
        summary = f"[execute_bash] {cmd}".strip()
        cls = classify_bash_command(cmd)
        return cls, summary
        
    elif tool_name == "think":
        thought = str(args.get("thought", ""))[:80].replace("\n", " ")
        return "other", f"[think] {thought}"
        
    elif tool_name == "finish":
        return "other", "[finish]"
        
    elif tool_name == "task_tracker":
        return "other", f"[task_tracker] {args.get('command', '')}"
        
    else:
        return "other", f"[{tool_name}]"

def extract_step_action(message: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Extract (class, summary_text) for a trajectory message.
    Returns None if message contains no tool calls.
    If multiple tool calls, prioritizes edit > test_run > read_only > other.
    """
    tcs = message.get("tool_calls")
    if tcs is None:
        return None
        
    # Handle both list and numpy ndarray
    if hasattr(tcs, "__len__") and len(tcs) == 0:
        return None
        
    classes_and_summaries = []
    for tc in tcs:
        if isinstance(tc, dict):
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", "")
            cls, summary = classify_tool_call(name, args)
            classes_and_summaries.append((cls, summary))
            
    if not classes_and_summaries:
        return None
        
    # Priority order if multiple: edit > test_run > read_only > other
    priority = {"edit": 0, "test_run": 1, "read_only": 2, "other": 3}
    classes_and_summaries.sort(key=lambda x: priority.get(x[0], 99))
    return classes_and_summaries[0]
