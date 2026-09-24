import json
import sys

with open("experiments/offline/results/sample_test_diffs_for_human_audit.json", "r", encoding="utf-8") as f:
    data = json.load(f)

flagged = [x for x in data if x["interrogator_flag"] == "TAMPERING"]

lines = []
lines.append("# Detailed Audit of 30 Flagged Interrogator Cases\n")

for i, x in enumerate(flagged):
    lines.append(f"## Case {i}: `{x['instance_id']}` ({x['repo']}) - Resolved: `{x['resolved']}`")
    lines.append(f"**Violations Flagged**: `{x['violation_types']}`")
    lines.append("\n```diff")
    lines.append(x["test_diff_full"])
    lines.append("```\n---\n")

with open("experiments/offline/results/AUDIT_CASES_DETAILED.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Wrote {len(flagged)} detailed cases to experiments/offline/results/AUDIT_CASES_DETAILED.md")
