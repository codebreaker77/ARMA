# ARMA: Autonomous Reliability & Metacognitive Architecture
### The Decision, Context, and Evidence Layer for Coding Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Architecture: Three--Plane](https://img.shields.io/badge/Architecture-Three--Plane-indigo.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Status: Phase--3--Active](https://img.shields.io/badge/Status-Phase--3--Active-success.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Token--Compression: 75.7%](https://img.shields.io/badge/Token--Compression-75.7%25-brightgreen.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Calibrated--ECE: 0.0124](https://img.shields.io/badge/Calibrated--ECE-0.0124-blueviolet.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
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

# Optimize probability calibration (Temperature & Platt scaling)
python -m layer.cli optimize

# Replay historical traces through candidate policies
python -m layer.cli replay

# Export labeled decision traces into contrastive triplet datasets
python -m layer.cli export --format triplets --output data/triplets.jsonl
```

### 6. Run Benchmarks
```bash
# Phase 1: 50-scenario multi-language decision gate benchmark
python benchmark_phase1.py

# Phase 2: 10-suite SWE-bench context efficiency benchmark
python benchmark_phase2_efficiency.py

# Phase 3: Continuous learning, calibration & counterfactual replay benchmark
python benchmark_phase3_learning.py
```

---

## Context Plane & End-to-End Efficiency

The Context Plane eliminates two primary failure modes of long-running coding agents: **token bloat** (leading to excessive API costs and slow prompt evaluation) and **attention degradation** ("Lost in the Middle" phenomenon).

### Core Components

1. **Fullerenes Code Graph (`layer/code_graph.py`)**:
   - Parses AST structures across repository source trees.
   - Traces imports, class inheritance, function calls, and symbol dependencies.
   - Computes transitive dependency closures via `predict_impact()` to enforce blast radius bounds.

2. **Tool Output Pruner (`layer/context_plane.py`)**:
   - Inspects tool outputs (pytest logs, compiler diagnostics, large git diffs).
   - Extracts root-cause failure tracebacks and execution summaries while omitting repetitive passing dots and file listings.
   - Reduces raw tool output tokens by 70% to 90% with zero loss of diagnostic signal.

3. **Pinned Facts Manager (`layer/context_plane.py`)**:
   - Maintains a structured invariant block (active test status, files touched, verified blast radius, and requirement checklist).
   - Injects this block directly before the final prompt turn, ensuring the agent never "forgets" requirements or test outcomes.

4. **Compaction Scorer (`layer/context_plane.py`)**:
   - Scores conversation turns on a 1-5 scale to selectively preserve user intent, failures, and file write operations during historical context compaction.

### Empirical SWE-bench Benchmark Results

Tested across 10 multi-turn debugging sessions covering Django, Flask, FastAPI, Requests, Click, SymPy, Pandas, Scikit-Learn, Pytest, and SQLAlchemy:

| Metric | Target | Measured Result | Status |
| :--- | :--- | :--- | :--- |
| **Token Compression** | >= 50.0% | **75.67%** (39,362 -> 9,577 tokens) | Met |
| **Prompt Latency Reduction** | >= 40.0% | **64.32%** | Met |
| **Invariant Retention** | 100.0% | **100.0%** (0 lost invariants) | Met |
| **Transitive Impact Accuracy** | 100.0% | **100.0%** | Met |

---

## Continuous Learning & Counterfactual Replay (Phase 3)

Phase 3 closes the feedback loop between real execution outcomes in the **Evidence Plane** and future policy evaluations in the **Decision Plane**.

### Core Components

1. **Trace Replay Simulator (`layer/replay_engine.py`)**:
   - Replays historical agent decisions from SQLite against updated gate configurations or alternate models.
   - Evaluates counterfactual lift: measures how many premature stops or false alarms would have been eliminated before deploying policy changes.

2. **Parametric Temperature & Platt Scaling Optimizer (`layer/calibrator.py`)**:
   - Fits optimal temperature $T^*$ and Platt bias $b^*$ to align raw model probabilities with empirical accuracy:
     $$P_{\text{calibrated}} = \sigma\left(\frac{\text{logit}(P)}{T} + b\right)$$
   - Performs bounded search to minimize Expected Calibration Error (ECE) and find the optimal decision threshold $\tau^*$ maximizing $F_1$ while enforcing false-alarm constraints.
   - Persists parameters to `arma_calibration.json` for dynamic zero-restart reloading.

3. **Distillation Dataset Exporter (`layer/distill_exporter.py`)**:
   - Extracts verified execution decisions into contrastive triplet formats (`anchor`, `positive`, `negative`) for embedding fine-tuning.
   - Generates instruction-tuning datasets (Alpaca / ShareGPT format) for distilling small parameter models.

### Empirical Calibration & Replay Results

Evaluated across 50 diverse decision traces spanning all 4 gates:

| Metric | Baseline | Calibrated Candidate | Net Improvement |
| :--- | :--- | :--- | :--- |
| **Decision Accuracy** | 62.00% | **100.00%** | **+38.00% Net Lift** |
| **Expected Calibration Error (ECE)** | 0.2454 | **0.0124** | **94.9% Error Reduction** |
| **False Stops Permitted** | 14 | **0** | **14 False Alarms Eliminated** |
| **Distillation Triplets Generated** | 0 | **50** | **Verified ML Format** |

---

## Repository Structure

```
ARMA/
├── README.md                      # Project documentation and architectural specification
├── setup.py                       # Package definition and dependencies
├── arma_calibration.json          # Persisted calibrated temperatures and thresholds
├── benchmark_phase1.py            # 50-scenario multi-language gate decision benchmark
├── benchmark_phase2_efficiency.py # 10-suite SWE-bench context efficiency benchmark
├── benchmark_phase3_learning.py   # 50-trace continuous learning and replay benchmark
├── layer/                         # Core ARMA runtime
│   ├── __init__.py                # Package initialization
│   ├── evidence_db.py             # SQLite Evidence Plane implementation
│   ├── decision_engine.py         # Decision Plane gates, modules, and promotion ladder
│   ├── promotion_ladder.py        # Statistical promotion state machine (shadow -> enforce)
│   ├── gate_specs.py              # Standardized contrastive question templates
│   ├── code_graph.py              # Fullerenes AST parser and predict_impact engine
│   ├── context_plane.py           # ToolOutputPruner, PinnedFactsManager, CompactionScorer
│   ├── calibrator.py              # TemperatureScaler, ThresholdOptimizer, OfflineCalibrator
│   ├── replay_engine.py           # Trace Replay Simulator and counterfactual evaluator
│   ├── distill_exporter.py        # Triplet and instruction tuning dataset exporter
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
    ├── test_code_graph.py         # Fullerenes Code Graph unit tests
    ├── test_context_plane.py      # Context Plane unit tests
    └── test_replay.py             # Replay, Calibration, and DistillExporter unit tests
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


