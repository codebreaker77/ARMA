"""
Unit tests for ARMA Model Context Protocol (MCP) Server (layer/mcp_server.py).
"""

import json
import unittest
from layer.mcp_server import MCPServer, PROTOCOL_VERSION


class TestMCPServer(unittest.TestCase):

    def setUp(self):
        self.server = MCPServer()

    def test_mcp_initialize(self):
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        }
        res = self.server.handle_request(req)
        self.assertEqual(res["jsonrpc"], "2.0")
        self.assertEqual(res["id"], 1)
        self.assertEqual(res["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(res["result"]["serverInfo"]["name"], "arma-metacognitive-layer")

    def test_mcp_tools_list(self):
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        res = self.server.handle_request(req)
        tools = res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("arma_check_stop", tool_names)
        self.assertIn("arma_predict_impact", tool_names)
        self.assertIn("arma_prune_output", tool_names)
        self.assertIn("arma_audit_command", tool_names)

    def test_mcp_tool_prune_output(self):
        verbose_log = "pytest header\n" + "\n".join([f"line {i}" for i in range(200)]) + "\nFAILED test_x\n"
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "arma_prune_output",
                "arguments": {"raw_output": verbose_log}
            }
        }
        res = self.server.handle_request(req)
        self.assertFalse(res["result"]["isError"])
        content_text = res["result"]["content"][0]["text"]
        payload = json.loads(content_text)
        self.assertIn("compression_ratio", payload)
        self.assertIn("pruned_content", payload)
        self.assertLess(payload["pruned_chars"], payload["original_chars"])

    def test_mcp_tool_audit_command(self):
        # Destructive command should be blocked
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "arma_audit_command",
                "arguments": {"command": "rm -rf / --no-preserve-root"}
            }
        }
        res = self.server.handle_request(req)
        self.assertFalse(res["result"]["isError"])
        payload = json.loads(res["result"]["content"][0]["text"])
        self.assertFalse(payload["is_safe"])
        self.assertEqual(payload["counterfactual"], "block")

        # In enforce mode, active action is also block
        self.server.engine.set_module_mode("risk_gate", "enforce")
        res_enforce = self.server.handle_request(req)
        payload_enforce = json.loads(res_enforce["result"]["content"][0]["text"])
        self.assertFalse(payload_enforce["is_safe"])
        self.assertEqual(payload_enforce["action"], "block")

    def test_mcp_tool_predict_impact(self):
        req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "arma_predict_impact",
                "arguments": {"target_file": "layer/decision_engine.py"}
            }
        }
        res = self.server.handle_request(req)
        self.assertFalse(res["result"]["isError"])
        payload = json.loads(res["result"]["content"][0]["text"])
        self.assertIn("blast_radius_count", payload)
        self.assertIn("impacted_files", payload)


if __name__ == "__main__":
    unittest.main()
