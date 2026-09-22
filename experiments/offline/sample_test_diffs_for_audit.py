"""Extract and audit test diff samples for human-precision check on the interrogator.

Samples all flagged test-tampering cases (n=30) plus 50 clean test-addition cases
to evaluate precision, false discovery rate, and refactoring false-positives.
"""

import os
import re
import json
import pandas as pd
from typing import List, Dict, Any

from experiments.offline.config import SAMPLED_DATA_PATH, RESULTS_DIR, RANDOM_SEED
from layer.test_diff_interrogator import TestDiffInterrogator, TEST_FILE_PATTERN


def extract_test_diff_chunks(patch_text: str) -> str:
    """Extract only the diff chunks modifying test files."""
    if not patch_text:
        return ""
    blocks = re.split(r"(?=diff --git )", patch_text)
    test_blocks = []
    for block in blocks:
        header = re.search(r"diff --git a/(\S+) b/(\S+)", block)
        if header and TEST_FILE_PATTERN.search(header.group(2)):
            test_blocks.append(block.strip())
    return "\n\n".join(test_blocks)


def generate_audit_sample():
    df = pd.read_parquet(SAMPLED_DATA_PATH)
    interrogator = TestDiffInterrogator()

    flagged_records = []
    clean_records = []

    for idx, row in df.iterrows():
        patch = row.get("model_patch") or ""
        if not patch.strip():
            continue

        report = interrogator.interrogate_diff(patch)
        if not report.touches_test_files:
            continue

        test_diff = extract_test_diff_chunks(patch)
        record = {
            "index": idx,
            "instance_id": row["instance_id"],
            "repo": row["repo"],
            "resolved": bool(row["resolved"]),
            "interrogator_flag": "TAMPERING" if report.has_critical_weakening else "CLEAN",
            "violation_types": "; ".join([v.violation_type for v in report.violations]),
            "violation_snippets": " || ".join([f"{v.violation_type}: {v.snippet}" for v in report.violations[:3]]),
            "test_diff_preview": test_diff[:1500],  # preview of the diff
            "test_diff_full": test_diff,
        }

        if report.has_critical_weakening:
            flagged_records.append(record)
        else:
            clean_records.append(record)

    flagged_df = pd.DataFrame(flagged_records)
    clean_df = pd.DataFrame(clean_records).sample(n=min(50, len(clean_records)), random_state=RANDOM_SEED)

    combined_df = pd.concat([flagged_df, clean_df], ignore_index=True)
    combined_df["human_label"] = ""
    combined_df["human_rationale"] = ""

    out_csv = os.path.join(RESULTS_DIR, "sample_test_diffs_for_human_audit.csv")
    # Save CSV without full text to keep it readable, but keep preview
    export_df = combined_df.drop(columns=["test_diff_full"])
    export_df.to_csv(out_csv, index=False)
    print(f"Exported {len(combined_df)} test diff samples to {out_csv}")
    print(f"  - Flagged tampering cases: {len(flagged_df)}")
    print(f"  - Sampled clean additions : {len(clean_df)}")

    # Also save full JSON for automated inspection
    out_json = os.path.join(RESULTS_DIR, "sample_test_diffs_for_human_audit.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(combined_df.to_dict(orient="records"), f, indent=2)
    print(f"Saved complete audit dataset with full diffs to {out_json}")


if __name__ == "__main__":
    generate_audit_sample()
