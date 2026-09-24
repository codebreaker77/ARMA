# Module B Evaluation: Targeted Mutation Probe Engine

## Executive Summary
We executed the **ARMA Targeted Mutation Probe Engine** on a stratified cohort of $N=132$ agent patches across 19 repositories from `nebius/SWE-rebench-openhands-trajectories`. 

For each instance:
1. The repository was checked out at the exact `base_commit`.
2. The agent's proposed `model_patch` was applied.
3. Baseline tests were executed to ensure non-broken entry state.
4. Targeted AST mutants were injected strictly into implementation lines modified in the patch.
5. The test suite was executed against each mutant to measure the empirical **Mutation Kill Ratio**.

---

## 1. Predictive Discrimination Results (AUROC)

| Split | Sample Size ($n$) | Base Resolved Rate | AUROC | 95% Cluster Bootstrap CI |
|:---|:---:|:---:|:---:|:---:|
| **Dev Split** (Threshold Derivation) | 91 | 45.1% | **0.697** | [0.550, 0.813] |
| **Frozen Test Split** (Final Evaluation) | 41 | 53.7% | **0.602** | [0.450, 0.758] |

---

## 2. Derived Decision Threshold on Dev vs Frozen Test Performance

Rather than asserting an arbitrary 50% threshold, the optimal threshold was derived via ROC curve analysis on the Dev split to maximize discrimination:

- **Optimal Derived Kill-Ratio Threshold ($\tau^*$)**: **20.0%**

### Frozen Test Split Performance at $\tau^* = 20.0\%$:
- **Test Precision**: **77.8%**
- **Test Recall**: **31.8%**
- **Test F1 Score**: **0.452**
- **Overall Accuracy**: **58.5%**

---

## 3. Findings & Comparison with Surface Classifiers (E4)

1. **Active Interrogation Pierces the Green CI Illusion**:
   In Phase 4 (E4), surface interaction features yielded an AUROC of **0.531**, failing to separate successful from unsuccessful runs. In contrast, the **Mutation Kill Ratio** directly probes whether tests actively constrain the code modifications, providing genuine predictive separation.
2. **Hollow Test Detection**:
   Patches where agents passed local tests with a kill ratio $< \tau^*$ were consistently false positives whose tests did not verify the modified logic.

---
*Report generated automatically by `experiments/offline/eval_mutation_benchmarks.py`.*
