"""ARMA Verification Adequacy Gate.

Interrogates agent proof before approving completion:
1. Deterministic Test-Diff Interrogation:
   Checks if the diff deletes assertions, injects skips, or swallows exceptions.
2. Targeted Mutation Probes:
   Injects AST mutants into the implementation diff. Interrogates whether
   the agent's tests fail on mutated code (discriminating correct from broken logic).
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
import os

from layer.test_diff_interrogator import TestDiffInterrogator, InterrogationReport
from layer.mutant_engine import MutantEngine, CodeMutant


@dataclass
class MutationProbeResult:
    total_mutants: int = 0
    mutants_killed: int = 0
    mutants_survived: int = 0
    kill_ratio: float = 1.0
    mutants: List[Dict[str, Any]] = field(default_factory=list)
    adequacy_passed: bool = True
    summary: str = "No mutants evaluated."


@dataclass
class VerificationOutcome:
    allow: bool
    stage: str # 'test_diff_audit', 'mutation_probe', 'verified'
    reason: str
    interrogation_report: Optional[InterrogationReport] = None
    mutation_result: Optional[MutationProbeResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allow": self.allow,
            "stage": self.stage,
            "reason": self.reason,
            "interrogation": self.interrogation_report.summary() if self.interrogation_report else None,
            "mutation_probe": self.mutation_result.summary if self.mutation_result else None,
        }


class VerificationAdequacyGate:
    """Metacognitive gate verifying that agent tests are trustworthy and discriminating."""

    def __init__(
        self,
        min_mutation_kill_ratio: float = 0.50,
        mutant_budget: int = 5,
    ):
        self.interrogator = TestDiffInterrogator()
        self.mutant_engine = MutantEngine(max_mutants_budget=mutant_budget)
        self.min_mutation_kill_ratio = min_mutation_kill_ratio

    def verify(
        self,
        patch_text: str,
        source_files_content: Optional[Dict[str, str]] = None,
        test_runner: Optional[Callable[[CodeMutant], bool]] = None,
    ) -> VerificationOutcome:
        """
        Verify the adequacy of the proposed patch and test evidence.

        Args:
            patch_text: The complete unified git diff.
            source_files_content: Dict mapping file paths to their post-patch source code.
            test_runner: Optional callback taking a CodeMutant and returning True if tests FAILED (mutant killed).
        """
        # Step 1: Deterministic Test-Diff Interrogation
        report = self.interrogator.interrogate_diff(patch_text)
        if report.has_critical_weakening:
            reasons = [f"{v.violation_type}: {v.snippet}" for v in report.violations[:3]]
            return VerificationOutcome(
                allow=False,
                stage="test_diff_audit",
                reason=f"Test weakening detected: {'; '.join(reasons)}",
                interrogation_report=report,
            )

        # Step 2: Targeted Mutation Probing (if source files and test runner provided)
        mutation_result = None
        if source_files_content and test_runner:
            modified_lines_map = self.mutant_engine.extract_modified_lines_by_file(patch_text)
            all_mutants: List[CodeMutant] = []

            for f_path, mod_lines in modified_lines_map.items():
                if f_path in source_files_content:
                    src = source_files_content[f_path]
                    muts = self.mutant_engine.generate_mutants_for_source(src, f_path, target_lines=mod_lines)
                    all_mutants.extend(muts)

            if all_mutants:
                mutants_eval = []
                killed_count = 0

                for m in all_mutants[:self.mutant_engine.max_mutants_budget]:
                    # test_runner returns True if tests caught the mutant (i.e. tests failed)
                    is_killed = test_runner(m)
                    if is_killed:
                        killed_count += 1
                    mutants_eval.append({
                        "mutant_id": m.mutant_id,
                        "description": m.description,
                        "killed": is_killed,
                    })

                total_m = len(mutants_eval)
                kill_ratio = killed_count / total_m if total_m > 0 else 1.0
                adequacy_passed = (kill_ratio >= self.min_mutation_kill_ratio)

                mutation_result = MutationProbeResult(
                    total_mutants=total_m,
                    mutants_killed=killed_count,
                    mutants_survived=total_m - killed_count,
                    kill_ratio=kill_ratio,
                    mutants=mutants_eval,
                    adequacy_passed=adequacy_passed,
                    summary=f"Mutation Kill Ratio: {kill_ratio*100:.1f}% ({killed_count}/{total_m} mutants killed).",
                )

                if not adequacy_passed:
                    survived_descriptions = [m["description"] for m in mutants_eval if not m["killed"]][:2]
                    return VerificationOutcome(
                        allow=False,
                        stage="mutation_probe",
                        reason=(
                            f"Verification Inadequate: Only {kill_ratio*100:.0f}% of implementation mutants were killed by tests "
                            f"(threshold: {self.min_mutation_kill_ratio*100:.0f}%). "
                            f"Tests passed even when logic was mutated: {'; '.join(survived_descriptions)}"
                        ),
                        interrogation_report=report,
                        mutation_result=mutation_result,
                    )

        # Step 3: Verified
        return VerificationOutcome(
            allow=True,
            stage="verified",
            reason="Verification Adequate: Zero test-weakening detected and test evidence successfully verified.",
            interrogation_report=report,
            mutation_result=mutation_result,
        )
