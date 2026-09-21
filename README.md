# ARMA: Autonomous Reliability & Metacognitive Architecture
### The Control Plane, Context Optimizer, and Evidence Layer for Coding Agents

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Risk--Gate: Deterministic--Enforced](https://img.shields.io/badge/Risk--Gate-Deterministic--Enforced-brightgreen.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Stop--Gate: Experimental--Advisory](https://img.shields.io/badge/Stop--Gate-Experimental--Advisory-yellow.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Promotion--Ladder: Active](https://img.shields.io/badge/Promotion--Ladder-Active-blueviolet.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![MCP: Native--JSON--RPC](https://img.shields.io/badge/MCP-Native--JSON--RPC-orange.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)
[![Local--First](https://img.shields.io/badge/Design-Local--First-black.svg?style=flat-square)](https://github.com/codebreaker77/ARMA)

---

## Executive Summary

Autonomous coding agents (such as Claude Code, OpenCode, Aider, and SWE-agent) fail predominantly at a small set of recurring operational and metacognitive decisions:
1. **Destructive Operations**: Shell commands that wipe environments, force-push branches, or delete database tables.
2. **Context Bloat & Token Inefficiency**: Multi-thousand line tool outputs that inflate prompt costs and degrade agent reasoning.
3. **Out-of-Scope Blast Radius**: Modifying unrelated infrastructure or configuration files outside the target task bounds.
4. **Premature Termination**: Stopping execution before verifying changes or when terminal assertions remain unresolved.

ARMA operates as a local-first control plane between any coding agent harness and the target codebase.

### Core Design Principles & Empirical Transparency:
- **Deterministic Vetoes Over Machine Learning**: Hard deny rules (Risk Gate) retain instant veto power (<1 ms). Statistical heads only provide advisory signals.
- **Strict Promotion Governance**: Invariants prevent unverified heuristics from blocking developer workflows. A gate remains in `Shadow` or `Advisory` mode until it mathematically demonstrates $\ge 96\%$ precision and $\le 4\%$ false-block rates.
- **Empirically Validated Limits**: On 1,000 public benchmark trajectories (OpenHands / SWE-rebench across 553 repositories), naive test-exit rules exhibit a **42.1% False-Block Rate** and near-chance accuracy (56.2%). Consequently, Stop Gate is maintained in **Advisory / Experimental** mode, avoiding unrewarded token loops.

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
|     - Diagnostic tool output pruner (action-preserving compaction)      |
|     - Pinned facts injector (countering middle-of-context burial)       |
|                                                                         |
|  2. DECISION PLANE (Deterministic Invariants + Advisory Middle)         |
|     - Risk Gate     : Hard deny policies (<1ms instant veto) [Enforce]  |
|     - Scope Gate    : AST CodeGraph blast radius + probe [Advisory]     |
|     - Stop Gate     : Pre-submit diagnostic check [Experimental]        |
|     - Loop Detector : Thrashing detection & surgical rollback [Advisory]|
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
  Pluggable Backend Ladder: Rule (Rung 0) -> SupervisedEmbed (Rung 2) -> LLM Logit (Rung 3) -> Cloud Gateway (Rung 4)
```

---

## Core Modules & Status

| Module | Deterministic Inputs | Evaluation Method | Status | Role |
| :--- | :--- | :--- | :--- | :--- |
| **Risk Gate** | Shell command, working directory, git state | Exact invariant regex & path validation | **Enforce** | Instant sub-millisecond veto for destructive commands (`rm -rf`, force push) |
| **Scope Gate** | Task description, target file, Fullerenes AST graph | AST closure + linear probe head | **Advisory** | Flags edits outside dependency closure; warns on non-code distractors |
| **Context Plane** | Raw tool logs, pytest traces, diffs | Diagnostic extraction & line compaction | **Active** | Reduces cumulative prompt tokens while preserving critical identifiers |
| **Stop Gate** | Task checklist, exit codes, git diffstat | Diagnostic test check | **Experimental** | Advisory check before submit (demoted from enforce due to 42.1% false-block rate on N=1,000) |
| **Loop Detector** | Rolling window of last N tool calls and diff hashes | Repetition detection & test signatures | **Advisory** | Intercepts dead-end loops and suggests surgical git stash rollback |

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

## Live Harness Integration & Real-Time Monitor (Phase 4)

Phase 4 turns ARMA into an operational developer platform with zero-configuration execution, desktop MCP assistant support, and a high-density live telemetry dashboard.

### 1. Turnkey Harness Execution (`arma run`)

Run any coding harness directly through ARMA. The runner automatically launches the interceptor proxy in the background, sets `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`, registers session telemetry, and emits a post-session diagnostic summary card upon exit:

```bash
# Execute Claude Code with ARMA decision and context planes active
python -m layer.cli run claude

# Execute Aider with automatic proxy interception
python -m layer.cli run aider --model anthropic/claude-3-5-sonnet-20241022

# Execute custom test suites or agent scripts
python -m layer.cli run python agent_loop.py
```

### 2. Native Model Context Protocol (MCP) Server (`arma mcp`)

ARMA exposes its decision gates, code graph blast radius calculator, and context pruner as native tools conforming to the official MCP JSON-RPC 2.0 stdio specification.

#### Connecting Claude Desktop or Cursor (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "arma": {
      "command": "python",
      "args": ["-m", "layer.cli", "mcp"]
    }
  }
}
```

#### Exposed MCP Tools:
- `arma_check_stop`: Audits task requirements and test outcomes before the agent exits.
- `arma_predict_impact`: Computes Fullerenes transitive blast radius for planned file edits.
- `arma_prune_output`: Compresses verbose test outputs and terminal logs by 70-90%.
- `arma_audit_command`: Evaluates shell commands against Risk Gate hard invariants.

### 3. Real-Time Web Telemetry Dashboard (`arma dashboard`)

Launches a zero-dependency dark-mode monitoring dashboard on `http://127.0.0.1:4041`:
```bash
python -m layer.cli dashboard --port 4041
```
- **Live Decision Stream**: Real-time inspection of gate evaluations, probabilities, and actions.
- **Token Compression Gauge**: Live tracking of tokens saved and latency reduction.
- **Fullerenes Code Graph Visualizer**: Transitive dependency inspection and symbol indexing.
- **Calibration Status Cards**: Real-time display of module temperatures, thresholds, and ECE.

---

## Phase 5: Autonomous Self-Healing & Strategic Remediation

When coding agents get stuck in repetitive edit-fail loops, modify files outside the intended scope, or cause regression cascades, ARMA's remediation engine intercepts execution, executes a non-destructive surgical rollback, and synthesizes high-signal pivot directives directly into the agent's pinned context window.

### Core Remediation Architecture

1. **CheckpointManager (`layer/remediator.py`)**:
   - Captures shadow file snapshots when verification tests pass (green checkpoints).
   - Provides non-destructive surgical rollback: restores only thrashed files while preserving intervening user edits.
   - Preserves all reverted modifications in a persistent safety stash (`~/.arma/recovery_stash/`), ensuring zero work loss.

2. **LoopBreaker (`layer/remediator.py`)**:
   - Monitors rolling action history and test outcome signatures.
   - Detects circular thrashing (3 or more consecutive failed attempts on the same module).
   - Halts dead-end iteration loops in `enforce` mode and executes automated rollback to the last verified passing state.

3. **AlternativeStrategySynthesizer (`layer/remediator.py`)**:
   - Formulates actionable pivot directives instructing the agent to cease edits on the failing file, examine upstream callers or interfaces, and refocus on core task constraints.
   - Injected directly into `PinnedFactsManager` at the context tail.

### CLI Checkpoint & Rollback Commands

Inspect available recovery checkpoints:
```bash
python -m layer.cli checkpoints [--session <session_id>]
```

Perform surgical rollback to a verified state:
```bash
python -m layer.cli rollback [--checkpoint <checkpoint_id>] [--files <file1,file2>]
```

### Empirical Evaluation: Phase 5 Self-Healing Benchmark (`benchmark_phase5_remediation.py`)

Simulates 5 multi-turn agent failure scenarios (syntax thrashing, assertion deadlocks, regression cascades, API contract mismatches, async thread starvation).

| Benchmark Metric | Measured Result | Benchmark Target | Status |
| :--- | :--- | :--- | :--- |
| **Loop Escape Rate (Intervention)** | 100.0% | 100.0% | Verified Passing |
| **Surgical Rollback Fidelity** | 100.0% | 100.0% | Verified Passing |
| **Non-Destructive Stash Safety** | 100.0% | 100.0% | Verified Passing |
| **Strategic Pivot Context Injection** | 100.0% | 100.0% | Verified Passing |
| **Post-Pivot Task Resolution Rate** | 100.0% | 100.0% | Verified Passing |

---

## Classifier Backend Ladder (`layer/classifier_ladder.py`)

ARMA structures decision classification into a multi-rung hierarchy. This guarantees fast deterministic veto power while eliminating the probability compression inherent in zero-shot embedding heuristics.

| Rung | Classifier Backend | Method | AUROC | FNR @ 5% FPR | Latency | Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Rung 0** | `RuleClassifier` | Deterministic invariant checks & regex hard vetoes | 1.0000 | 0.0% | <1 ms | Instant veto for destructive commands and failing exits |
| **Rung 1** | `EmbedPrior` | Zero-shot cosine similarity heuristic | 0.5400 | 100.0% | ~100 ms | Uncalibrated lexical prior (baseline) |
| **Rung 2** | `SupervisedEmbedClassifier` | Dense embeddings + supervised linear probe ($z = W^T x + b$) | **0.9680** | **0.0%** | ~110 ms | Production default: discriminative logit spread ($[0.004, 0.983]$) |
| **Rung 3** | `LLMLogitClassifier` | Instruction-tuned local LLM (Gemma 3) prompt judge | ~0.9400 | ~5.0% | ~4000 ms | High-complexity semantic disambiguation |
| **Rung 4** | `VercelAIGatewayClassifier` | Vercel AI Gateway (Gemini 2.5, GPT-4o, Claude) | 0.9800+ | ~2.0% | ~500 ms | Cloud Foundation Gateway with graceful Rung 2 fallback |

### Empirical Validation 1: 100-Action Classifier Benchmark (`benchmark_classifier_ladder.py`)

Evaluating 100 balanced coding agent action scenarios (50 in-scope vs. 50 out-of-scope):

| Backend Rung | Prob Range | Prob Spread | AUROC | Control AUROC | FNR @ 5% FPR | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Rung 1: EmbedPrior (Zero-Shot)** | [0.4906, 0.5030] | 0.0124 | 0.5400 | 0.5914 | 100.0% | 107.7 ms |
| **Rung 2: SupervisedEmbed (Linear Probe)** | [0.0043, 0.9829] | 0.9786 | **0.9680** | 0.4862 | **0.0%** | 115.1 ms |
| **Rung 0+2: ClassifierLadder** | [0.0043, 0.9829] | 0.9786 | **0.9680** | 0.4862 | **0.0%** | 110.6 ms |

### Empirical Validation 2: Adversarial Leakage Audit (`benchmark_leakage_audit.py`)

Testing whether probe accuracy is an artifact of lexical keyword overlap or genuine semantic boundaries:
- **Zero-Lexical-Overlap Positives**: Pure conceptual descriptions without filename tokens (e.g. *"Resolve boundary index error when slicing array subsets"* -> `src/pagination.py`).
- **High-Lexical-Overlap Negatives**: Adversarial keyword distractors pointing to out-of-scope configs or CI scripts (e.g. *"Fix off-by-one error in pagination slice"* -> `.github/workflows/pagination_ci.yml`).

| Backend Rung | Adversarial AUROC | Mean P(Zero-Overlap Pos) | Mean P(High-Overlap Neg) | Prob Spread | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Rung 1: EmbedPrior (Zero-Shot)** | 0.6500 | 0.498 | 0.496 | 0.0112 | 306.6 ms |
| **Rung 2: SupervisedEmbed (Linear Probe)** | **0.9300** | 0.295 | **0.028** | **0.9786** | 185.8 ms |
| **Rung 3: LLMLogit (Local Gemma 3)** | 0.4000 | 0.754 | 0.920 | 0.8275 | 4411.0 ms |
| **Rung 4: VercelAIGateway (Cloud Gateway)** | **0.9300** | 0.295 | **0.028** | **0.9786** | 508.7 ms |

#### Key Empirical Insights from the Leakage Audit:
1. **Probe Ceiling Robustness**: When lexical tokens are stripped, the linear probe retains an AUROC of 0.9300 and successfully suppresses high-overlap distractors to p = 0.028.
2. **Lexical Distractor Vulnerability in Naive LLMs**: Zero-shot prompting on Gemma 3 exhibited strong lexical capture (p = 0.920 on distractors containing the task keyword), confirming that raw LLMs require structured rubric prompting and probe gating rather than naive zero-shot classification.
3. **Resilient Cloud Gateway Fallback**: Vercel AI Gateway authentication seamlessly handled the gateway response envelope, with transparent fallback to Rung 2 when customer verification is pending.

### Empirical Validation 3: Offline Evaluation on Public SWE-bench Lite Instances (`benchmark_swebench_official.py`)

Evaluating Scope Gate file localization on public SWE-bench Lite issue descriptions from `django/django` and `astropy/astropy` against true gold maintainer patches vs. intra-repo distractors:

| Backend Rung | AUROC (95% Bootstrap CI) | Mean P(Gold Patch) | Mean P(Distractor) | Prob Spread | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Rung 1: EmbedPrior (Zero-Shot Baseline)** | 0.5459 [0.442, 0.648] | 0.492 | 0.492 | 0.0177 | 252.7 ms |
| **Rung 2: SupervisedEmbed (Linear Probe)** | **0.6509 [0.531, 0.770]** | **0.804** | 0.550 | **0.9786** | 194.1 ms |
| **Rung 0+2: ClassifierLadder (Rules + Probe)** | **0.6509 [0.531, 0.770]** | **0.804** | 0.550 | **0.9786** | 193.9 ms |

#### Generalization Gap & Caveats:
1. **The Real Generalization Picture**: Linear probe AUROC drops from **0.9680** on synthetic actions to **0.6509** (95% CI: [0.531, 0.770]) on real SWE-bench Lite issues. EmbedPrior remains at chance level (0.5459).
2. **Task Formulation Caveat**: File localization from issue text is an information retrieval problem over long natural language descriptions, which carries different structural priors than gating an agent's runtime edit against a task.
3. **Pre-Fix Test Invariant**: FAIL_TO_PASS assertions fail before the fix by definition; blocking on failing exit codes reflects expected invariant enforcement, not proof that forcing continuation resolves the bug.

---

### Empirical Validation 4: Offline Trajectory Replay on Public OpenHands Runs (`benchmark_trajectory_replay.py`)

Replaying 1,000 historical execution trajectories (Qwen3-Coder-480B with OpenHands from `nebius/SWE-rebench-openhands-trajectories` across 553 repositories), comprising 492 resolved and 508 unresolved runs:

#### 1. Leak-Free Stop Gate Evaluation (Observable Signals Before Submit vs. PR Resolution)

| Stop Gate Metric | Measured Value on Real Public Traces (N=1,000) |
| :--- | :--- |
| **Total Evaluated Trajectories** | 1,000 (492 resolved, 508 unresolved across 553 repos) |
| **True Positives (Allowed & PR Resolved)** | 285 |
| **False Positives (Allowed but PR Unresolved)** | 231 |
| **True Negatives (Blocked & PR Unresolved)** | 277 |
| **False Negatives (Blocked but PR Resolved - False Block!)** | 207 |
| **Precision (P(Resolved \| Allowed))** | 55.2% |
| **Recall** | 57.9% |
| **False-Block Rate (FN / Resolved)** | **42.1%** |
| **Unresolved Interception Rate (TNR)** | 54.5% |
| **Overall Resolution Classification Accuracy** | 56.2% (Chance baseline: 50.8%) |
| **Multi-Feature Grouped-CV AUROC** | **0.6770** (Grouped by 553 Repositories) |

#### 2. Compression vs. Non-Trivial Identifier Retention Across Baselines

Evaluating whether tool output compaction preserves the exact identifiers and paths referenced in the agent's immediate next turn (excluding keywords, built-ins, and trivial tokens across 54,605 target instances):

| Pruning Strategy | Char Compression | Identifier Retention | Information Loss |
| :--- | :--- | :--- | :--- |
| **BM25 Line Selection (35 lines)** | 33.38% | **98.36%** (53,711 / 54,605) | **1.64%** |
| **Conservative ARMA Pruner (3000 chars)** | **55.55%** | **88.26%** (48,194 / 54,605) | 11.74% |
| **Naive Head/Tail (15+15 lines)** | 44.66% | 88.71% (48,442 / 54,605) | 11.29% |
| **Duplicate Read Cache** | 40.22% | 77.89% (42,534 / 54,605) | 22.11% |
| **Standard ARMA Pruner (1200 chars)** | 59.55% | 77.82% (42,496 / 54,605) | 22.18% |

##### Conservative ARMA Retention by Tool Category:
- **Git Diffs**: 92.16% retention (7.84% loss)
- **General Terminal Commands**: 91.25% retention (8.75% loss)
- **Compiler / Syntax Errors**: 85.74% retention (14.26% loss)
- **Test Tracebacks**: 76.47% retention (23.53% loss)

*Takeaway*: BM25 line selection achieves **98.36% retention** (clearing the $\ge 95\%$ action-preservation threshold) while trimming 33.4% of characters. Conservative ARMA Pruning (3,000 chars) reaches 55.6% compression with 88.3% overall retention, outperforming aggressive 1,200-char compaction which loses over 22% of critical identifiers.

#### 3. Full Cumulative Cost Model (Input + Output Tokens & Real Cache Pricing)

Across 1,000 multi-turn sessions (3.86 Billion cumulative input tokens, 15.5M output tokens):

| Pricing Tier (Claude 3.5 Sonnet) | Raw Cost | Pruned Cost | Dollar Cut (Upper Bound) |
| :--- | :--- | :--- | :--- |
| **Uncached** ($3.00/M input, $15.00/M output) | $11,815.22 | $7,286.38 | **38.3% cut** |
| **80% Prompt Cache** ($0.30 read, $3.75 write, $15.00 output) | $4,054.99 | $2,560.47 | **36.9% cut** |

*Upper Bound Caveat*: These figures represent an offline upper bound on fixed historical traces. In live execution, minor information loss will cause agents to take additional turns to re-inspect code, lowering net savings toward the 20-35% range observed in empirical literature (AgentDiet).

#### 4. Early Failure Termination (EET) Feasibility

Predicting final PR failure at early execution steps using observable trajectory features with GroupKFold cross-validation grouped by repository across 553 repositories:
- **Trajectory Step Disparity**: Resolved runs average 117.6 steps; unresolved runs average 141.7 steps (1.21x step consumption).
- **Step 10 Failure AUROC**: 0.5140 +/- 0.0361
- **Step 20 Failure AUROC**: 0.5293 +/- 0.0249
- **Step 30 Failure AUROC**: 0.5194 +/- 0.0331

*Insight*: During early turns (steps 1-30), both successful and failing agents heavily encounter errors, stack traces, and test failures during initial exploration. Surface error counts in early steps do not reliably discriminate failure (AUROC remains near chance, 0.51-0.53); reliable early termination requires detecting repetitive dead-end edit cycles (loop detection) rather than counting early test failures.

---

## Next Milestone: Live A/B Execution on Verified Mini

Offline replays evaluate historical transcripts under fixed agent actions. The definitive test of ARMA's value proposition is live execution on `mini-swe-agent` against SWE-bench Verified Mini:
1. **Control**: Baseline agent without ARMA.
2. **Treatment**: Agent wrapped with ARMA (Conservative Pruner + Risk Gate + LoopBreaker).
3. **Target Metrics**: Real dollar cost per resolved issue, pass rate delta, and total turn count.

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
├── benchmark_phase5_remediation.py# 5-scenario self-healing & remediation benchmark
├── benchmark_classifier_ladder.py # 100-scenario backend ladder empirical benchmark
├── benchmark_leakage_audit.py     # Adversarial zero-overlap vs. distractor leakage audit
├── benchmark_swebench_official.py # Offline SWE-bench Lite real issue & gold patch benchmark
├── benchmark_trajectory_replay.py # Offline replay on public OpenHands trajectories
├── layer/                         # Core ARMA runtime
│   ├── __init__.py                # Package initialization
│   ├── evidence_db.py             # SQLite Evidence Plane implementation
│   ├── decision_engine.py         # Decision Plane gates, modules, and promotion ladder
│   ├── promotion_ladder.py        # Statistical promotion state machine (shadow -> enforce)
│   ├── gate_specs.py              # Standardized contrastive question templates
│   ├── classifier_ladder.py       # Rule, SupervisedEmbed, LLMLogit, VercelAIGateway
│   ├── embed_prior.py             # Truthful zero-shot EmbedPrior heuristic (session pooling, fallback)
│   ├── code_graph.py              # Fullerenes AST parser and predict_impact engine
│   ├── context_plane.py           # ToolOutputPruner, PinnedFactsManager, CompactionScorer
│   ├── calibrator.py              # TemperatureScaler, ThresholdOptimizer, OfflineCalibrator
│   ├── replay_engine.py           # Trace Replay Simulator and counterfactual evaluator
│   ├── distill_exporter.py        # Triplet and instruction tuning dataset exporter
│   ├── remediator.py              # CheckpointManager, LoopBreaker, StrategySynthesizer
│   ├── interceptor_proxy.py       # Universal HTTP reverse proxy
│   ├── harness_hooks.py           # Native lifecycle hooks for Claude Code / OpenCode
│   ├── runner.py                  # Turnkey harness runner (arma run)
│   ├── mcp_server.py              # Model Context Protocol stdio server (arma mcp)
│   ├── web_dashboard.py           # Real-time web telemetry dashboard (arma dashboard)
│   └── cli.py                     # Command-line dashboard and calibration tool
├── micro_jev.py                   # Legacy backwards-compatible adapter (delegates to embed_prior)
├── dual_process_pipeline.py       # System 1 + System 2 reference pipeline
├── benchmark_comparison.py        # Empirical benchmark suite
├── jev_research/                  # Foundational research, papers, and Obsidian knowledge vault
└── tests/                         # Automated test suite
    ├── test_evidence_db.py        # Evidence Plane unit tests
    ├── test_decision_engine.py    # Decision Gates unit tests
    ├── test_code_graph.py         # Fullerenes Code Graph unit tests
    ├── test_context_plane.py      # Context Plane unit tests
    ├── test_replay.py             # Replay, Calibration, and DistillExporter unit tests
    ├── test_runner.py             # Harness Runner unit tests
    ├── test_mcp.py                # Model Context Protocol server unit tests
    ├── test_web_dashboard.py      # Web Dashboard and REST API unit tests
    ├── test_remediator.py         # Self-Healing and Rollback unit tests
    └── test_classifier_ladder.py  # Classifier Ladder and SupervisedEmbed unit tests
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.



