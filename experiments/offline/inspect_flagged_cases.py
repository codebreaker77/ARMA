"""Audit each of the 30 flagged test-tampering cases to classify true tampering vs false positive."""

import json
import re

with open("experiments/offline/results/sample_test_diffs_for_human_audit.json", "r", encoding="utf-8") as f:
    data = json.load(f)

flagged = [d for d in data if d["interrogator_flag"] == "TAMPERING"]

print(f"Total Flagged Cases: {len(flagged)}\n")

for i, d in enumerate(flagged):
    print(f"=== Case {i+1}/{len(flagged)}: {d['instance_id']} ({d['repo']}) ===")
    print(f"Resolved: {d['resolved']}")
    print(f"Violations: {d['violation_snippets']}")
    print("--- Test Diff Snippet ---")
    lines = d["test_diff_full"].splitlines()
    # Print relevant hunk
    for l in lines[:25]:
        print("  " + l)
    if len(lines) > 25:
        print("  ... [truncated]")
    print("\n")
