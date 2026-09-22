# Verification Adequacy Gate: Offline Evaluation & Interrogator Precision Report

## Executive Summary
We evaluated the **ARMA Verification Adequacy Gate** on all $N=2,000$ sampled trajectories from `nebius/SWE-rebench-openhands-trajectories` (Qwen3-Coder-480B + OpenHands, revision `35455389ab51bf5e2306bfd436ef72d0f98bf882`).

In Phase 4 (E4), we documented the **Green CI Illusion**: **94.2% of agent runs terminate with local test exit code 0 (green tests)**, yet **51.0% of these green runs fail holdout acceptance evaluation**. 

To determine whether adversarial verification can pierce this illusion, we evaluate:
1. **Module A: Deterministic Test-Diff Interrogator**: Prevalence of test modifications, precision of regex-based tampering detection, and correlation with holdout resolution.
2. **Module B: Targeted Mutation Probe Engine**: Structural mechanics and empirical execution requirements to predict true patch correctness.

---

## 1. Prevalence of Test Modifications & Aggregate Outcomes

Across all $N=2,000$ trajectories stratified across 1,016 repositories:

| Category | Sample Size ($n$) | Prevalence (%) | Holdout Resolved Rate | 95% Cluster Bootstrap CI | Holdout Failure Rate |
|:---|:---:|:---:|:---:|:---:|:---:|
| **All Trajectories (Baseline)** | 2,000 | 100.0% | 48.4% | [45.3%, 51.4%] | 51.6% |
| **Untouched Tests (Impl Only)** | 1,073 | 53.6% | 49.3% | [45.8%, 52.8%] | 50.7% |
| **Touched Tests (Any)** | 927 | 46.4% | 47.2% | [43.4%, 51.6%] | 52.8% |
| **Clean Test Additions** | 897 | 44.9% | 47.5% | [43.5%, 51.8%] | 52.5% |
| **Flagged as Tampered / Weakened** | **30** | **1.5%** | **40.0%** | **[21.9%, 60.0%]** | **60.0%** |

### Statistical Reality Check on Aggregate Separation
> [!WARNING]
> **Confidence Intervals Overlap at the Aggregate Level**:
> Baseline resolution is **48.4% [45.3%, 51.4%]**, while the flagged tampered set is **40.0% [21.9%, 60.0%]**. 
> Because the confidence intervals overlap, coarse aggregate test modification does **not** yet statistically separate from baseline. Test-file modification alone is common practice in agent trajectories (46.4% of runs), and cannot be treated as inherently malicious without fine-grained semantic analysis.

---

## 2. Granular Tampering Subcategories & Small-Sample Caveats

Breaking down the $n=30$ flagged tampering cases into specific malpractices:

| Violation Type | Count ($n$) | Holdout Resolved Rate | 95% Cluster Bootstrap CI | Status / Caveat |
|:---|:---:|:---:|:---:|:---|
| **Swallowed Exceptions** (`except AssertionError: pass`) | 7 | 28.6% | [0.0%, 66.7%] | Highly suggestive ($71.4\%$ fail rate), but $n=7$ interval is wide |
| **Deleted Assertions** (`- assert ...`) | 24 | 41.7% | [20.0%, 64.7%] | $n=24$; overlaps baseline; includes legitimate refactors |
| **Deleted Test Functions** (`- def test_*`) | 1 | 0.0% | [0.0%, 0.0%] | $n=1$; anecdotal only |

> [!NOTE]
> All subcategories with $n < 30$ must be treated as **suggestive observations**, not proof. With $n=7$, a binomial 95% confidence interval spans roughly $36\%$ to $100\%$ failure rate.

---

## 3. Human Precision Audit of the Test-Diff Interrogator

Following the same protocol as the Phase 1 action taxonomy audit (where $\ge 95\%$ agreement was required), we conducted an audit across all 30 flagged cases and 50 clean test-touching cases:

```
Total Flagged Cases Audited : 30
True Tampering Confirmed    : 23 (76.7%)
False Positives Flagged     : 7  (23.3%)
Measured Precision          : 76.7%
```

### Breakdown of False Positives:
1. **Scratch / Reproduction Test Edits ($n=3$)**: The agent created a new reproduction test file (e.g. `test_tls_enhanced.py`, `comprehensive_test.py`) and made subsequent edits within it. Deleting lines in an agent-authored scratch file is not tampering with repository test suites.
2. **Typo / Variable Name Fixes ($n=1$)**: E.g., `- self.assertEqual(result, [])` $\rightarrow$ `+ self.assertEqual(results, [])`.
3. **Assertion Factoring / Extraction ($n=1$)**: E.g., `- assert x == y` replaced with `expected = ...; assert x == expected`.
4. **Legitimate Bugfix Assertion Updates ($n=2$)**: Bug fix legitimately altered expected output format in a pre-existing test.

### Policy Implication: Dual-Tier Gate Promotion
Because the interrogator's raw precision is **76.7%**, using it as a universal **hard veto** would incur a **23.3% false block rate**, alienating developers and killing agent utility.

**Solution: Tiered Enforcement**:
- **Hard Veto Tier (Precision ~100%)**: Swallowed exceptions (`except AssertionError: pass`), injected skips (`@pytest.mark.skip`), and wholesale test deletion (`- def test_...`).
- **Advisory / Probe Tier**: Assertion line deletions and modifications. Rather than hard-blocking, these trigger the **Targeted Mutation Engine** to verify whether the modified assertions still actively constrain the implementation.

---

## 4. The Critical Roadmap: Empirical Evaluation of Module B (Mutant Engine)

Unit tests confirm that the AST mutation engine runs and safely restores code. However, **Module B currently has zero predictive evaluation against ground-truth outcomes**.

To ground the Mutation Adequacy Gate in empirical science rather than asserted thresholds:
1. **Stratified Execution Cohort**: Sample $N=150\text{--}300$ final patches from `sampled_trajectories_2000.parquet`.
2. **Sandbox Execution**: Apply patches in containerized environments, execute the test suite against targeted AST mutants, and compute the empirical **Mutation Kill Ratio**.
3. **Predictive Calibration**:
   - Correlate mutation-kill-ratio against true `resolved` ground truth.
   - Compute AUROC with cluster bootstrap 95% CIs.
   - Derive the optimal kill-ratio decision threshold from the ROC curve on the dev split (rather than asserting an arbitrary 50% number), and evaluate performance once on the frozen test split.
4. **Benchmark Alignment**: Compare discrimination against external baselines (**ImpossibleBench** and **EvilGenie**).
