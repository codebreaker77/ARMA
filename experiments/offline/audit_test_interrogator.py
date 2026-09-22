"""Audit TestDiffInterrogator across sampled 2,000 trajectories.

Evaluates how often agents weaken or modify existing test files,
and how these violations correlate with resolution status.
"""

import json
import os
import pandas as pd

from experiments.offline.config import SAMPLED_DATA_PATH, RESULTS_DIR
from layer.test_diff_interrogator import TestDiffInterrogator

def run_interrogator_audit():
    print("=" * 80)
    print("TEST-DIFF INTERROGATOR AUDIT ACROSS 2,000 TRAJECTORIES")
    print("=" * 80)

    df = pd.read_parquet(SAMPLED_DATA_PATH)
    interrogator = TestDiffInterrogator()

    total_patches = 0
    test_modifying_patches = 0
    clean_test_patches = 0
    violated_test_patches = 0

    violation_counts = {
        "ASSERTION_DELETED": 0,
        "ASSERTION_WEAKENED": 0,
        "SKIP_INJECTED": 0,
        "EXCEPTION_SWALLOWED": 0,
        "TEST_DELETED": 0,
    }

    violation_resolved_map = {k: {"resolved": 0, "unresolved": 0} for k in violation_counts}
    clean_resolved = 0
    clean_unresolved = 0

    for idx, row in df.iterrows():
        patch = row.get("model_patch") or ""
        res = int(row.get("resolved", 0))
        if not patch.strip():
            continue

        total_patches += 1
        report = interrogator.interrogate_diff(patch)

        if report.touches_test_files:
            test_modifying_patches += 1
            if report.is_adequate:
                clean_test_patches += 1
                if res == 1:
                    clean_resolved += 1
                else:
                    clean_unresolved += 1
            else:
                violated_test_patches += 1
                for v in report.violations:
                    v_type = v.violation_type
                    if v_type in violation_counts:
                        violation_counts[v_type] += 1
                        if res == 1:
                            violation_resolved_map[v_type]["resolved"] += 1
                        else:
                            violation_resolved_map[v_type]["unresolved"] += 1

    print(f"Total evaluated patches: {total_patches}")
    print(f"Patches touching test files: {test_modifying_patches} ({test_modifying_patches/total_patches*100:.1f}%)")
    print(f"  - Clean test additions (new tests, no weakening): {clean_test_patches} ({clean_test_patches/test_modifying_patches*100:.1f}%)")
    print(f"    * Resolution rate for clean additions: {clean_resolved/(clean_test_patches or 1)*100:.1f}%")
    print(f"  - Flagged for test-weakening / cheating: {violated_test_patches} ({violated_test_patches/test_modifying_patches*100:.1f}%)")
    print("\nBreakdown of Detected Violations:")
    for v_type, count in violation_counts.items():
        v_res = violation_resolved_map[v_type]["resolved"]
        v_unres = violation_resolved_map[v_type]["unresolved"]
        print(f"  - {v_type:<22}: {count:>4} occurrences (Resolved: {v_res}, Unresolved: {v_unres})")

    out_file = os.path.join(RESULTS_DIR, "interrogator_audit.json")
    results = {
        "total_patches": total_patches,
        "test_modifying_patches": test_modifying_patches,
        "clean_test_patches": clean_test_patches,
        "violated_test_patches": violated_test_patches,
        "clean_resolution_rate": clean_resolved / (clean_test_patches or 1),
        "violation_counts": violation_counts,
        "violation_resolved_map": violation_resolved_map,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved audit results to: {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    run_interrogator_audit()
