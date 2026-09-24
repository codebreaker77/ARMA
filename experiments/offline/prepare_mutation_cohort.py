"""Prepare an expanded stratified cohort of 350-400 instances for sandbox mutation evaluation."""

import json
import os
import pandas as pd
from datasets import load_dataset

from experiments.offline.config import (
    SAMPLED_DATA_PATH,
    DATA_DIR,
    RANDOM_SEED,
    is_dev_repo,
)

PURE_PYTHON_REPOS = [
    "tobymao/sqlglot",
    "asottile/pyupgrade",
    "reata/sqllineage",
    "asottile/add-trailing-comma",
    "marshmallow-code/apispec",
    "joke2k/faker",
    "encode/starlette",
    "omni-us/jsonargparse",
    "tefra/xsdata",
    "narwhals-dev/narwhals",
    "PyCQA/pyflakes",
    "getsentry/responses",
    "peterbe/hashin",
    "sqlfluff/sqlfluff",
    "pre-commit/pre-commit",
    "Fatal1ty/mashumaro",
    "python-cmd2/cmd2",
    "burnash/gspread",
    "oasis-open/cti-python-stix2",
    "networkx/networkx",
    "hgrecco/pint",
    "wemake-services/wemake-python-styleguide",
    "pypa/setuptools_scm",
    "frictionlessdata/frictionless-py",
]


def prepare_cohort():
    print("Loading trajectory data from sampled_trajectories_2000.parquet and rg0.parquet...")
    df1 = pd.read_parquet(SAMPLED_DATA_PATH)
    rg0_path = os.path.join(DATA_DIR, "rg0.parquet")
    if os.path.exists(rg0_path):
        df2 = pd.read_parquet(rg0_path)
        traj_df = pd.concat([df1, df2], ignore_index=True)
    else:
        traj_df = df1

    # Deduplicate by instance_id, preferring rows with non-empty model_patch
    traj_df = traj_df.sort_values(by="model_patch", key=lambda s: s.str.len(), ascending=False)
    traj_df = traj_df.drop_duplicates(subset=["instance_id"]).reset_index(drop=True)

    print(f"Total unique trajectories across datasets: {len(traj_df)}")

    print("Loading SWE-rebench metadata...")
    ds = load_dataset("nebius/SWE-rebench", split="test")
    bench_map = {x["instance_id"]: x for x in ds}

    # Load existing evaluated instances to guarantee 100% overlap
    results_path = os.path.join("experiments", "offline", "results", "mutation_eval_results.json")
    existing_iids = set()
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                existing_iids.add(item["instance_id"])
    print(f"Found {len(existing_iids)} already evaluated instances to preserve.")

    # Filter for candidate instances
    candidates = []
    seen_iids = set()

    # First add all existing evaluated instances if they have bench metadata
    for idx, row in traj_df.iterrows():
        iid = row["instance_id"]
        if iid in existing_iids and iid in bench_map and iid not in seen_iids:
            repo = row["repo"]
            patch = row.get("model_patch") or ""
            b_meta = bench_map[iid]
            candidates.append({
                "trajectory_id": row["trajectory_id"],
                "instance_id": iid,
                "repo": repo,
                "resolved": bool(row["resolved"]),
                "split": "dev" if is_dev_repo(repo) else "test",
                "base_commit": b_meta["base_commit"],
                "test_patch": b_meta.get("test_patch", ""),
                "fail_to_pass": b_meta.get("FAIL_TO_PASS", []),
                "pass_to_pass": b_meta.get("PASS_TO_PASS", []),
                "model_patch": patch,
                "patch_lines": len(patch.splitlines()),
            })
            seen_iids.add(iid)

    print(f"Added {len(candidates)} previously evaluated instances.")

    # Next add new pure-python candidates
    new_added = 0
    for idx, row in traj_df.iterrows():
        iid = row["instance_id"]
        if iid in seen_iids:
            continue
        repo = row["repo"]
        patch = row.get("model_patch") or ""
        if not patch.strip():
            continue
        if repo not in PURE_PYTHON_REPOS:
            continue
        if iid not in bench_map:
            continue

        b_meta = bench_map[iid]
        candidates.append({
            "trajectory_id": row["trajectory_id"],
            "instance_id": iid,
            "repo": repo,
            "resolved": bool(row["resolved"]),
            "split": "dev" if is_dev_repo(repo) else "test",
            "base_commit": b_meta["base_commit"],
            "test_patch": b_meta.get("test_patch", ""),
            "fail_to_pass": b_meta.get("FAIL_TO_PASS", []),
            "pass_to_pass": b_meta.get("PASS_TO_PASS", []),
            "model_patch": patch,
            "patch_lines": len(patch.splitlines()),
        })
        seen_iids.add(iid)
        new_added += 1

    print(f"Added {new_added} new candidate instances.")
    cand_df = pd.DataFrame(candidates)
    print(f"\nFinal Selected Cohort: N={len(cand_df)} instances")
    print(f"  - Dev instances : {(cand_df['split'] == 'dev').sum()}")
    print(f"  - Test instances: {(cand_df['split'] == 'test').sum()}")
    print(f"  - Resolved base rate: {cand_df['resolved'].mean()*100:.1f}%")
    print(f"  - Repositories: {cand_df['repo'].nunique()}")

    manifest_path = os.path.join(DATA_DIR, "mutation_eval_manifest.json")
    # Backup old manifest if not backed up
    bak_path = os.path.join(DATA_DIR, "mutation_eval_manifest_150.json.bak")
    if os.path.exists(manifest_path) and not os.path.exists(bak_path):
        os.rename(manifest_path, bak_path)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(cand_df.to_dict(orient="records"), f, indent=2)
    print(f"Saved expanded cohort manifest to {manifest_path}")


if __name__ == "__main__":
    prepare_cohort()
