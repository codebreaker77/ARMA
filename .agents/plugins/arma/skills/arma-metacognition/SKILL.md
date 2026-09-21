---
name: arma-metacognition
description: ARMA Metacognitive Architecture tool suite. Use to evaluate Stop invariants before completing tasks, compute transitive CodeGraph blast radii before editing code, prune verbose logs, and audit shell commands for destructive risk.
---

# ARMA Metacognitive Architecture Skill

Use this skill to interface with ARMA (Autonomous Reliability & Metacognitive Architecture).
ARMA provides deterministic invariants and calibrated evaluations for coding agents.

---

## Available Workflows

### 1. Pre-Flight Blast Radius Check (`arma_predict_impact`)
Before modifying, renaming, or refactoring an existing source file, check its Fullerenes dependency closure to understand what other modules, tests, or services will be impacted.

```json
{
  "target_file": "layer/decision_engine.py"
}
```

- **Output**: Returns `blast_radius_count` and the list of `impacted_files`.
- **Policy**: Avoid touching files outside this impact set unless explicitly requested by the user.

---

### 2. Destructive Shell Command Audit (`arma_audit_command`)
Before executing any shell command that deletes files, modifies git history, alters permissions, or drops database tables, run an audit check.

```json
{
  "command": "rm -rf build/ dist/",
  "cwd": "d:/labs/JEV"
}
```

- **Output**: Returns `is_safe` (boolean), `action` (`pass` or `block`), and the diagnostic `reason`.
- **Policy**: If `is_safe` is `false` or `action` is `block`, abort the command and propose a safe alternative.

---

### 3. Verbose Log Compression (`arma_prune_output`)
When a test runner (`pytest`, `unittest`, `cargo test`, `go test`) or compiler emits hundreds of lines of output, compress the log before placing it into the conversation context.

```json
{
  "raw_output": "<multi-thousand line pytest output>",
  "max_chars": 1200
}
```

- **Output**: Returns root-cause failure tracebacks, assertion messages, and summary lines, omitting repetitive passing dots and file listings with a 70-90% compression ratio.

---

### 4. Verified Completion Stop Check (`arma_check_stop`)
Before declaring a coding task finished or telling the user that a bug is fixed, run `arma_check_stop` to verify that test invariants and task criteria are met.

```json
{
  "task_text": "Fix atomic transaction rollback when IntegrityError is raised",
  "test_exit_code": 0,
  "test_output": "Ran 15 tests in 0.4s. OK",
  "diff_stat": "2 files changed, 14 insertions(+)"
}
```

- **Output**: Returns `allow_completion` (boolean), `action` (`pass`, `warn`, or `block`), and `reason`.
- **Policy**: If `allow_completion` is `false`, do not terminate; inspect the remaining failing requirements.
