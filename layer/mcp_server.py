"""
ARMA Model Context Protocol (MCP) Server (layer/mcp_server.py)
Provides native JSON-RPC 2.0 stdio interface conforming to the official MCP specification.
Enables Claude Desktop, Cursor, and Windsurf to natively invoke ARMA metacognitive tools:
1. arma_check_stop: Audit completion criteria and test verification before finishing a task.
2. arma_predict_impact: Calculate Fullerenes transitive blast radius for a file edit.
3. arma_prune_output: Compress verbose test logs and terminal output by 70-90%.
4. arma_audit_command: Pre-flight safety evaluation for shell commands.
"""

import sys
import json
import os
from typing import Dict, Any, List, Optional

from layer.evidence_db import EvidenceDB
from layer.decision_engine import DecisionEngine
from layer.code_graph import CodeGraph
from layer.context_plane import ToolOutputPruner


# Official MCP protocol version
PROTOCOL_VERSION = "2024-11-05"


class MCPServer:
    """Standard Model Context Protocol (MCP) stdio server for ARMA."""

    def __init__(self, db: Optional[EvidenceDB] = None, engine: Optional[DecisionEngine] = None):
        self.db = db or EvidenceDB()
        self.engine = engine or DecisionEngine(evidence_db=self.db)
        self.graphs: Dict[str, CodeGraph] = {}
        self.session_id: Optional[str] = None

    def _ensure_session(self) -> str:
        """Ensure an active session exists in EvidenceDB so foreign keys are satisfied."""
        if not self.session_id:
            self.session_id = self.db.start_session(
                repo_path=os.getcwd(),
                harness="mcp_stdio",
                task_text="Native MCP Assistant Session"
            )
        return self.session_id

    def get_code_graph(self, repo_path: Optional[str] = None) -> CodeGraph:
        path = repo_path or os.getcwd()
        if path not in self.graphs:
            self.graphs[path] = CodeGraph(root_dir=path)
        return self.graphs[path]

    def run_stdio(self):
        """Main stdio loop reading JSON-RPC 2.0 lines from stdin and replying on stdout."""
        # Initialize evidence session for MCP lifecycle
        self._ensure_session()

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except Exception:
                continue

            response = self.handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dispatch JSON-RPC request to appropriate handler."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        # Handle notifications (no response needed)
        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "arma-metacognitive-layer",
                        "version": "1.0.0"
                    }
                }
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self._get_tool_schemas()
                }
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            return self._execute_tool_call(req_id, tool_name, tool_args)

        else:
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found"
                    }
                }
            return None

    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return MCP schemas for all 4 ARMA metacognitive tools."""
        return [
            {
                "name": "arma_check_stop",
                "description": (
                    "Metacognitive Stop Gate: Verify whether task checklist requirements and test execution "
                    "invariants are satisfied before declaring completion. Prevents premature termination."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_text": {"type": "string", "description": "The user's original task description"},
                        "test_exit_code": {"type": "integer", "description": "Exit code of the test command (0 for pass)"},
                        "test_output": {"type": "string", "description": "Terminal output or summary from test runner"},
                        "diff_stat": {"type": "string", "description": "Git diffstat summary of modifications made"}
                    },
                    "required": ["task_text"]
                }
            },
            {
                "name": "arma_predict_impact",
                "description": (
                    "Context Plane Blast Radius: Compute the transitive dependency impact of modifying a specific file "
                    "using Fullerenes AST code graph. Identifies affected modules and tests."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target_file": {"type": "string", "description": "Relative or absolute path of file to be edited"},
                        "repo_path": {"type": "string", "description": "Root directory of repository (default: current directory)"}
                    },
                    "required": ["target_file"]
                }
            },
            {
                "name": "arma_prune_output",
                "description": (
                    "Context Plane Log Compression: Compress bloated test outputs, tracebacks, compiler errors, "
                    "or git diffs by 70-90% while preserving root-cause failure assertions."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "raw_output": {"type": "string", "description": "Verbose raw output string to compress"},
                        "max_chars": {"type": "integer", "description": "Target max characters (default 1200)"}
                    },
                    "required": ["raw_output"]
                }
            },
            {
                "name": "arma_audit_command",
                "description": (
                    "Decision Plane Risk Gate: Pre-flight safety check for shell commands. "
                    "Checks deterministic hard invariants (e.g. destructive deletions, secret leaks)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command line to evaluate"},
                        "cwd": {"type": "string", "description": "Working directory for command execution"}
                    },
                    "required": ["command"]
                }
            }
        ]

    def _execute_tool_call(self, req_id: Any, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool and format MCP result."""
        sess_id = self._ensure_session()
        event_id = self.db.record_event(
            session_id=sess_id,
            turn=1,
            kind="mcp_tool_call",
            tool_name=tool_name,
            raw_payload_summary=str(args)[:200]
        )

        try:
            if tool_name == "arma_check_stop":
                test_res = None
                if "test_exit_code" in args:
                    test_res = {
                        "exit_code": args.get("test_exit_code"),
                        "output": args.get("test_output", "")
                    }
                result = self.engine.evaluate_stop(
                    session_id=sess_id,
                    event_id=event_id,
                    task_text=args.get("task_text", ""),
                    test_results=test_res,
                    diff_stat=args.get("diff_stat")
                )
                output_payload = {
                    "allow_completion": result.allow,
                    "mode": result.mode,
                    "action": result.action_taken,
                    "reason": result.reason,
                    "confidence": result.confidence,
                    "probability": result.probability
                }

            elif tool_name == "arma_predict_impact":
                target_file = args.get("target_file", "")
                graph = self.get_code_graph(args.get("repo_path"))
                impact_set = graph.predict_impact(target_file)
                output_payload = {
                    "target_file": target_file,
                    "blast_radius_count": len(impact_set),
                    "impacted_files": sorted(list(impact_set))
                }

            elif tool_name == "arma_prune_output":
                raw_out = args.get("raw_output", "")
                max_c = args.get("max_chars", 1200)
                pruned = ToolOutputPruner.prune(raw_out, max_chars=max_c)
                output_payload = {
                    "original_chars": len(raw_out),
                    "pruned_chars": len(pruned),
                    "compression_ratio": f"{round((1.0 - len(pruned)/max(len(raw_out), 1))*100, 1)}%",
                    "pruned_content": pruned
                }

            elif tool_name == "arma_audit_command":
                cmd = args.get("command", "")
                res = self.engine.evaluate_risk(
                    session_id=sess_id,
                    event_id=event_id,
                    command=cmd,
                    cwd=args.get("cwd", os.getcwd())
                )
                output_payload = {
                    "command": cmd,
                    "is_safe": (res.counterfactual_action == "pass" and res.action_taken != "block"),
                    "mode": res.mode,
                    "action": res.action_taken,
                    "counterfactual": res.counterfactual_action,
                    "reason": res.reason,
                    "confidence": res.confidence
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(output_payload, indent=2)
                        }
                    ],
                    "isError": False
                }
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"ARMA MCP Error: {str(e)}"}],
                    "isError": True
                }
            }


def run_mcp_server():
    """Start the ARMA Model Context Protocol stdio server."""
    server = MCPServer()
    server.run_stdio()


if __name__ == "__main__":
    run_mcp_server()
