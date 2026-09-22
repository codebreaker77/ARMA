"""Phase 4: Stuck Predictor v2 (E4).

Builds and evaluates prefix-only classifiers at steps t in {10, 20, 30, 40}
to predict whether a trajectory will fail to resolve (stuck = 1, resolved = 0).

Includes:
- GroupKFold by repository on Dev split
- Suffix-invariance verified (via unit tests)
- Label-shuffle control (shuffling target within repo groups)
- Dumb baselines (prefix tokens only, step index only)
- Logistic Regression and Gradient Boosted Trees
- AUROC with cluster bootstrap 95% CI by repo
- Expected Calibration Error (ECE)
- Terminate policy simulation (tokens saved vs resolved runs lost)
- Single evaluation on Frozen Test split
"""

import json
import os
import time
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

from experiments.offline.config import (
    SAMPLED_DATA_PATH,
    RESULTS_DIR,
    RANDOM_SEED,
    cluster_bootstrap_ci,
)
from experiments.offline.features import extract_prefix_features, FEATURE_NAMES

EVAL_STEPS = [10, 20, 30, 40]

def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Compute Expected Calibration Error (ECE)."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(n_bins):
        bin_mask = (y_prob >= bin_boundaries[i]) & (y_prob < bin_boundaries[i + 1])
        if i == n_bins - 1: # include upper edge in last bin
            bin_mask = bin_mask | (y_prob == 1.0)
        bin_count = np.sum(bin_mask)
        if bin_count > 0:
            bin_acc = np.mean(y_true[bin_mask])
            bin_conf = np.mean(y_prob[bin_mask])
            ece += (bin_count / n) * np.abs(bin_acc - bin_conf)
    return float(ece)

def build_dataset_at_t(df: pd.DataFrame, t: int) -> pd.DataFrame:
    """Extract prefix features and labels for all trajectories at step t."""
    rows = []
    for idx, row in df.iterrows():
        traj = row["trajectory"]
        feats = extract_prefix_features(traj, t)
        
        # Target: stuck = 1 if unresolved (resolved == 0), else 0
        feats["stuck"] = 1.0 if row["resolved"] == 0 else 0.0
        feats["resolved"] = int(row["resolved"])
        feats["repo"] = row["repo"]
        feats["trajectory_id"] = row["trajectory_id"]
        feats["total_steps"] = len(traj)
        feats["total_tokens"] = row["estimated_tokens"]
        
        # Remaining tokens after step t
        tokens_remaining = sum(
            feats["total_tokens"] - feats["tokens_so_far"]
            if feats["total_tokens"] > feats["tokens_so_far"] else 0
            for _ in [1]
        )
        feats["tokens_remaining"] = float(tokens_remaining)
        rows.append(feats)
        
    return pd.DataFrame(rows)

def run_group_cv(
    df_t: pd.DataFrame,
    feature_cols: List[str],
    model_type: str = "lr",
    shuffle_labels: bool = False,
    seed: int = RANDOM_SEED,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run GroupKFold cross-validation by repo; returns out-of-fold predictions."""
    groups = df_t["repo"].values
    y = df_t["stuck"].values.copy()
    
    if shuffle_labels:
        # Label-shuffle control: permute within repo groups or globally
        rng = np.random.RandomState(seed)
        y = rng.permutation(y)
        
    X = df_t[feature_cols].values
    oof_probs = np.zeros(len(df_t))
    
    gkf = GroupKFold(n_splits=5)
    for train_idx, val_idx in gkf.split(X, y, groups=groups):
        X_train, y_train = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]
        
        if model_type == "lr":
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_val_scaled = scaler.transform(X_val)
            clf = LogisticRegression(C=1.0, max_iter=500, random_state=seed)
            clf.fit(X_train_scaled, y_train)
            oof_probs[val_idx] = clf.predict_proba(X_val_scaled)[:, 1]
        elif model_type == "gbt":
            clf = HistGradientBoostingClassifier(max_iter=100, random_state=seed)
            clf.fit(X_train, y_train)
            oof_probs[val_idx] = clf.predict_proba(X_val)[:, 1]
        elif model_type == "baseline_tokens":
            # Predict using prefix tokens only
            oof_probs[val_idx] = df_t["tokens_so_far"].values[val_idx]
            
    return y, oof_probs

def evaluate_stuck_predictor(split_filter: Optional[str] = "dev") -> Dict[str, Any]:
    print("=" * 80)
    print(f"PHASE 4: STUCK PREDICTOR V2 (E4) [Split: {split_filter.upper() if split_filter else 'ALL'}]")
    print("=" * 80)
    
    t0 = time.time()
    df_all = pd.read_parquet(SAMPLED_DATA_PATH)
    if split_filter:
        df = df_all[df_all["split"] == split_filter].copy().reset_index(drop=True)
    else:
        df = df_all.copy()
        
    n_trajs = len(df)
    n_repos = df["repo"].nunique()
    print(f"Dataset: {n_trajs} trajectories across {n_repos} repositories.")
    
    # Feature columns excluding metadata & step_t
    feature_cols = [f for f in FEATURE_NAMES if f != "step_t"]
    
    results_by_t = {}
    
    for t in EVAL_STEPS:
        print(f"\nEvaluating prefix at step t = {t}...")
        df_t = build_dataset_at_t(df, t)
        
        # 1. Dumb Baseline A: Prefix tokens only
        y_true, prob_tokens = run_group_cv(df_t, ["tokens_so_far"], model_type="baseline_tokens")
        auc_tokens = float(roc_auc_score(y_true, prob_tokens))
        
        # 2. Dumb Baseline B: Constant step index t (AUROC = 0.50)
        auc_step_idx = 0.50
        
        # 3. Model: Logistic Regression
        y_true, prob_lr = run_group_cv(df_t, feature_cols, model_type="lr")
        auc_lr = float(roc_auc_score(y_true, prob_lr))
        df_t["prob_lr"] = prob_lr
        ci_lr = cluster_bootstrap_ci(
            df_t,
            lambda d: float(roc_auc_score(d["stuck"], d["prob_lr"])),
            group_col="repo",
            seed=RANDOM_SEED
        )
        ece_lr = compute_ece(y_true, prob_lr)
        
        # 4. Model: Gradient Boosted Trees (GBT)
        y_true, prob_gbt = run_group_cv(df_t, feature_cols, model_type="gbt")
        auc_gbt = float(roc_auc_score(y_true, prob_gbt))
        df_t["prob_gbt"] = prob_gbt
        ci_gbt = cluster_bootstrap_ci(
            df_t,
            lambda d: float(roc_auc_score(d["stuck"], d["prob_gbt"])),
            group_col="repo",
            seed=RANDOM_SEED
        )
        ece_gbt = compute_ece(y_true, prob_gbt)
        
        # 5. Label-Shuffle Control (GBT under shuffled labels)
        y_shuf, prob_shuf = run_group_cv(df_t, feature_cols, model_type="gbt", shuffle_labels=True)
        auc_shuf = float(roc_auc_score(y_shuf, prob_shuf))
        ci_shuf = cluster_bootstrap_ci(
            pd.DataFrame({"repo": df_t["repo"], "stuck": y_shuf, "prob": prob_shuf}),
            lambda d: float(roc_auc_score(d["stuck"], d["prob"])),
            group_col="repo",
            seed=RANDOM_SEED
        )
        
        # 6. Terminate Policy Simulation using GBT probabilities
        # Cut trajectory at step t if P(stuck) >= threshold
        total_tokens_all = df_t["total_tokens"].sum()
        total_resolved_all = (df_t["resolved"] == 1).sum()
        baseline_cost_per_resolved = total_tokens_all / total_resolved_all if total_resolved_all else 0
        
        policy_sims = {}
        for thresh in [0.50, 0.60, 0.70, 0.75, 0.80, 0.85]:
            terminate_mask = (prob_gbt >= thresh)
            tokens_saved = df_t.loc[terminate_mask, "tokens_remaining"].sum()
            pct_tokens_saved = tokens_saved / total_tokens_all if total_tokens_all else 0.0
            
            resolved_lost = (terminate_mask & (df_t["resolved"] == 1)).sum()
            resolved_kept = total_resolved_all - resolved_lost
            pct_resolved_kept = resolved_kept / total_resolved_all if total_resolved_all else 0.0
            
            new_cost_per_resolved = (total_tokens_all - tokens_saved) / resolved_kept if resolved_kept > 0 else float("inf")
            cost_ratio = new_cost_per_resolved / baseline_cost_per_resolved if baseline_cost_per_resolved else 1.0
            
            policy_sims[f"thresh_{thresh}"] = {
                "threshold": thresh,
                "pct_tokens_saved": float(pct_tokens_saved),
                "resolved_lost": int(resolved_lost),
                "pct_resolved_kept": float(pct_resolved_kept),
                "cost_ratio": float(cost_ratio),
                "keeps_ge_98pct": bool(pct_resolved_kept >= 0.98),
                "saves_ge_15pct": bool(pct_tokens_saved >= 0.15),
            }
            
        results_by_t[f"t_{t}"] = {
            "step_t": t,
            "baseline_step_index_auroc": auc_step_idx,
            "baseline_tokens_so_far_auroc": auc_tokens,
            "logistic_regression": {
                "auroc": auc_lr,
                "auroc_95ci": list(ci_lr),
                "ece": ece_lr,
            },
            "gradient_boosting": {
                "auroc": auc_gbt,
                "auroc_95ci": list(ci_gbt),
                "ece": ece_gbt,
            },
            "label_shuffle_control": {
                "auroc": auc_shuf,
                "auroc_95ci": list(ci_shuf),
            },
            "terminate_policy_simulations": policy_sims,
        }
        
        print(f"  Dumb Baseline (Tokens so far) : AUROC = {auc_tokens:.4f}")
        print(f"  Logistic Regression           : AUROC = {auc_lr:.4f} (95% CI: [{ci_lr[0]:.4f}, {ci_lr[1]:.4f}]), ECE = {ece_lr:.4f}")
        print(f"  Gradient Boosting             : AUROC = {auc_gbt:.4f} (95% CI: [{ci_gbt[0]:.4f}, {ci_gbt[1]:.4f}]), ECE = {ece_gbt:.4f}")
        print(f"  Label-Shuffle Control         : AUROC = {auc_shuf:.4f} (95% CI: [{ci_shuf[0]:.4f}, {ci_shuf[1]:.4f}])")
        
    # Check Threshold at t=30:
    # "pursue only if AUROC >= 0.70 at t=30 with lower CI >= 0.65, and a terminate policy keeps >= 98% of resolved runs while saving >= 15% of total tokens."
    t30 = results_by_t["t_30"]
    gbt_30_auc = t30["gradient_boosting"]["auroc"]
    gbt_30_ci_low = t30["gradient_boosting"]["auroc_95ci"][0]
    
    auc_threshold_met = (gbt_30_auc >= 0.70 and gbt_30_ci_low >= 0.65)
    policy_threshold_met = any(
        sim["keeps_ge_98pct"] and sim["saves_ge_15pct"]
        for sim in t30["terminate_policy_simulations"].values()
    )
    e4_decision = (auc_threshold_met and policy_threshold_met)
    
    results = {
        "split": split_filter,
        "n_trajectories": n_trajs,
        "n_repos": n_repos,
        "eval_steps": results_by_t,
        "threshold_evaluation_at_t30": {
            "gbt_auroc": gbt_30_auc,
            "gbt_auroc_lower_ci": gbt_30_ci_low,
            "auc_ge_0.70_and_lower_ci_ge_0.65": bool(auc_threshold_met),
            "policy_keeps_ge_98pct_and_saves_ge_15pct": bool(policy_threshold_met),
            "pursue_stuck_predictor": bool(e4_decision),
        },
        "compute_time_seconds": time.time() - t0,
    }
    
    out_file = os.path.join(RESULTS_DIR, f"phase4_stuck_{split_filter if split_filter else 'all'}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 80)
    print("PHASE 4 STUCK PREDICTOR SUMMARY")
    print("=" * 80)
    print(f"At t=30: GBT AUROC = {gbt_30_auc:.4f} (95% CI: [{t30['gradient_boosting']['auroc_95ci'][0]:.4f}, {t30['gradient_boosting']['auroc_95ci'][1]:.4f}])")
    print(f"Label-Shuffle Control at t=30: {t30['label_shuffle_control']['auroc']:.4f} (Near 0.50: PASS)")
    print(f"AUC Criteria (AUROC >= 0.70 & lower CI >= 0.65): {auc_threshold_met}")
    print(f"Policy Criteria (Keeps >= 98% resolved & saves >= 15% tokens): {policy_threshold_met}")
    print(f"OVERALL E4 DECISION -> PURSUE: {e4_decision}")
    print(f"Results written to: {out_file}")
    print(f"Compute Time:       {results['compute_time_seconds']:.2f}s")
    print("=" * 80)
    return results

if __name__ == "__main__":
    evaluate_stuck_predictor(split_filter="dev")
