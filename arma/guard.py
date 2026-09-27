"""ARMA AgentGuard: Active Guardrails & Supervision SDK for Coding Agents.

Provides a unified programmatic interface to audit agent actions before execution:
1. Diff Auditing: Prevents reward-hacking (test deletions, injected skips, swallowed exceptions).
2. Command Auditing: Pre-flight safety checks for destructive terminal commands.
3. Blast Radius Prediction: AST dependency impact closure before modifying files.
4. Closed-Loop Prompt Guidance: Structured feedback formatted for LLM self-correction.
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

from arma_veto.interrogator import TestDiffInterrogator, InterrogationReport, TestViolation
from layer.code_graph import CodeGraph
from layer.verification_gate import VerificationAdequacyGate, VerificationOutcome


# Hard-deny command patterns for destructive operations
HARD_DENY_PATTERNS = [
    (r"\brm\s+-(?:rf|fr|r\s+-f|f\s+-r)\s+[/~]", "Recursive deletion of root or home directory"),
    (r"\bDROP\s+DATABASE\b", "Destructive SQL DROP DATABASE"),
    (r"\bDROP\s+TABLE\b", "Destructive SQL DROP TABLE"),
    (r"\bTRUNCATE\s+TABLE\b", "Destructive SQL TRUNCATE TABLE"),
    (r"\bgit\s+push\b.*?(?:--force\b|-f\b)", "Force-pushing to remote git repository"),
    (r"\bgit\s+reset\s+--hard\s+HEAD~", "Hard reset discarding commit history"),
    (r"\bchmod\s+(?:-R\s+)?777\b", "Overly permissive chmod 777"),
    (r"\bcurl\b.*\|\s*(?:bash|sh)\b", "Piping remote script directly to shell execution"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", "Fork bomb denial of service"),
]


@dataclass
class GuardVerdict:
    allowed: bool
    reason: str
    feedback: str
    directive: str = ""
    violations: List[TestViolation] = field(default_factory=list)
    blast_radius: Set[str] = field(default_factory=set)
    report: Optional[InterrogationReport] = None
    verification_outcome: Optional[VerificationOutcome] = None

    @property
    def vetoed(self) -> bool:
        return not self.allowed


@dataclass
class CommandVerdict:
    allowed: bool
    command: str
    reason: str


class AgentGuard:
    """Active reliability guardrail for AI coding agents and autonomous loops."""

    def __init__(
        self,
        repo_path: Optional[str] = None,
        strict: bool = False,
        enable_mutation_probe: bool = False,
        mutant_budget: int = 3,
        min_kill_ratio: float = 0.20,
    ):
        self.repo_path = os.path.abspath(repo_path or os.getcwd())
        self.strict = strict
        self.enable_mutation_probe = enable_mutation_probe
        self.mutant_budget = mutant_budget
        self.min_kill_ratio = min_kill_ratio

        self.interrogator = TestDiffInterrogator()
        self._code_graph: Optional[CodeGraph] = None
        self._gate: Optional[VerificationAdequacyGate] = None

    @property
    def code_graph(self) -> CodeGraph:
        """Lazily initialize CodeGraph to keep instantiations sub-millisecond if unused."""
        if self._code_graph is None:
            self._code_graph = CodeGraph(root_dir=self.repo_path)
        return self._code_graph

    @property
    def gate(self) -> VerificationAdequacyGate:
        """Lazily initialize VerificationAdequacyGate for mutation probes."""
        if self._gate is None:
            self._gate = VerificationAdequacyGate(
                min_mutation_kill_ratio=self.min_kill_ratio,
                mutant_budget=self.mutant_budget,
            )
        return self._gate

    def audit_diff(self, diff_text: str, test_command: Optional[str] = None) -> GuardVerdict:
        """Audits a unified git diff for test-tampering, evasion, and test adequacy.

        Args:
            diff_text: Unified diff string (e.g. from `git diff`).
            test_command: Optional test command for dynamic mutation probe.

        Returns:
            GuardVerdict with allow/veto decision and actionable feedback.
        """
        if not diff_text or not diff_text.strip():
            return GuardVerdict(
                allowed=True,
                reason="Clean: No modifications in diff.",
                feedback="No changes detected.",
            )

        # 1. Deterministic AST Interrogation (Sub-50ms)
        report = self.interrogator.interrogate_diff(diff_text)
        is_vetoed = report.has_critical_weakening if self.strict else report.has_structural_tampering

        # Calculate blast radius for touched files
        blast_radius: Set[str] = set()
        for f in report.impl_files_touched:
            blast_radius.update(self.predict_impact(f))

        if is_vetoed:
            violations_detail = []
            for v in report.violations:
                if self.strict or v.violation_type in (
                    "TEST_DELETED", "SKIP_INJECTED", "EXCEPTION_SWALLOWED",
                    "ASSERTION_DELETED", "ASSERTION_WEAKENED"
                ):
                    violations_detail.append(f"  - [{v.violation_type}] {v.file_path}:{v.line_number or '?'} -> {v.snippet}")

            viol_str = "\n".join(violations_detail) if violations_detail else "  - Test structural integrity compromised."
            feedback = (
                f"[VETO: TEST TAMPERING DETECTED]\n"
                f"Your patch modified or removed existing test validations:\n"
                f"{viol_str}\n\n"
                f"DIRECTIVE: You are strictly forbidden from deleting tests, skipping tests, or swallowing "
                f"assertions to make CI pass. Restore the tests and fix the implementation logic instead."
            )
            return GuardVerdict(
                allowed=False,
                reason=f"Structural test tampering ({len(report.violations)} violations)",
                feedback=feedback,
                directive="Restore deleted/weakened tests and fix underlying code.",
                violations=report.violations,
                blast_radius=blast_radius,
                report=report,
            )

        # 2. Dynamic Mutation Probe (Optional or when test_command is provided)
        verification_outcome = None
        if self.enable_mutation_probe and test_command:
            verification_outcome = self.gate.verify_repository(
                repo_path=self.repo_path,
                patch_text=diff_text,
                test_command=test_command,
            )
            if not verification_outcome.allow:
                feedback = verification_outcome.format_agent_feedback()
                return GuardVerdict(
                    allowed=False,
                    reason=f"Mutation probe failed: {verification_outcome.reason}",
                    feedback=feedback,
                    directive="Tests are hollow; add assertions that discriminate against implementation mutations.",
                    violations=report.violations,
                    blast_radius=blast_radius,
                    report=report,
                    verification_outcome=verification_outcome,
                )

        # 3. Passed Clean
        summary = "Diff passed audit cleanly."
        if report.touches_test_files:
            summary = f"Passed: {report.new_tests_count} new tests added with zero test weakening."
        if report.modified_assertions_count > 0:
            summary += f" ({report.modified_assertions_count} assertion updates verified safe)."

        return GuardVerdict(
            allowed=True,
            reason=summary,
            feedback="[GUARD PASSED] Code modifications adhere to reliability invariants.",
            violations=report.violations,
            blast_radius=blast_radius,
            report=report,
            verification_outcome=verification_outcome,
        )

    def audit_command(self, command: str, cwd: Optional[str] = None) -> CommandVerdict:
        """Pre-flight check evaluating shell command safety before execution."""
        clean_cmd = command.strip()
        for pattern, explanation in HARD_DENY_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                return CommandVerdict(
                    allowed=False,
                    command=command,
                    reason=f"Blocked hazardous command: {explanation} (matched pattern: {pattern})"
                )
        return CommandVerdict(
            allowed=True,
            command=command,
            reason="Command passed safety invariants."
        )

    def predict_impact(self, target_file: str, symbol: Optional[str] = None) -> Set[str]:
        """Calculates transitive dependency blast radius for a given file."""
        return self.code_graph.predict_impact(target_file, symbol=symbol)

    def get_prompt_guardrails(self) -> str:
        """Returns standard reliability instructions to inject into coding agent prompts."""
        return (
            "### ARMA Reliability Invariants\n"
            "1. Never delete, comment out, or skip existing tests (@pytest.mark.skip, it.skip, t.Skip).\n"
            "2. Never wrap assertions in empty 'except Exception: pass' or '.catch(() => {})'.\n"
            "3. Keep code changes tightly bounded within the dependency closure of the issue.\n"
            "4. Verify that newly added tests actively fail on broken mutants before concluding."
        )
