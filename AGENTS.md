# ARMA Autonomous Reliability & Metacognitive Rules

These rules apply across all coding sessions in this repository.

## 1. Stop Gate Invariant
- An agent must NEVER declare a task fixed or complete unless:
  1. Tests have been executed and returned an exit code of 0.
  2. Git diff matches the scope of the stated problem.
  3. No unhandled syntax or runtime exceptions remain.

## 2. Scope Gate Invariant
- Before modifying existing modules, compute the Fullerenes AST blast radius.
- Keep edits tightly bounded within the dependency closure of the target bug or feature.
- Disallow editing unrelated infrastructure, authentication keys, or configuration files.

## 3. Risk Gate Invariant
- Hard deny patterns (e.g. `rm -rf /`, `DROP DATABASE`, `git push --force`) are blocked instantly.
- Always prefer recoverable operations over destructive ones.

## 4. Context Optimization Invariant
- Prune multi-hundred line pytest / compiler tracebacks using ARMA `ToolOutputPruner`.
- Maintain active test status and checklist items pinned at the context tail.
