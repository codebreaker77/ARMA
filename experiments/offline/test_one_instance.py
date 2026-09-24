"""Test single instance sandbox execution and mutation probe calculation."""

import os
import subprocess
import json
from layer.verification_gate import VerificationAdequacyGate

CACHE_DIR = os.path.abspath(os.path.join("experiments", "offline", "data", "repos_cache"))
os.makedirs(CACHE_DIR, exist_ok=True)

manifest_path = os.path.join("experiments", "offline", "data", "mutation_eval_manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    cohort = json.load(f)

PATCH_EXE = r"E:\Git\usr\bin\patch.exe" if os.path.exists(r"E:\Git\usr\bin\patch.exe") else "patch"

# Find tobymao__sqlglot-3855
inst = next(x for x in cohort if x["instance_id"] == "tobymao__sqlglot-3855")
print(f"Testing instance: {inst['instance_id']}")
print(f"Repo: {inst['repo']}, Base commit: {inst['base_commit']}, Resolved: {inst['resolved']}")

repo_dir = os.path.join(CACHE_DIR, "sqlglot")
if not os.path.exists(repo_dir):
    print("Cloning sqlglot with blobless filter...")
    subprocess.run(["git", "clone", "--filter=blob:none", f"https://github.com/{inst['repo']}.git", repo_dir], check=True)

# Fetch base_commit and checkout
print(f"Checking out base commit {inst['base_commit']}...")
subprocess.run(["git", "fetch", "--depth=1", "origin", inst["base_commit"]], cwd=repo_dir, check=False)
subprocess.run(["git", "checkout", "-f", inst["base_commit"]], cwd=repo_dir, check=True, capture_output=True)
subprocess.run(["git", "clean", "-fdx"], cwd=repo_dir, check=True, capture_output=True)

# Apply test_patch first if present so benchmark tests exist
if inst.get("test_patch"):
    print("Applying test_patch...")
    subprocess.run([PATCH_EXE, "-p1", "--ignore-whitespace", "-N"], cwd=repo_dir, input=inst["test_patch"], text=True, encoding="utf-8", capture_output=True)

# Apply model_patch with whitespace tolerance
print("Applying model_patch...")
p = subprocess.run([PATCH_EXE, "-p1", "--ignore-whitespace", "-N"], cwd=repo_dir, input=inst["model_patch"], text=True, encoding="utf-8", capture_output=True)
print("Git apply returncode:", p.returncode)
if p.returncode != 0:
    print("Git apply stderr:", p.stderr)

# Derive test command from fail_to_pass / pass_to_pass targets
test_files = set()
for t in inst.get("fail_to_pass", []) + inst.get("pass_to_pass", []):
    f_path = t.split("::")[0].strip()
    if f_path:
        test_files.add(f_path)

if not test_files:
    test_files = {"tests/"}

test_targets = " ".join(sorted(list(test_files)))
test_cmd = f"python -m pytest {test_targets} -q"
print(f"Derived test command: {test_cmd}")

gate = VerificationAdequacyGate(mutant_budget=5)
outcome = gate.verify_repository(
    repo_path=repo_dir,
    patch_text=inst["model_patch"],
    test_command=test_cmd,
    timeout_seconds=30
)

print("\n=== Verification Outcome ===")
print("Allow:", outcome.allow)
print("Stage:", outcome.stage)
print("Reason:", outcome.reason)
if outcome.mutation_result:
    m = outcome.mutation_result
    print(f"Total Mutants: {m.total_mutants}, Killed: {m.mutants_killed}, Ratio: {m.kill_ratio*100:.1f}%")
    for mut in m.mutants:
        print(f"  - [{ 'KILLED' if mut['killed'] else 'SURVIVED' }] {mut['description']}")
