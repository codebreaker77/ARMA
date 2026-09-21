# ARMA Agent Rules & Invariants

These rules govern agent behavior within the ARMA repository and any project utilizing the ARMA Metacognitive Layer.

## Core Rules

1. **Deterministic Verification Invariant**:
   - Never declare a coding task complete without running tests and verifying an exit code of 0.
   - If tests fail, diagnose the root cause before attempting random edits.

2. **Blast Radius Scope Limitation**:
   - Before modifying core architecture files, calculate the Fullerenes blast radius.
   - Restrict modifications strictly to files within the transitive dependency closure.
   - Never edit credentials, environment secrets, or external configs unless explicitly requested.

3. **Context Efficiency & Pruning**:
   - Do not inject multi-hundred line raw terminal or test outputs into the prompt.
   - Always prune verbose tool logs to essential failure assertions and execution summaries.

4. **Risk Gate & Destructive Command Veto**:
   - Destructive operations (force-pushing to git, recursive deletions outside temp directories, dropping database tables) are vetoed by default.
   - Always propose non-destructive alternatives (e.g. `git stash`, targeted file deletes).
