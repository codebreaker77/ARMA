"""
Unit tests for ARMA Real-Time Web Telemetry Dashboard (layer/web_dashboard.py).
"""

import json
import time
import socket
import threading
import urllib.request
import unittest
from http.server import HTTPServer

from layer.evidence_db import EvidenceDB
from layer.code_graph import CodeGraph
from layer.web_dashboard import DashboardHandler


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class TestWebDashboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.db = EvidenceDB()
        DashboardHandler.db = cls.db
        DashboardHandler.graph = CodeGraph()

        cls.httpd = HTTPServer(("127.0.0.1", cls.port), DashboardHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.server_close()

    def test_dashboard_html_page(self):
        url = f"http://127.0.0.1:{self.port}/"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("ARMA // Telemetry & Decision Monitor", body)
            self.assertIn("Token Compression", body)

    def test_api_stats_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/stats"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("total_decisions", data)
            self.assertIn("total_sessions", data)
            self.assertIn("ece", data)

    def test_api_decisions_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/decisions"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIsInstance(data, list)

    def test_api_graph_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/graph"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("indexed_files_count", data)
            self.assertIn("total_symbols_count", data)


if __name__ == "__main__":
    unittest.main()
