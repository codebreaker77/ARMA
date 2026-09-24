import json

with open("experiments/offline/results/sample_test_diffs_for_human_audit.json", "r", encoding="utf-8") as f:
    data = json.load(f)

flagged = [x for x in data if x["interrogator_flag"] == "TAMPERING"]

for i, x in enumerate(flagged):
    print("=" * 80)
    print(f"CASE {i}: {x['instance_id']} | Repo: {x['repo']} | Resolved: {x['resolved']}")
    print(f"Violations: {x['violation_types']}")
    print("-" * 40)
    print(x["test_diff_full"])
    print()
