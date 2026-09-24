"""Prepare a stratified cohort of 150-200 instances for sandbox mutation-kill-ratio evaluation."""

import json
import os
import pandas as pd
from datasets import load_dataset

from experiments.offline.config import (
    SAMPLED_DATA_PATH,
    RESULTS_DIR,
    RANDOM_SEED,
    is_dev_repo,
)

# High-density, fast pure-Python repositories suitable for deterministic local/sandbox testing
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
]


def prepare_cohort():
    print("Loading trajectory data...")
    traj_df = pd.read_parquet(SAMPLED_DATA_PATH)
    
    print("Loading SWE-rebench metadata...")
    ds = load_dataset("nebius/SWE-rebench", split="test")
    bench_map = {x["instance_id"]: x for x in ds}

    # Filter for instances with non-empty patch and belonging to pure-python repos
    candidates = []
    for idx, row in traj_df.iterrows():
        iid = row["instance_id"]
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

    cand_df = pd.DataFrame(candidates)
    print(f"Total pure-Python candidate instances with patches: {len(cand_df)}")
    print(f"  - Repositories: {cand_df['repo'].nunique()}")
    print(f"  - Resolved base rate: {cand_df['resolved'].mean()*100:.1f}%")
    print(f"  - Split distribution: {cand_df['split'].value_counts().to_dict()}")

    # Stratified sampling of N=150 (roughly 70% dev, 30% test)
    dev_cand = cand_df[cand_df["split"] == "dev"]
    test_cand = cand_df[cand_df["split"] == "test"]

    n_dev = min(105, len(dev_cand))
    n_test = min(45, len(test_cand))

    sample_dev = dev_cand.sample(n=n_dev, random_state=RANDOM_SEED)
    sample_test = test_cand.sample(n=n_test, random_state=RANDOM_SEED)

    selected_cohort = pd.concat([sample_dev, sample_test], ignore_index=True)
    n_total = len(selected_cohort)
    print(f"\nFinal Selected Cohort: N={n_total} instances")
    print(f"  - Dev instances : {len(sample_dev)}")
    print(f"  - Test instances: {len(sample_test)}")
    print(f"  - Resolved instances: {selected_cohort['resolved'].sum()} ({selected_cohort['resolved'].mean()*100:.1f}%)")

    manifest_path = os.path.join("experiments", "offline", "data", "mutation_eval_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(selected_cohort.to_dict(orient="records"), f, indent=2)
    print(f"Saved cohort manifest to {manifest_path}")

    # Print repo distribution
    print("\nRepo distribution in cohort:")
    print(selected_cohort["repo"].value_counts())


if __name__ == "__main__":
    prepare_cohort()
