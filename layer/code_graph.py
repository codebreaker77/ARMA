"""
ARMA Context Plane: Fullerenes Code Graph Engine
Builds structural code graphs (AST, imports, symbol references, and caller hierarchies).
Implements predict_impact() to calculate transitive dependency closures (blast radius)
for deterministic Scope Gate enforcement.
"""

import os
import ast
import re
from typing import Dict, Set, List, Optional, Tuple


class CodeGraph:
    """
    High-performance structural code graph for repository dependency analysis.
    Indexes files, module imports, function/class definitions, and call hierarchies.
    """

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = os.path.abspath(root_dir or os.getcwd())
        # file_path -> Set of file_paths it directly imports
        self.import_graph: Dict[str, Set[str]] = {}
        # file_path -> Set of file_paths that import it (reverse graph)
        self.reverse_import_graph: Dict[str, Set[str]] = {}
        # file_path -> Set of defined symbol names (classes, functions)
        self.file_symbols: Dict[str, Set[str]] = {}
        # symbol_name -> Set of file_paths defining it
        self.symbol_to_files: Dict[str, Set[str]] = {}
        # symbol_name -> Set of symbol_names it calls
        self.call_graph: Dict[str, Set[str]] = {}

        self.indexed_files: Set[str] = set()
        self.build_graph()

    def _normalize_rel_path(self, full_path: str) -> str:
        """Get clean relative POSIX path from root_dir."""
        try:
            rel = os.path.relpath(full_path, self.root_dir)
            return rel.replace("\\", "/")
        except ValueError:
            return full_path.replace("\\", "/")

    def build_graph(self):
        """Scan repository files and index AST dependencies."""
        self.import_graph.clear()
        self.reverse_import_graph.clear()
        self.file_symbols.clear()
        self.symbol_to_files.clear()
        self.indexed_files.clear()

        # Target extensions for code analysis
        supported_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs"}

        for root, dirs, files in os.walk(self.root_dir):
            # Skip hidden and cache directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", "__pycache__", "dist", "build")]

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, f)
                    rel_path = self._normalize_rel_path(full_path)
                    self.indexed_files.add(rel_path)
                    self.import_graph[rel_path] = set()
                    self.reverse_import_graph[rel_path] = set()
                    self.file_symbols[rel_path] = set()

                    if ext == ".py":
                        self._index_python_file(full_path, rel_path)
                    elif ext in (".js", ".jsx", ".ts", ".tsx"):
                        self._index_js_ts_file(full_path, rel_path)
                    elif ext == ".go":
                        self._index_go_file(full_path, rel_path)

        # Build reverse import graph for transitive caller closures
        for src_file, imported_files in self.import_graph.items():
            for imp in imported_files:
                if imp not in self.reverse_import_graph:
                    self.reverse_import_graph[imp] = set()
                self.reverse_import_graph[imp].add(src_file)

    def _index_python_file(self, full_path: str, rel_path: str):
        """Parse Python AST to extract imports, function/class symbols, and references."""
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                tree = ast.parse(fp.read(), filename=rel_path)
        except Exception:
            return

        for node in ast.walk(tree):
            # 1. Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_name = alias.name.split(".")[0]
                    self._resolve_and_link_import(rel_path, mod_name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod_name = node.module.split(".")[0]
                    self._resolve_and_link_import(rel_path, mod_name)

            # 2. Function & Class definitions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbol_name = node.name
                self.file_symbols[rel_path].add(symbol_name)
                if symbol_name not in self.symbol_to_files:
                    self.symbol_to_files[symbol_name] = set()
                self.symbol_to_files[symbol_name].add(rel_path)

    def _resolve_and_link_import(self, src_rel_path: str, module_name: str):
        """Attempt to match an imported module to an internal repository file."""
        # Check standard layout patterns
        candidates = [
            f"{module_name}.py",
            f"{module_name}/__init__.py",
            f"src/{module_name}.py",
            f"src/{module_name}/__init__.py",
            f"pkg/{module_name}.py",
            f"layer/{module_name}.py"
        ]
        for c in candidates:
            if c in self.indexed_files and c != src_rel_path:
                self.import_graph[src_rel_path].add(c)
                return

    def _index_js_ts_file(self, full_path: str, rel_path: str):
        """Regex-based scanner for JS/TS imports and exports."""
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
        except Exception:
            return

        # Matches: import ... from './components/Button' or require('./utils')
        import_matches = re.findall(r"(?:import\s+.*?from\s+['\"](.*?)['\"]|require\(['\"](.*?)['\"]\))", content)
        for m in import_matches:
            target = m[0] or m[1]
            if target and target.startswith("."):
                # Relative import
                base_dir = os.path.dirname(rel_path)
                norm_target = os.path.normpath(os.path.join(base_dir, target)).replace("\\", "/")
                for ext in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
                    candidate = f"{norm_target}{ext}"
                    if candidate in self.indexed_files:
                        self.import_graph[rel_path].add(candidate)
                        break

    def _index_go_file(self, full_path: str, rel_path: str):
        """Regex-based scanner for Go imports."""
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
        except Exception:
            return

        matches = re.findall(r"import\s+(?:\((.*?)\)|\"([^\"]+)\")", content, re.DOTALL)
        for block, single in matches:
            text = block if block else single
            for line in text.splitlines():
                pkg = line.strip().strip('"')
                if pkg and "/" in pkg:
                    # Match package suffix to local directory
                    pkg_suffix = pkg.split("/")[-1]
                    for f in self.indexed_files:
                        if f.startswith(f"pkg/{pkg_suffix}/") or f.startswith(f"internal/{pkg_suffix}/"):
                            self.import_graph[rel_path].add(f)

    def predict_impact(self, target_file: str, symbol: Optional[str] = None, max_depth: int = 4) -> Set[str]:
        """
        Calculates the transitive dependency closure (blast radius) of modifying target_file.
        Returns the set of all files directly or indirectly affected by changes to target_file.
        """
        norm_target = self._normalize_rel_path(target_file)
        impact_set: Set[str] = {norm_target}

        # If a specific symbol is specified, also find files referencing that symbol
        if symbol and symbol in self.symbol_to_files:
            impact_set.update(self.symbol_to_files[symbol])

        # Traverse reverse import graph using Breadth-First Search (BFS)
        queue = [(norm_target, 0)]
        visited = {norm_target}

        while queue:
            current_file, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            dependents = self.reverse_import_graph.get(current_file, set())
            for dep in dependents:
                if dep not in visited:
                    visited.add(dep)
                    impact_set.add(dep)
                    queue.append((dep, depth + 1))

        # Also add associated test files by convention
        base_name = os.path.splitext(os.path.basename(norm_target))[0]
        test_patterns = [
            f"tests/test_{base_name}.py",
            f"test_{base_name}.py",
            f"tests/unit/test_{base_name}.py",
            f"{os.path.dirname(norm_target)}/test_{base_name}.py",
            f"{os.path.dirname(norm_target)}/{base_name}.test.ts",
            f"{os.path.dirname(norm_target)}/{base_name}.test.js"
        ]
        for t in test_patterns:
            if t in self.indexed_files:
                impact_set.add(t)

        return impact_set

    def find_relevant_symbols(self, query: str, top_k: int = 15) -> List[Tuple[str, str]]:
        """
        Wide retrieval step: Fast keyword & structural symbol lookup across the graph.
        Returns list of (rel_file_path, symbol_name) candidates.
        """
        candidates = []
        tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]

        for file_path, symbols in self.file_symbols.items():
            for sym in symbols:
                sym_lower = sym.lower()
                score = sum(2 for t in tokens if t in sym_lower)
                if any(t in file_path.lower() for t in tokens):
                    score += 1
                if score > 0:
                    candidates.append((score, file_path, sym))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [(file_path, sym) for _, file_path, sym in candidates[:top_k]]
