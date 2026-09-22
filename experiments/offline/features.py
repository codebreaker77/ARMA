"""Prefix-only feature extraction for Stuck Predictor v2 (E4).

Features are strictly extracted from trajectory[:t].
Any interaction at step >= t is completely invisible to this module.
"""

import json
import os
import re
from typing import Dict, Any, List, Optional
import numpy as np

from experiments.offline.config import estimate_tokens, estimate_message_tokens
from experiments.offline.parser import extract_step_action, clean_bash_command
from experiments.offline.phase2_census import extract_failure_signature

FEATURE_NAMES = [
    "step_t",
    "read_only_count",
    "test_run_count",
    "edit_count",
    "other_count",
    "read_only_ratio",
    "test_run_ratio",
    "edit_ratio",
    "distinct_files_touched",
    "edit_revert_count",
    "repeated_command_count",
    "failing_test_stability",
    "tokens_so_far",
    "mean_obs_len",
    "first_edit_step_idx",
    "has_edited",
    "repro_script_exists",
    "num_assistant_turns",
]

def extract_prefix_features(traj: List[Dict[str, Any]], t: int) -> Dict[str, float]:
    """
    Extract observable features strictly from trajectory prefix before step t.
    Invariant: For any message at index >= t, content is never accessed.
    """
    prefix = traj[:t]
    
    read_only_count = 0
    test_run_count = 0
    edit_count = 0
    other_count = 0
    
    files_touched = set()
    edit_revert_count = 0
    commands_seen = set()
    repeated_command_count = 0
    
    failing_test_stability = 0
    last_failure_sig = None
    
    obs_lengths = []
    tokens_so_far = 0
    first_edit_step_idx = -1
    repro_script_exists = 0
    num_assistant_turns = 0
    
    file_state_history: Dict[str, List[str]] = {}
    
    for i, msg in enumerate(prefix):
        tokens_so_far += estimate_message_tokens(msg)
        role = msg.get("role")
        
        if role == "tool":
            content = msg.get("content", "")
            obs_lengths.append(len(content))
            
        elif role == "assistant":
            num_assistant_turns += 1
            action_res = extract_step_action(msg)
            if not action_res:
                continue
                
            cls, summary = action_res
            if cls == "read_only":
                read_only_count += 1
            elif cls == "test_run":
                test_run_count += 1
            elif cls == "edit":
                edit_count += 1
                if first_edit_step_idx == -1:
                    first_edit_step_idx = i
            elif cls == "other":
                other_count += 1
                
            tcs = msg.get("tool_calls", [])
            if tcs and len(tcs) > 0:
                tc = tcs[0].get("function", {})
                tool_name = tc.get("name", "")
                args_str = tc.get("arguments", "{}")
                try:
                    args_dict = json.loads(args_str) if isinstance(args_str, str) else args_str
                except Exception:
                    args_dict = {}
                    
                # Track repeated commands
                cmd_sig = (tool_name, args_str if isinstance(args_str, str) else json.dumps(args_str))
                if cmd_sig in commands_seen:
                    repeated_command_count += 1
                else:
                    commands_seen.add(cmd_sig)
                    
                # Track files touched
                p = args_dict.get("path")
                if p:
                    files_touched.add(p)
                elif tool_name == "execute_bash":
                    cmd = args_dict.get("command", "")
                    paths = re.findall(r"([a-zA-Z0-9_./-]+\.(?:py|c|h|md|txt|json|yaml|yml|toml|sh))", cmd)
                    for fp in paths:
                        files_touched.add(fp)
                    if any(w in cmd for w in ("reproduce", "repro", "test_", "_test", "verify")):
                        repro_script_exists = 1
                        
                # Edit-revert detection
                if cls == "edit":
                    p = args_dict.get("path")
                    cmd = args_dict.get("command")
                    if p:
                        hist = file_state_history.setdefault(p, [])
                        if cmd == "create":
                            h = "create:" + str(hash(args_dict.get("file_text", "")))
                            if h in hist:
                                edit_revert_count += 1
                            hist.append(h)
                        elif cmd == "undo_edit":
                            edit_revert_count += 1
                        elif cmd == "str_replace":
                            old_s = args_dict.get("old_str", "")
                            new_s = args_dict.get("new_str", "")
                            fwd = f"{old_s}-->{new_s}"
                            rev = f"{new_s}-->{old_s}"
                            if rev in hist:
                                edit_revert_count += 1
                            hist.append(fwd)
                            
                # Check failing test stability
                if cls == "test_run" and i + 1 < len(prefix) and prefix[i + 1].get("role") == "tool":
                    obs = prefix[i + 1].get("content", "")
                    sig = extract_failure_signature(obs)
                    if sig:
                        if sig == last_failure_sig:
                            failing_test_stability += 1
                        last_failure_sig = sig
                elif cls == "edit":
                    last_failure_sig = None
                    
    total_actions = max(1, read_only_count + test_run_count + edit_count + other_count)
    mean_obs = float(np.mean(obs_lengths)) if obs_lengths else 0.0
    
    return {
        "step_t": float(t),
        "read_only_count": float(read_only_count),
        "test_run_count": float(test_run_count),
        "edit_count": float(edit_count),
        "other_count": float(other_count),
        "read_only_ratio": float(read_only_count / total_actions),
        "test_run_ratio": float(test_run_count / total_actions),
        "edit_ratio": float(edit_count / total_actions),
        "distinct_files_touched": float(len(files_touched)),
        "edit_revert_count": float(edit_revert_count),
        "repeated_command_count": float(repeated_command_count),
        "failing_test_stability": float(failing_test_stability),
        "tokens_so_far": float(tokens_so_far),
        "mean_obs_len": mean_obs,
        "first_edit_step_idx": float(first_edit_step_idx),
        "has_edited": 1.0 if edit_count > 0 else 0.0,
        "repro_script_exists": float(repro_script_exists),
        "num_assistant_turns": float(num_assistant_turns),
    }
