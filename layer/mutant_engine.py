"""Targeted Mutation Probe Engine.

Generates localized, deterministic AST mutants strictly within the modified
implementation lines of an agent's diff. Used by the Verification Adequacy Gate
to interrogate whether the agent's tests can discriminate correct logic
from broken variants.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set


@dataclass
class CodeMutant:
    mutant_id: str
    mutation_type: str
    file_path: str
    line_number: int
    original_code: str
    mutated_code: str
    description: str


class AstMutator(ast.NodeTransformer):
    """AST transformer that generates a single targeted mutant at a specified location."""

    def __init__(self, target_line: int, mutation_type: str):
        self.target_line = target_line
        self.mutation_type = mutation_type
        self.mutated = False
        self.original_snippet = ""
        self.mutated_snippet = ""

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        if self.mutated or node.lineno != self.target_line:
            return self.generic_visit(node)

        if self.mutation_type == "INVERT_COMPARATOR":
            inverted_ops = []
            for op in node.ops:
                if isinstance(op, ast.Eq):
                    inverted_ops.append(ast.NotEq())
                elif isinstance(op, ast.NotEq):
                    inverted_ops.append(ast.Eq())
                elif isinstance(op, ast.Lt):
                    inverted_ops.append(ast.GtE())
                elif isinstance(op, ast.LtE):
                    inverted_ops.append(ast.Gt())
                elif isinstance(op, ast.Gt):
                    inverted_ops.append(ast.LtE())
                elif isinstance(op, ast.GtE):
                    inverted_ops.append(ast.Lt())
                elif isinstance(op, ast.In):
                    inverted_ops.append(ast.NotIn())
                elif isinstance(op, ast.NotIn):
                    inverted_ops.append(ast.In())
                elif isinstance(op, ast.Is):
                    inverted_ops.append(ast.IsNot())
                elif isinstance(op, ast.IsNot):
                    inverted_ops.append(ast.Is())
                else:
                    inverted_ops.append(op)

            new_node = ast.Compare(left=node.left, ops=inverted_ops, comparators=node.comparators)
            ast.copy_location(new_node, node)
            self.mutated = True
            return new_node

        return self.generic_visit(node)

    def visit_If(self, node: ast.If) -> ast.AST:
        if self.mutated or node.lineno != self.target_line:
            return self.generic_visit(node)

        if self.mutation_type == "NEGATE_CONDITION":
            new_test = ast.UnaryOp(op=ast.Not(), operand=node.test)
            ast.copy_location(new_test, node.test)
            new_node = ast.If(test=new_test, body=node.body, orelse=node.orelse)
            ast.copy_location(new_node, node)
            self.mutated = True
            return new_node

        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self.mutated or getattr(node, "lineno", None) != self.target_line:
            return self.generic_visit(node)

        if self.mutation_type == "SWAP_BOOLEAN" and isinstance(node.value, bool):
            new_node = ast.Constant(value=not node.value)
            ast.copy_location(new_node, node)
            self.mutated = True
            return new_node

        if self.mutation_type == "OFF_BY_ONE" and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            new_val = node.value + 1 if node.value == 0 else node.value - 1
            new_node = ast.Constant(value=new_val)
            ast.copy_location(new_node, node)
            self.mutated = True
            return new_node

        return self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if self.mutated or node.lineno != self.target_line:
            return self.generic_visit(node)

        if self.mutation_type == "RETURN_NONE" and node.value is not None:
            new_node = ast.Return(value=ast.Constant(value=None))
            ast.copy_location(new_node, node)
            self.mutated = True
            return new_node

        return self.generic_visit(node)


class MutantEngine:
    """Generates localized implementation mutants from unified git diffs."""

    def __init__(self, max_mutants_budget: int = 5):
        self.max_mutants_budget = max_mutants_budget

    def extract_modified_lines_by_file(self, patch_text: str) -> Dict[str, List[int]]:
        """Parse git diff to extract modified line numbers in Python files."""
        result: Dict[str, List[int]] = {}
        blocks = re.split(r"(?=diff --git )", patch_text)
        for block in blocks:
            header = re.search(r"diff --git a/(\S+) b/(\S+)", block)
            if not header:
                continue
            fname = header.group(2)
            if not fname.endswith(".py"):
                continue
            # Skip test files - we mutate the IMPLEMENTATION, not the tests
            if re.search(r"(?:^|[/\\])(?:tests?|testing|test_[^/\\]+|[^/\\]+_test)\.py$", fname, re.IGNORECASE):
                continue

            lines = block.split("\n")
            curr_line = 0
            mod_lines = []
            for l in lines:
                if l.startswith("@@"):
                    m = re.search(r"\+(\d+)", l)
                    if m:
                        curr_line = int(m.group(1))
                    continue
                if l.startswith("+") and not l.startswith("+++"):
                    mod_lines.append(curr_line)
                    curr_line += 1
                elif not l.startswith("-"):
                    curr_line += 1
            if mod_lines:
                result[fname] = mod_lines
        return result

    def generate_mutants_for_source(
        self, source_code: str, file_path: str, target_lines: Optional[List[int]] = None
    ) -> List[CodeMutant]:
        """Generate up to max_mutants_budget mutants for the given source code."""
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        source_lines = source_code.splitlines()
        mutants: List[CodeMutant] = []
        candidate_opportunities: List[Tuple[int, str]] = []

        # Find mutation opportunities on target lines (or all lines if none specified)
        target_set = set(target_lines) if target_lines else set(range(1, len(source_lines) + 1))

        for node in ast.walk(tree):
            lineno = getattr(node, "lineno", None)
            if lineno is None or lineno not in target_set:
                continue

            if isinstance(node, ast.Compare):
                candidate_opportunities.append((lineno, "INVERT_COMPARATOR"))
            elif isinstance(node, ast.If):
                candidate_opportunities.append((lineno, "NEGATE_CONDITION"))
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, bool):
                    candidate_opportunities.append((lineno, "SWAP_BOOLEAN"))
                elif isinstance(node.value, (int, float)):
                    candidate_opportunities.append((lineno, "OFF_BY_ONE"))
            elif isinstance(node, ast.Return) and node.value is not None:
                candidate_opportunities.append((lineno, "RETURN_NONE"))

        # Deduplicate candidates by (line, type)
        unique_opps = []
        seen = set()
        for opp in candidate_opportunities:
            if opp not in seen:
                seen.add(opp)
                unique_opps.append(opp)

        # Budget capping
        selected = unique_opps[:self.max_mutants_budget]

        for idx, (line_no, m_type) in enumerate(selected, 1):
            mutator = AstMutator(target_line=line_no, mutation_type=m_type)
            try:
                mutated_tree = mutator.visit(ast.parse(source_code))
                ast.fix_missing_locations(mutated_tree)
                mutated_source = ast.unparse(mutated_tree)

                orig_snippet = source_lines[line_no - 1].strip() if line_no <= len(source_lines) else ""
                mut_lines = mutated_source.splitlines()
                mut_snippet = mut_lines[line_no - 1].strip() if line_no <= len(mut_lines) else m_type

                mutants.append(CodeMutant(
                    mutant_id=f"MUT_{idx}_{m_type}_{line_no}",
                    mutation_type=m_type,
                    file_path=file_path,
                    line_number=line_no,
                    original_code=orig_snippet,
                    mutated_code=mut_snippet,
                    description=f"{m_type} at {file_path}:{line_no} ('{orig_snippet}' -> '{mut_snippet}')"
                ))
            except Exception:
                continue

        return mutants
