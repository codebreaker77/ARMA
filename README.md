# ARMA: Autonomous Reliability & Metacognitive Architecture
### The Decision, Context, and Evidence Layer for Coding Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Architecture: Three--Plane](https://img.shields.io/badge/Architecture-Three--Plane-indigo.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Status: Phase--0--Active](https://img.shields.io/badge/Status-Phase--0--Active-success.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Local--First](https://img.shields.io/badge/Design-Local--First-black.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)

---

## Executive Summary

Autonomous coding agents (such as Claude Code, OpenCode, Aider, and SWE-agent) fail predominantly at a small set of recurring metacognitive decisions:
1. When to stop (premature exit vs. infinite looping).
2. What remains in scope (accidental refactoring outside the blast radius).
3. What commands are destructive (unrecoverable shell operations).
4. What information is worth preserving in context (preventing context degradation).

Today, these decisions are implicit, unmeasured, and uncalibrated. ARMA makes these decisions explicit, measures them against real-world execution outcomes, and continuously improves them using empirical data.

ARMA operates as a universal, local-first control plane between any coding agent harness and the target codebase.

---

## System Architecture: The Three Planes

```
 Claude Code / OpenCode / Aider / Codex / Custom Harness
        |
        +-- Native Lifecycle Hooks (Stop, PreToolUse, PostToolUse)
        +-- Universal Base-URL Proxy (127.0.0.1:4040)
        |
        v
+----------------------------- ARMA RUNTIME -----------------------------+
|                                                                         |
|  1. CONTEXT PLANE                                                       |
|     - Fullerenes Code Graph foundation (predict_impact integration)     |
|     - Wide retrieval with low-latency relevance filtering              |
|     - Tool output pruner (collapsing multi-thousand line logs)          |
|     - Pinned facts injector (countering middle-of-context burial)       |
|                                                                         |
|  2. DECISION PLANE (Hybrid Deterministic + Calibrated Middle)           |
|     - Stop Gate     : Blocks premature completion without verification  |
|     - Scope Gate    : Constrains edits to verified dependency bounds    |
|     - Risk Gate     : Hard deny policies + calibrated risk scoring      |
|     - Loop Detector : Detects thrashing and triggers git rollbacks      |
|                                                                         |
|     Promotion Ladder: Shadow -> Advisory -> Confirm -> Enforce          |
|                                                                         |
|  3. EVIDENCE PLANE (The Continuous Learning Engine)                     |
|     - Local SQLite datastore (sessions, events, decisions, outcomes)    |
|     - Counterfactual logging on every decision                          |
|     - Ground-truth labeling via test outcomes, git reverts, approvals   |
|     - Calibration tracking (Expected Calibration Error minimization)    |
|                                                                         |
+-------------------------------------------------------------------------+
        |
        v
  Pluggable Backend: MicroJev (Local) -> Jev (Cloud) -> Distilled Model
```

---

## Core Modules & Decision Invariants

ARMA enforces a strict architectural invariant: **Deterministic code computes anything exact; hard deny rules retain veto power; the classifier only judges the fuzzy middle.**

| Module | Deterministic Inputs | Classifier Question Primitives | Enforced Action |
| :--- | :--- | :--- | :--- |
| **Stop Gate** | Task checklist, exit codes, git diffstat, unhandled exceptions | `Noul` (requirement met probability), `Choice` (done / needs verification / incomplete / blocked) | Blocks premature agent exit with a concrete diagnostic rationale |
| **Scope Gate** | Task description, proposed file edit, Fullerenes impact graph closure | `Noul` (edit justified by task), `Score` (blast radius divergence 1-5) | Warns, prompts for confirmation, or blocks edits outside blast radius |
| **Risk Gate** | Shell command, working directory, git state, sandbox flags | `Choice` (read_only, recoverable, destructive, exfiltrating) | Executes instant deny on hard invariants; prompts confirmation on high-risk actions |
| **Loop Detector** | Rolling window of last N tool calls, diff hashes, and results | `Choice` (progressing, thrashing, blocked) | Triggers automated git stash reset and injects a strategic constraint |

---

## Promotion Ladder

To prevent premature disruption of developer workflows, every module advances through a formal promotion ladder based on empirical precision and calibration:

```
[ Shadow Mode ]  -------------------> [ Advisory Mode ] -------------------> [ Confirm Mode ] -------------------> [ Enforce Mode ]
Log decisions &                        Inject non-blocking                   Require explicit                      Actively block
counterfactuals to                     warnings into agent                   human approval for                    non-compliant actions
SQLite telemetry                       context window                        flagged operations                    with full authority
```

### Promotion Criteria
A module is promoted to `Enforce Mode` if and only if:
1. $N \ge 100$ labeled decisions are recorded in the Evidence Plane.
2. Measured Precision $\ge 0.96$ (False-block rate $\le 4\%$).
3. Expected Calibration Error (ECE) $\le 0.04$.

---

## The Evidence Plane: Ground-Truth Schema

ARMA maintains a local SQLite database recording all interactions, decisions, and real-world outcomes:

```sql
sessions(id, repo_path, harness, task_text, graph_version, started_at, ended_at, final_status)
events(id, session_id, turn, kind, tool_name, args_hash, raw_payload_summary, tokens_in, tokens_out)
decisions(id, event_id, module, question_type, question_text, answer_raw, probability, confidence,
          backend, model_version, threshold, mode, action_taken, counterfactual_action)
outcomes(id, decision_id, label, source, verified_at)
```

Ground-truth labels are derived automatically from:
- Test suite exit codes (`test_pass`, `test_fail`).
- Git history (`git_reverted`, `diff_survived`).
- Human developer actions (`user_approved`, `user_denied`).
- Issue tracking status (`task_resolved`).

---

## Phased Implementation Roadmap

```
Phase 0: Groundwork, Telemetry & Shadow Mode (Weeks 1-3)
├── SQLite Evidence Engine & Schema
├── Universal Interceptor Proxy (127.0.0.1:4040)
├── Native Hook Adapters (Claude Code, OpenCode)
└── Exit Criterion: 100% of local developer sessions captured in shadow mode

Phase 1: The Core Decision Plane (Weeks 3-8)
├── Stop, Scope, Risk, and Loop Gate implementation
├── Integration with local MicroJev / TypeSafe Jev
├── Automated precision & ECE calculation pipeline
└── Exit Criterion: Stop Gate false-stop rate below 5%

Phase 2: Context Plane & SWE-bench Verification (Weeks 8-16)
├── Fullerenes Code Graph integration (predict_impact)
├── Dynamic tool output pruner and Pinned Facts injector
├── Formal A/B evaluation on SWE-bench Verified
└── Exit Criterion: Token consumption reduced by >=40% with no loss in resolve rate

Phase 3: Model Distillation & Benchmark Release (Months 4-6)
├── Distill collected decision traces into a local 1.5B parameter model
├── Release the Agent Decision Benchmark (ADB)
└── Exit Criterion: Local distilled model matches cloud classifier F1 score

Phase 4: Enterprise Fleet Governance (Month 6+)
├── Cross-repo calibration and organizational policy synchronization
├── Cryptographic audit logging for SOC2 / ISO compliance
└── Exit Criterion: First production deployment across an enterprise engineering team
```

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.9 or higher
- Git
- Ollama (optional, for local System 1 embedding models)

### 2. Installation
```bash
git clone https://github.com/codebreaker77/ARMA.git
cd ARMA
pip install -e .
```

### 3. Launch the Interceptor Proxy
```bash
python -m layer.interceptor_proxy --port 4040
```

### 4. Attach to Any Coding Harness
To attach ARMA to any tool (Claude Code, OpenCode, Aider), set the base URL environment variable:

```bash
# For Anthropic-based harnesses (e.g., Claude Code)
export ANTHROPIC_BASE_URL="http://127.0.0.1:4040/v1"

# For OpenAI-compatible harnesses (e.g., OpenCode, Aider)
export OPENAI_BASE_URL="http://127.0.0.1:4040/v1"
```

### 5. Inspect Telemetry & Calibration
```bash
# View active sessions and gate status
python -m layer.cli status

# Live stream decisions and counterfactuals
python -m layer.cli tail

# Check precision, recall, and calibration error (ECE)
python -m layer.cli calibrate
```

---

## Repository Structure

```
ARMA/
├── README.md                      # Project documentation and architectural specification
├── setup.py                       # Package definition and dependencies
├── layer/                         # Core ARMA runtime
│   ├── __init__.py                # Package initialization
│   ├── evidence_db.py             # SQLite Evidence Plane implementation
│   ├── decision_engine.py         # Decision Plane gates, modules, and promotion ladder
│   ├── interceptor_proxy.py       # Universal HTTP reverse proxy
│   ├── harness_hooks.py           # Native lifecycle hooks for Claude Code / OpenCode
│   └── cli.py                     # Command-line dashboard and calibration tool
├── micro_jev.py                   # Local System 1 non-autoregressive decision engine
├── dual_process_pipeline.py       # System 1 (MicroJev) + System 2 (Gemma 3) reference pipeline
├── benchmark_comparison.py        # Empirical benchmark suite
├── jev_research/                  # Foundational research, papers, and Obsidian knowledge vault
└── tests/                         # Automated test suite
    ├── test_evidence_db.py        # Evidence Plane unit tests
    ├── test_decision_engine.py    # Decision Gates unit tests
    └── test_proxy.py              # Interceptor Proxy unit tests
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
