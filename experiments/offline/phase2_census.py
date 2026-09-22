"""Phase 2: Loop Census (E1) and Step-Type Routing Census (E2).

Implements:
- E1 Exact loop detection (OpenHands patterns):
  1. Identical action + observation >= 4
  2. Identical action + error >= 3
  3. Monologue >= 3
  4. Alternating A, B >= 6 cycles
- E1 Semantic loop detection:
  1. Edit-revert (file hash state returns to earlier state)
  2. Same failing test IDs >= 3 times with no intervening edit
  3. Same file re-read >= 3 times with no intervening edit or test
- Loop impact & simulated cut policy (grace g in {0, 3, 5}):
  Tokens saved, resolved runs wrongly cut, cost per resolved task.
- E2 Step-type census & routable cost upper bounds:
  Step share and cost share by class, routable bound for r in {0.10, 0.25},
  and cache-aware model switch discount analysis.
"""

import json
import os
import re
import time
from typing import Dict, Any, List, Tuple, Optional, Set
import numpy as np
import pandas as pd

from experiments.offline.config import (
    SAMPLED_DATA_PATH,
    RESULTS_DIR,
    RANDOM_SEED,
    estimate_tokens,
    estimate_message_tokens,
    cluster_bootstrap_ci,
    is_dev_repo,
)
from experiments.offline.parser import extract_step_action, clean_bash_command

# ---------------------------------------------------------------------------
# E1: Loop Detectors
# ---------------------------------------------------------------------------

def extract_failure_signature(obs_text: str) -> Optional[str]:
    """Extract a representative test failure signature from tool output."""
    if not obs_text:
        return None
    # 1. Look for pytest FAILED lines
    failed_lines = re.findall(r"FAILED\s+([^\s:]+(?:::[\w\<\>\[\]_]+)*)", obs_text)
    if failed_lines:
        return "pytest:" + ",".join(sorted(set(failed_lines))[:5])
    # 2. Look for Python exceptions/traceback tail
    exc = re.findall(r"\b([A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception):\s*(.*)", obs_text)
    if exc:
        err_type, err_msg = exc[-1]
        return f"exc:{err_type}:{err_msg.strip()[:60]}"
    # 3. Check for non-zero exit code
    m = re.search(r"\[Command finished with exit code ([1-9]\d*)\]", obs_text)
    if m:
        return f"exit_code:{m.group(1)}"
    if "Traceback (most recent call last):" in obs_text:
        return "traceback:generic"
    return None

def detect_loops_in_trajectory(traj: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Scan a trajectory for exact and semantic loop patterns.
    Returns detection flags, first detection step index, and loop step masks.
    """
    n_msgs = len(traj)
    
    # Pre-extract assistant actions and their corresponding tool observations
    # Each entry: (msg_idx, tool_name, args_dict, args_str, obs_content, action_class, step_tokens)
    actions = []
    monologue_streaks = []
    current_mono_streak = 0
    
    # Calculate cumulative prefix tokens (prompt size at each assistant step)
    cum_tokens = 0
    prefix_tokens_by_step = []
    msg_token_counts = []
    
    for i, msg in enumerate(traj):
        t_cnt = estimate_message_tokens(msg)
        msg_token_counts.append(t_cnt)
        prefix_tokens_by_step.append(cum_tokens)
        cum_tokens += t_cnt
        
        if msg.get("role") == "assistant":
            tcs = msg.get("tool_calls")
            if tcs is None or len(tcs) == 0:
                current_mono_streak += 1
                if current_mono_streak >= 3:
                    monologue_streaks.append(i)
                continue
            else:
                current_mono_streak = 0
                
            tc = tcs[0].get("function", {})
            name = tc.get("name", "")
            args_str = tc.get("arguments", "{}")
            try:
                args_dict = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception:
                args_dict = {}
                
            obs = ""
            if i + 1 < n_msgs and traj[i + 1].get("role") == "tool":
                obs = traj[i + 1].get("content", "")
                
            action_res = extract_step_action(msg)
            cls = action_res[0] if action_res else "other"
            
            actions.append({
                "msg_idx": i,
                "tool_name": name,
                "args_dict": args_dict,
                "args_str": args_str if isinstance(args_str, str) else json.dumps(args_str),
                "obs": obs,
                "class": cls,
                "step_tokens": t_cnt,
                "prompt_tokens": prefix_tokens_by_step[i],
            })
            
    n_actions = len(actions)
    
    # Tracking detection events: (detection_step_idx, loop_type)
    detections = []
    
    # Record monologue detections
    for m_idx in monologue_streaks:
        detections.append((m_idx, "exact_monologue"))
        
    # 1. Exact: Identical action + observation >= 4
    for k in range(3, n_actions):
        if (actions[k]["tool_name"] == actions[k-1]["tool_name"] == actions[k-2]["tool_name"] == actions[k-3]["tool_name"] and
            actions[k]["args_str"] == actions[k-1]["args_str"] == actions[k-2]["args_str"] == actions[k-3]["args_str"] and
            actions[k]["obs"] == actions[k-1]["obs"] == actions[k-2]["obs"] == actions[k-3]["obs"] and
            actions[k]["obs"] != ""):
            detections.append((actions[k]["msg_idx"], "exact_action_obs_4"))
            
    # 2. Exact: Identical action + error >= 3
    for k in range(2, n_actions):
        is_err = any(extract_failure_signature(actions[j]["obs"]) is not None for j in (k, k-1, k-2))
        if is_err:
            if (actions[k]["tool_name"] == actions[k-1]["tool_name"] == actions[k-2]["tool_name"] and
                actions[k]["args_str"] == actions[k-1]["args_str"] == actions[k-2]["args_str"]):
                detections.append((actions[k]["msg_idx"], "exact_action_err_3"))
                
    # 3. Exact: Alternating A, B >= 6 cycles (12 actions)
    for k in range(11, n_actions):
        a_sig = (actions[k-1]["tool_name"], actions[k-1]["args_str"])
        b_sig = (actions[k]["tool_name"], actions[k]["args_str"])
        if a_sig != b_sig:
            is_alt = True
            for c in range(6):
                cur_b = (actions[k - 2*c]["tool_name"], actions[k - 2*c]["args_str"])
                cur_a = (actions[k - 2*c - 1]["tool_name"], actions[k - 2*c - 1]["args_str"])
                if cur_b != b_sig or cur_a != a_sig:
                    is_alt = False
                    break
            if is_alt:
                detections.append((actions[k]["msg_idx"], "exact_alternating_6"))
                
    # 4. Semantic: (a) Edit-revert
    file_state_history: Dict[str, List[str]] = {}
    for act in actions:
        if act["class"] == "edit":
            p = act["args_dict"].get("path")
            cmd = act["args_dict"].get("command")
            if p:
                hist = file_state_history.setdefault(p, [])
                if cmd == "create":
                    h = "content:" + str(hash(act["args_dict"].get("file_text", "")))
                    if h in hist:
                        detections.append((act["msg_idx"], "semantic_edit_revert"))
                    hist.append(h)
                elif cmd == "undo_edit":
                    detections.append((act["msg_idx"], "semantic_edit_revert"))
                elif cmd == "str_replace":
                    old_s = act["args_dict"].get("old_str", "")
                    new_s = act["args_dict"].get("new_str", "")
                    fwd = f"{old_s}-->{new_s}"
                    rev = f"{new_s}-->{old_s}"
                    if rev in hist:
                        detections.append((act["msg_idx"], "semantic_edit_revert"))
                    hist.append(fwd)
                    
    # 5. Semantic: (b) Same failing test IDs >= 3 times with no relevant edit between
    failing_streak = 0
    last_fail_sig = None
    for act in actions:
        cls = act["class"]
        if cls == "test_run":
            sig = extract_failure_signature(act["obs"])
            if sig is not None:
                if sig == last_fail_sig:
                    failing_streak += 1
                    if failing_streak >= 3:
                        detections.append((act["msg_idx"], "semantic_failing_test_3"))
                else:
                    last_fail_sig = sig
                    failing_streak = 1
        elif cls == "edit":
            failing_streak = 0
            last_fail_sig = None
            
    # 6. Semantic: (c) Same file re-read >= 3 times with no edit or test between
    file_reads_streak: Dict[str, int] = {}
    for act in actions:
        cls = act["class"]
        if cls in ("edit", "test_run"):
            file_reads_streak.clear()
        elif cls == "read_only":
            p = act["args_dict"].get("path")
            if not p and act["tool_name"] == "execute_bash":
                m = re.search(r"\b(?:cat|head|tail|view)\s+([^\s|;&]+)", act["args_dict"].get("command", ""))
                if m:
                    p = m.group(1)
            if p:
                file_reads_streak[p] = file_reads_streak.get(p, 0) + 1
                if file_reads_streak[p] >= 3:
                    detections.append((act["msg_idx"], "semantic_reread_3"))
                    
    # Sort detections by step index
    detections.sort(key=lambda x: x[0])
    has_loop = len(detections) > 0
    first_detect_idx = detections[0][0] if has_loop else None
    loop_types = sorted(set(d[1] for d in detections))
    
    # Mask of messages inside loops (from first detection to end of trajectory)
    is_step_inside_loop = np.zeros(n_msgs, dtype=bool)
    if has_loop:
        is_step_inside_loop[first_detect_idx:] = True
        
    # Check recovery within k=5 steps (did an action of a different type happen, or did test pass?)
    recovered_in_5 = False
    if has_loop and first_detect_idx is not None:
        # Find which action corresponded to first detection
        action_match_idx = None
        for a_idx, act in enumerate(actions):
            if act["msg_idx"] >= first_detect_idx:
                action_match_idx = a_idx
                break
        if action_match_idx is not None:
            # Check next 5 actions
            future_actions = actions[action_match_idx+1 : action_match_idx+6]
            initial_cls = actions[action_match_idx]["class"]
            for fa in future_actions:
                if fa["class"] != initial_cls:
                    recovered_in_5 = True
                    break
                    
    return {
        "has_loop": has_loop,
        "first_detect_idx": first_detect_idx,
        "loop_types": loop_types,
        "detections_count": len(detections),
        "is_step_inside_loop": is_step_inside_loop,
        "recovered_in_5": recovered_in_5,
        "actions": actions,
        "msg_token_counts": msg_token_counts,
        "total_trajectory_tokens": cum_tokens,
    }

# ---------------------------------------------------------------------------
# E1 & E2 Driver & Simulation
# ---------------------------------------------------------------------------

def run_phase2_census(split_filter: Optional[str] = "dev") -> Dict[str, Any]:
    print("=" * 80)
    print(f"PHASE 2: LOOP CENSUS (E1) & STEP-TYPE CENSUS (E2) [Split: {split_filter.upper() if split_filter else 'ALL'}]")
    print("=" * 80)
    
    t0 = time.time()
    df_all = pd.read_parquet(SAMPLED_DATA_PATH)
    if split_filter:
        df = df_all[df_all["split"] == split_filter].copy().reset_index(drop=True)
    else:
        df = df_all.copy()
        
    n_trajs = len(df)
    n_repos = df["repo"].nunique()
    print(f"Analyzing {n_trajs} trajectories across {n_repos} repositories...")
    
    # Storage for per-trajectory results
    loop_results = []
    class_step_counts = {"read_only": 0, "test_run": 0, "edit": 0, "other": 0}
    class_step_tokens = {"read_only": 0, "test_run": 0, "edit": 0, "other": 0}
    class_prompt_tokens = {"read_only": 0, "test_run": 0, "edit": 0, "other": 0}
    
    total_steps_all = 0
    total_tokens_all = 0
    
    # Switching / cache tracking
    model_transitions = 0 # transitions between strong tier (edit/other) and cheap tier (read_only/test_run)
    
    for idx, row in df.iterrows():
        res = detect_loops_in_trajectory(row["trajectory"])
        res["resolved"] = int(row["resolved"])
        res["repo"] = row["repo"]
        res["trajectory_id"] = row["trajectory_id"]
        res["total_steps"] = len(row["trajectory"])
        loop_results.append(res)
        
        # Accumulate E2 step census
        last_tier = None
        for act in res["actions"]:
            c = act["class"]
            class_step_counts[c] += 1
            class_step_tokens[c] += act["step_tokens"]
            class_prompt_tokens[c] += act["prompt_tokens"]
            
            # Tier: cheap for read_only/test_run, strong for edit/other
            current_tier = "cheap" if c in ("read_only", "test_run") else "strong"
            if last_tier is not None and current_tier != last_tier:
                model_transitions += 1
            last_tier = current_tier
            
        total_steps_all += res["total_steps"]
        total_tokens_all += res["total_trajectory_tokens"]
        
    df_loops = pd.DataFrame({
        "repo": [r["repo"] for r in loop_results],
        "resolved": [r["resolved"] for r in loop_results],
        "has_loop": [r["has_loop"] for r in loop_results],
        "recovered_in_5": [r["recovered_in_5"] for r in loop_results],
        "total_steps": [r["total_steps"] for r in loop_results],
        "total_tokens": [r["total_trajectory_tokens"] for r in loop_results],
        "loop_steps": [int(np.sum(r["is_step_inside_loop"])) for r in loop_results],
        "loop_tokens": [int(np.sum(np.array(r["msg_token_counts"])[r["is_step_inside_loop"]])) for r in loop_results],
        "first_detect_idx": [r["first_detect_idx"] for r in loop_results],
    })
    
    # -----------------------------------------------------------------------
    # E1 Metrics Computation
    # -----------------------------------------------------------------------
    pct_has_loop = float(df_loops["has_loop"].mean())
    ci_has_loop = cluster_bootstrap_ci(df_loops, lambda d: float(d["has_loop"].mean()), seed=RANDOM_SEED)
    
    df_res = df_loops[df_loops["resolved"] == 1]
    df_unres = df_loops[df_loops["resolved"] == 0]
    
    # Percentage of steps and tokens inside loops
    pct_steps_loop_res = float(df_res["loop_steps"].sum() / df_res["total_steps"].sum()) if len(df_res) else 0.0
    pct_steps_loop_unres = float(df_unres["loop_steps"].sum() / df_unres["total_steps"].sum()) if len(df_unres) else 0.0
    
    pct_tokens_loop_res = float(df_res["loop_tokens"].sum() / df_res["total_tokens"].sum()) if len(df_res) else 0.0
    pct_tokens_loop_unres = float(df_unres["loop_tokens"].sum() / df_unres["total_tokens"].sum()) if len(df_unres) else 0.0
    
    # Bootstrap CI for tokens inside loops in unresolved runs
    ci_tokens_loop_unres = cluster_bootstrap_ci(
        df_unres,
        lambda d: float(d["loop_tokens"].sum() / d["total_tokens"].sum()) if d["total_tokens"].sum() > 0 else 0.0,
        seed=RANDOM_SEED
    )
    
    # Recovery rate (state changes within k=5 steps given loop entered)
    looped_df = df_loops[df_loops["has_loop"]]
    recovery_rate = float(looped_df["recovered_in_5"].mean()) if len(looped_df) else 0.0
    # True resolution given loop entered
    res_given_loop = float(looped_df["resolved"].mean()) if len(looped_df) else 0.0
    
    # -----------------------------------------------------------------------
    # E1 Simulated Cut Policy Simulation (Grace g in {0, 3, 5})
    # -----------------------------------------------------------------------
    cut_simulations = {}
    base_resolved_count = int(df_loops["resolved"].sum())
    base_total_tokens = int(df_loops["total_tokens"].sum())
    
    for g in [0, 3, 5]:
        tokens_saved = 0
        wrongly_cut_resolved = 0
        
        for idx, r in enumerate(loop_results):
            if r["has_loop"] and r["first_detect_idx"] is not None:
                cut_step = r["first_detect_idx"] + g
                if cut_step < r["total_steps"]:
                    # Tokens after cut_step are saved
                    t_after = sum(r["msg_token_counts"][cut_step:])
                    tokens_saved += t_after
                    if r["resolved"] == 1:
                        wrongly_cut_resolved += 1
                        
        effective_resolved = base_resolved_count - wrongly_cut_resolved
        pct_wrongly_cut = wrongly_cut_resolved / base_resolved_count if base_resolved_count > 0 else 0.0
        pct_tokens_saved = tokens_saved / base_total_tokens if base_total_tokens > 0 else 0.0
        
        cost_per_resolved = (base_total_tokens - tokens_saved) / effective_resolved if effective_resolved > 0 else float("inf")
        baseline_cost_per_resolved = base_total_tokens / base_resolved_count if base_resolved_count > 0 else float("inf")
        
        cut_simulations[f"grace_{g}"] = {
            "grace": g,
            "tokens_saved": int(tokens_saved),
            "pct_tokens_saved": float(pct_tokens_saved),
            "wrongly_cut_resolved": int(wrongly_cut_resolved),
            "pct_wrongly_cut_resolved": float(pct_wrongly_cut),
            "effective_resolved": int(effective_resolved),
            "cost_per_resolved_task_tokens": float(cost_per_resolved),
            "baseline_cost_per_resolved": float(baseline_cost_per_resolved),
            "cost_reduction_ratio": float(cost_per_resolved / baseline_cost_per_resolved),
        }
        
    # -----------------------------------------------------------------------
    # E2 Metrics Computation (Step Census & Routable Bounds)
    # -----------------------------------------------------------------------
    total_classified_steps = sum(class_step_counts.values())
    total_classified_tokens = sum(class_step_tokens.values())
    total_classified_prompt_tokens = sum(class_prompt_tokens.values())
    
    # Combined step tokens + prompt tokens represents the full API billing cost
    total_combined_cost_tokens = total_classified_tokens + total_classified_prompt_tokens
    
    e2_by_class = {}
    for c in ("read_only", "test_run", "edit", "other"):
        combined_cost = class_step_tokens[c] + class_prompt_tokens[c]
        e2_by_class[c] = {
            "step_count": class_step_counts[c],
            "step_share": class_step_counts[c] / total_classified_steps if total_classified_steps else 0.0,
            "completion_tokens_estimate": class_step_tokens[c],
            "prompt_tokens_estimate": class_prompt_tokens[c],
            "total_tokens_cost": combined_cost,
            "cost_share": combined_cost / total_combined_cost_tokens if total_combined_cost_tokens else 0.0,
        }
        
    routable_cost_share = e2_by_class["read_only"]["cost_share"] + e2_by_class["test_run"]["cost_share"]
    
    # Routing savings bounds for r in {0.10, 0.25}
    routing_bounds = {}
    for r in (0.10, 0.25):
        theoretical_upper_bound = routable_cost_share * (1.0 - r)
        
        # Cache-aware variant:
        # Prompt caching typically yields 50% discount on cached tokens.
        # When switching models, the entire prompt must be processed cold (loss of cache discount).
        # We estimate cache-loss penalty per model transition: ~20% penalty on prompt tokens during transition steps.
        transition_penalty = (model_transitions * (total_classified_prompt_tokens / total_classified_steps) * 0.20) / total_combined_cost_tokens
        cache_aware_savings = max(0.0, theoretical_upper_bound - transition_penalty)
        
        routing_bounds[f"price_ratio_{r}"] = {
            "price_ratio_r": r,
            "theoretical_savings_upper_bound": float(theoretical_upper_bound),
            "cache_penalty_share": float(transition_penalty),
            "cache_aware_net_savings": float(cache_aware_savings),
        }
        
    # -----------------------------------------------------------------------
    # Threshold Verification
    # -----------------------------------------------------------------------
    # E1 Threshold: Loops >= 10% of tokens in unresolved runs AND cut policy loses <= 2% of resolved runs (at grace 3 or 5)
    e1_threshold_tokens_met = (pct_tokens_loop_unres >= 0.10)
    e1_threshold_cut_met = any(cut_simulations[k]["pct_wrongly_cut_resolved"] <= 0.02 for k in cut_simulations)
    e1_decision = e1_threshold_tokens_met and e1_threshold_cut_met
    
    # E2 Threshold: Pursue routing only if routable share of cost >= 40%
    e2_threshold_met = (routable_cost_share >= 0.40)
    e2_decision = e2_threshold_met
    
    results = {
        "split": split_filter,
        "n_trajectories": n_trajs,
        "n_repos": n_repos,
        "e1_loop_census": {
            "pct_trajectories_with_any_loop": pct_has_loop,
            "pct_trajectories_with_any_loop_95ci": list(ci_has_loop),
            "pct_steps_inside_loops_resolved": pct_steps_loop_res,
            "pct_steps_inside_loops_unresolved": pct_steps_loop_unres,
            "pct_tokens_inside_loops_resolved": pct_tokens_loop_res,
            "pct_tokens_inside_loops_unresolved": pct_tokens_loop_unres,
            "pct_tokens_inside_loops_unresolved_95ci": list(ci_tokens_loop_unres),
            "recovery_rate_k5": recovery_rate,
            "resolution_rate_given_loop": res_given_loop,
            "cut_policy_simulation": cut_simulations,
            "e1_threshold_tokens_unres_ge_10pct": bool(e1_threshold_tokens_met),
            "e1_threshold_cut_loss_le_2pct": bool(e1_threshold_cut_met),
            "e1_pursue_loop_recovery": bool(e1_decision),
        },
        "e2_step_census": {
            "by_class": e2_by_class,
            "routable_cost_share": float(routable_cost_share),
            "model_transitions_count": model_transitions,
            "routing_savings_bounds": routing_bounds,
            "e2_threshold_routable_cost_ge_40pct": bool(e2_threshold_met),
            "e2_pursue_tier_routing": bool(e2_decision),
        },
        "compute_time_seconds": time.time() - t0,
    }
    
    out_file = os.path.join(RESULTS_DIR, f"phase2_census_{split_filter if split_filter else 'all'}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 80)
    print("PHASE 2 EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Trajectories:           {n_trajs} ({split_filter.upper() if split_filter else 'ALL'})")
    print(f"Trajectories w/ loop:   {pct_has_loop*100:.2f}% (95% CI: [{ci_has_loop[0]*100:.2f}%, {ci_has_loop[1]*100:.2f}%])")
    print(f"Tokens in Loops:        Resolved: {pct_tokens_loop_res*100:.2f}% | Unresolved: {pct_tokens_loop_unres*100:.2f}% (95% CI: [{ci_tokens_loop_unres[0]*100:.2f}%, {ci_tokens_loop_unres[1]*100:.2f}%])")
    print(f"Recovery Rate (k=5):    {recovery_rate*100:.2f}% (Final resolution given loop: {res_given_loop*100:.2f}%)")
    print("-" * 80)
    print("SIMULATED CUT POLICY (Grace g):")
    for k, v in cut_simulations.items():
        print(f"  {k}: Tokens Saved={v['pct_tokens_saved']*100:.2f}% | Wrongly Cut Resolved={v['pct_wrongly_cut_resolved']*100:.2f}% ({v['wrongly_cut_resolved']}/{base_resolved_count}) | Cost/Resolved Ratio={v['cost_reduction_ratio']:.3f}")
    print("-" * 80)
    print(f"E1 THRESHOLD EVALUATION: Tokens in Unres >= 10%: {e1_threshold_tokens_met} | Cut Loss <= 2%: {e1_threshold_cut_met} -> PURSUE: {e1_decision}")
    print("-" * 80)
    print("STEP-TYPE CENSUS (E2):")
    for c in ("read_only", "test_run", "edit", "other"):
        b = e2_by_class[c]
        print(f"  {c:<10}: Step Share={b['step_share']*100:.2f}%, Total Cost Share={b['cost_share']*100:.2f}%")
    print(f"Routable Cost Share (read_only + test_run): {routable_cost_share*100:.2f}%")
    for k, rb in routing_bounds.items():
        print(f"  {k}: Theoretical Upper Bound={rb['theoretical_savings_upper_bound']*100:.2f}%, Cache-Aware Net={rb['cache_aware_net_savings']*100:.2f}%")
    print(f"E2 THRESHOLD EVALUATION: Routable Cost >= 40%: {e2_threshold_met} -> PURSUE: {e2_decision}")
    print(f"Results written to:     {out_file}")
    print(f"Compute Time:           {results['compute_time_seconds']:.2f}s")
    print("=" * 80)
    return results

if __name__ == "__main__":
    run_phase2_census(split_filter="dev")
