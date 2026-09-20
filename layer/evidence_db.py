"""
ARMA Evidence Plane: SQLite Database Engine
Persists sessions, events, decisions, counterfactuals, and ground-truth outcomes.
Powers continuous calibration, threshold tuning, and distillation datasets.
"""

import os
import sqlite3
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime


DEFAULT_DB_PATH = os.path.expanduser("~/.arma/evidence.db")


class EvidenceDB:
    """Manages the local SQLite database for the ARMA Evidence Plane."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("ARMA_DB_PATH", DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_schema(self):
        """Initialize tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                repo_path TEXT NOT NULL,
                harness TEXT NOT NULL,
                task_text TEXT NOT NULL,
                graph_version TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                final_status TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                turn INTEGER NOT NULL,
                kind TEXT NOT NULL,
                tool_name TEXT,
                args_hash TEXT,
                raw_payload_summary TEXT,
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                module TEXT NOT NULL,
                question_type TEXT NOT NULL,
                question_text TEXT NOT NULL,
                answer_raw TEXT NOT NULL,
                probability REAL,
                confidence REAL NOT NULL,
                backend TEXT NOT NULL,
                model_version TEXT NOT NULL,
                threshold REAL NOT NULL,
                mode TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                counterfactual_action TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS outcomes (
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                source TEXT NOT NULL,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_decisions_module ON decisions(module, mode);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, turn);
            CREATE INDEX IF NOT EXISTS idx_outcomes_decision ON outcomes(decision_id, label);
            """)

    def start_session(self, repo_path: str, harness: str, task_text: str, graph_version: Optional[str] = None) -> str:
        """Record the start of an agent session."""
        session_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, repo_path, harness, task_text, graph_version) VALUES (?, ?, ?, ?, ?)",
                (session_id, repo_path, harness, task_text, graph_version)
            )
        return session_id

    def end_session(self, session_id: str, final_status: str = "resolved"):
        """Record the conclusion of an agent session."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP, final_status = ? WHERE id = ?",
                (final_status, session_id)
            )

    def record_event(
        self,
        session_id: str,
        turn: int,
        kind: str,
        tool_name: Optional[str] = None,
        args_hash: Optional[str] = None,
        raw_payload_summary: Optional[str] = None,
        tokens_in: int = 0,
        tokens_out: int = 0
    ) -> str:
        """Record an intercepted lifecycle event."""
        event_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO events 
                   (id, session_id, turn, kind, tool_name, args_hash, raw_payload_summary, tokens_in, tokens_out)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, session_id, turn, kind, tool_name, args_hash, raw_payload_summary, tokens_in, tokens_out)
            )
        return event_id

    def record_decision(
        self,
        event_id: str,
        module: str,
        question_type: str,
        question_text: str,
        answer_raw: str,
        probability: Optional[float],
        confidence: float,
        backend: str,
        model_version: str,
        threshold: float,
        mode: str,
        action_taken: str,
        counterfactual_action: Optional[str] = None
    ) -> str:
        """Record an evaluation made by a Decision Gate."""
        decision_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO decisions 
                   (id, event_id, module, question_type, question_text, answer_raw, probability, 
                    confidence, backend, model_version, threshold, mode, action_taken, counterfactual_action)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, event_id, module, question_type, question_text, answer_raw, probability,
                 confidence, backend, model_version, threshold, mode, action_taken, counterfactual_action)
            )
        return decision_id

    def record_outcome(self, decision_id: str, label: str, source: str) -> str:
        """Record ground-truth outcome linked to a past decision."""
        outcome_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO outcomes (id, decision_id, label, source) VALUES (?, ?, ?, ?)",
                (outcome_id, decision_id, label, source)
            )
        return outcome_id

    def get_recent_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch the most recent decisions for telemetry dashboards."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT d.id, d.module, d.question_type, d.answer_raw, d.probability, d.confidence,
                       d.mode, d.action_taken, d.counterfactual_action, d.created_at, e.turn, e.kind
                FROM decisions d
                JOIN events e ON d.event_id = e.id
                ORDER BY d.created_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def calculate_calibration_metrics(self, module: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculate empirical precision, recall, and Expected Calibration Error (ECE)
        for labeled decisions in the Evidence Plane.
        """
        query = """
            SELECT d.probability, d.action_taken, d.counterfactual_action, o.label
            FROM decisions d
            JOIN outcomes o ON d.id = o.decision_id
            WHERE d.probability IS NOT NULL
        """
        params = []
        if module:
            query += " AND d.module = ?"
            params.append(module)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        if not rows:
            return {
                "total_labeled": 0,
                "precision": 0.0,
                "recall": 0.0,
                "ece": 0.0,
                "status": "INSUFFICIENT_DATA"
            }

        probs = [r["probability"] for r in rows]
        # True ground truth: positive if label indicates correctness / survival
        ground_truth = [1 if r["label"] in ("test_pass", "user_approved", "diff_survived", "task_resolved") else 0 for r in rows]

        # Calculate Expected Calibration Error (ECE) with 5 bins
        num_bins = 5
        bin_limits = [i / num_bins for i in range(num_bins + 1)]
        ece = 0.0
        n_total = len(probs)

        for i in range(num_bins):
            low, high = bin_limits[i], bin_limits[i+1]
            bin_indices = [idx for idx, p in enumerate(probs) if low <= p < high or (i == num_bins - 1 and p == high)]
            if not bin_indices:
                continue
            bin_conf = sum(probs[idx] for idx in bin_indices) / len(bin_indices)
            bin_acc = sum(ground_truth[idx] for idx in bin_indices) / len(bin_indices)
            ece += (len(bin_indices) / n_total) * abs(bin_acc - bin_conf)

        true_positives = sum(1 for p, y in zip(probs, ground_truth) if p >= 0.5 and y == 1)
        false_positives = sum(1 for p, y in zip(probs, ground_truth) if p >= 0.5 and y == 0)
        false_negatives = sum(1 for p, y in zip(probs, ground_truth) if p < 0.5 and y == 1)

        precision = true_positives / max(true_positives + false_positives, 1)
        recall = true_positives / max(true_positives + false_negatives, 1)

        return {
            "total_labeled": n_total,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "ece": round(ece, 4),
            "status": "CALIBRATED" if ece <= 0.05 and n_total >= 20 else "COLLECTING_EVIDENCE"
        }
