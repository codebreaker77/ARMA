"""
ARMA Context Plane: End-to-End Efficiency & Context Optimization Suite
Features:
1. ToolOutputPruner: Compresses multi-thousand line tool logs by 70-90%.
2. PinnedFactsManager: Anchors task checklist & critical facts to the context tail.
3. CompactionScorer: Rates historical turn importance (1-5) for intelligent pruning.
4. GraphRelevanceFilter: Wide retrieval with fast single-pass calibrated filtering.
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from micro_jev import MicroJevClient, Noul, Score
from layer.code_graph import CodeGraph


class ToolOutputPruner:
    """
    Compresses bloated terminal logs, test tracebacks, and directory dumps
    by isolating root causes and removing repetitive boilerplate.
    """

    @staticmethod
    def prune(raw_output: str, max_chars: int = 1200) -> str:
        """Prune tool output to essential diagnostic information."""
        if not raw_output or len(raw_output) <= max_chars:
            return raw_output

        lines = raw_output.splitlines()
        total_lines = len(lines)

        # 1. Detect pytest / unittest / test runners
        is_test_runner = any("FAILED" in l or "pytest" in l or "AssertionError" in l or "Ran " in l for l in lines)
        if is_test_runner:
            return ToolOutputPruner._prune_test_output(lines, total_lines)

        # 2. Detect compiler / build errors
        is_compiler = any("error:" in l.lower() or "syntaxerror" in l.lower() for l in lines)
        if is_compiler:
            return ToolOutputPruner._prune_compiler_output(lines)

        # 3. Detect large git diff or file listings
        is_diff = any(l.startswith("diff --git") or l.startswith("@@") for l in lines)
        if is_diff:
            return ToolOutputPruner._prune_diff(lines)

        # 4. General fallback: Head + Tail truncation with omission notice
        head = lines[:15]
        tail = lines[-15:]
        omitted = total_lines - 30
        return "\n".join(head + [f"\n... [ARMA Context Plane: {omitted} lines omitted] ...\n"] + tail)

    @staticmethod
    def _prune_test_output(lines: List[str], total_lines: int) -> str:
        """Extract only failing assertions, tracebacks, and summary lines."""
        essential_lines = []
        in_failure_block = False
        summary_lines = []

        for line in lines:
            # Detect summary line at the bottom
            if any(kw in line for kw in ("passed in", "failed in", "failed,", "passed,", "Ran ")):
                summary_lines.append(line)
                in_failure_block = False
                continue

            # Detect failure sections
            if any(kw in line for kw in ("FAILURES", "FAILED ", "AssertionError", "Traceback (most recent call last):")):
                in_failure_block = True

            # If we are in a failure block, capture traceback and error markers
            if in_failure_block:
                if line.startswith("=" * 10) and "FAILURES" not in line:
                    if len(essential_lines) > 5:
                        in_failure_block = False
                        continue
                essential_lines.append(line)
                if len(essential_lines) >= 30:
                    in_failure_block = False

        if not essential_lines:
            # Fallback if no specific failure block matched
            essential_lines = [l for l in lines if any(kw in l for kw in ("FAIL", "assert", "Error", "Exception"))][:20]

        combined = essential_lines + summary_lines
        if not combined:
            combined = lines[:5] + lines[-5:]

        compressed = "\n".join(combined)
        return f"[ARMA PRUNED TEST LOG: {total_lines} lines -> {len(combined)} lines]\n{compressed}"

    @staticmethod
    def _prune_compiler_output(lines: List[str]) -> str:
        """Extract only error lines and immediate file context."""
        error_lines = [l for l in lines if "error:" in l.lower() or "syntaxerror:" in l.lower() or "warning:" in l.lower()]
        return "[ARMA PRUNED COMPILER ERRORS]\n" + "\n".join(error_lines[:20])

    @staticmethod
    def _prune_diff(lines: List[str]) -> str:
        """Keep diffstat and hunk headers, trim large blocks."""
        diff_summary = []
        for line in lines:
            if line.startswith("diff --git") or line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
                diff_summary.append(line)
            elif len(diff_summary) < 20:
                diff_summary.append(line)
        return "[ARMA COMPACT DIFF]\n" + "\n".join(diff_summary)


class PinnedFactsManager:
    """
    Maintains and injects critical session facts at the tail of messages.
    Counteracts 'Lost in the Middle' attention degradation.
    """

    def __init__(self, task_checklist: Optional[List[str]] = None):
        self.checklist: List[str] = task_checklist or []
        self.touched_files: Set[str] = set()
        self.test_status: str = "UNTESTED"
        self.impact_set: Set[str] = set()
        self.pivot_guidance: Optional[str] = None

    def update_task_checklist(self, checklist: List[str]):
        self.checklist = checklist

    def record_file_touched(self, file_path: str):
        self.touched_files.add(file_path)

    def update_test_status(self, passed: bool, exit_code: int):
        self.test_status = "PASSED (exit code 0)" if passed else f"FAILED (exit code {exit_code})"

    def set_impact_set(self, impact_set: Set[str]):
        self.impact_set = impact_set

    def set_pivot_guidance(self, guidance: Optional[str]):
        self.pivot_guidance = guidance

    def format_pinned_facts(self) -> str:
        """Format the critical facts into a high-density system instruction block."""
        facts = [
            "<!-- ARMA PINNED FACTS (CRITICAL INVARIANTS AT CONTEXT TAIL) -->",
            "[SESSION CONTEXT INVARIANTS]",
            f"1. Active Test Status: {self.test_status}",
            f"2. Files Touched So Far: {', '.join(sorted(self.touched_files)) if self.touched_files else 'None'}",
        ]

        if self.checklist:
            facts.append("3. Task Checklist Requirements:")
            for i, item in enumerate(self.checklist, 1):
                facts.append(f"   - Requirement {i}: {item}")

        if self.impact_set:
            facts.append(f"4. Verified Blast Radius: {len(self.impact_set)} files permitted")

        if self.pivot_guidance:
            facts.append(f"\n{self.pivot_guidance}\n")

        facts.append("Rule: Do NOT declare completion until all checklist requirements pass tests.")
        return "\n".join(facts)

    def inject_into_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Injects the pinned facts block directly before the final turn
        or appends to the last user message to ensure peak attention.
        """
        if not messages:
            return messages

        pinned_block = self.format_pinned_facts()
        new_messages = [dict(m) for m in messages]

        # Append to the last message content
        last_msg = new_messages[-1]
        orig_content = last_msg.get("content", "")
        if isinstance(orig_content, str):
            last_msg["content"] = f"{orig_content}\n\n{pinned_block}"
        elif isinstance(orig_content, list):
            # For Anthropic multi-part content
            last_msg["content"].append({"type": "text", "text": f"\n\n{pinned_block}"})

        return new_messages


class CompactionScorer:
    """
    Rates the importance of conversation turns on a 1-5 scale
    to selectively discard low-value turns during context compaction.
    """

    @staticmethod
    def score_turn(role: str, content: str, tool_name: Optional[str] = None) -> int:
        """
        Returns importance score from 1 (disposable) to 5 (critical).
        """
        # User prompt is always critical
        if role == "user":
            return 5

        # Critical: test failures, syntax errors, or architectural decisions
        if any(kw in content.lower() for kw in ("failed", "assertionerror", "error:", "syntaxerror")):
            return 4

        # Important: git diffs and code write operations
        if tool_name in ("write_to_file", "replace_file_content", "edit_file"):
            return 4

        # Moderate: reading key source files
        if tool_name in ("view_file", "read_file"):
            return 3

        # Low importance / disposable: directory listings, simple greps, empty searches
        if tool_name in ("list_dir", "ls", "find_by_name") or len(content) < 50:
            return 1

        return 2


class GraphRelevanceFilter:
    """
    Executes 'Retrieve Wide, Judge Cheap':
    Takes candidate symbols from CodeGraph, evaluates relevance via MicroJev in parallel,
    and returns only the top most relevant snippets for context insertion.
    """

    def __init__(self, classifier_client: Optional[MicroJevClient] = None):
        self.classifier = classifier_client or MicroJevClient()

    def filter_candidates(
        self,
        task_query: str,
        candidates: List[Tuple[str, str]],
        top_k: int = 4
    ) -> List[Tuple[str, str]]:
        """
        Evaluate candidate symbols in a single parallel pass.
        Returns the top_k most relevant (file_path, symbol_name) pairs.
        """
        if not candidates or len(candidates) <= top_k:
            return candidates

        # Fast parallel evaluation of candidate relevance
        questions = {
            f"cand_{i}": Noul(
                instructions=f"Is symbol '{sym}' in '{fpath}' directly relevant to resolving: {task_query}?"
            )
            for i, (fpath, sym) in enumerate(candidates)
        }

        res = self.classifier.system_one(
            state={"task_query": task_query},
            questions=questions
        )

        scored_candidates = []
        for i, (fpath, sym) in enumerate(candidates):
            key = f"cand_{i}"
            noul_ans = res.answers.get(key)
            prob = noul_ans.probability if noul_ans else 0.5
            scored_candidates.append((prob, fpath, sym))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        return [(fpath, sym) for _, fpath, sym in scored_candidates[:top_k]]
