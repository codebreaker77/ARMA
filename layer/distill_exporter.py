"""
ARMA Distillation & Dataset Exporter (layer/distill_exporter.py)
Transforms labeled Evidence Plane interactions into standardized training datasets:
1. Contrastive Triplets (anchor, positive, negative) for embedding / bi-encoder fine-tuning.
2. Instruction Tuning datasets (Alpaca / ShareGPT) for Small Language Model (SLM) policy distillation.
"""

import os
import json
from typing import Dict, Any, List, Optional
from layer.evidence_db import EvidenceDB


class DistillExporter:
    """
    Exports high-leverage decision traces from EvidenceDB
    into machine learning training corpora.
    """

    def __init__(self, db: Optional[EvidenceDB] = None):
        self.db = db or EvidenceDB()

    def fetch_labeled_decisions(
        self,
        module: Optional[str] = None,
        only_disagreements: bool = False
    ) -> List[Dict[str, Any]]:
        """Fetch all decisions that have verified ground-truth labels."""
        query = """
            SELECT d.id, d.module, d.question_type, d.question_text, d.answer_raw,
                   d.probability, d.confidence, d.action_taken, d.counterfactual_action,
                   e.raw_payload_summary, e.tool_name, e.turn,
                   s.task_text, s.repo_path,
                   o.label, o.source
            FROM decisions d
            JOIN events e ON d.event_id = e.id
            JOIN sessions s ON e.session_id = s.id
            JOIN outcomes o ON d.id = o.decision_id
            WHERE o.label IS NOT NULL
        """
        params = []
        if module:
            query += " AND d.module = ?"
            params.append(module)

        with self.db._get_connection() as conn:
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        if only_disagreements:
            # Filter for cases where action_taken was incorrect relative to ground truth
            filtered = []
            for r in rows:
                is_positive = r["label"] in ("test_pass", "user_approved", "diff_survived", "task_resolved")
                was_passed = (r["action_taken"] == "pass")
                if was_passed != is_positive:
                    filtered.append(r)
            return filtered

        return rows

    def export_contrastive_triplets(
        self,
        output_path: str,
        module: Optional[str] = None,
        only_disagreements: bool = False
    ) -> int:
        """
        Export triplet format for contrastive fine-tuning:
        { "anchor": ..., "positive": ..., "negative": ..., "module": ... }
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        rows = self.fetch_labeled_decisions(module=module, only_disagreements=only_disagreements)

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for r in rows:
                mod = r["module"]
                label = r["label"]
                is_pass = label in ("test_pass", "user_approved", "diff_survived", "task_resolved")

                anchor = (
                    f"Task: {r['task_text']}\n"
                    f"Module: {mod}\n"
                    f"Event Context: {r['raw_payload_summary']}\n"
                    f"Question: {r['question_text']}"
                )

                if is_pass:
                    positive = (
                        f"Action: ALLOW (PASS)\n"
                        f"Rationale: All requirements verified, tests pass ({label}), "
                        f"execution is safe within designated scope."
                    )
                    negative = (
                        f"Action: BLOCK (PREVENT)\n"
                        f"Rationale: Unjustified block; task was actually verified and passing."
                    )
                else:
                    positive = (
                        f"Action: BLOCK (INTERVENE)\n"
                        f"Rationale: Invariant violation detected; tests failed ({label}) "
                        f"or out-of-scope modifications present."
                    )
                    negative = (
                        f"Action: ALLOW (PASS)\n"
                        f"Rationale: Premature completion permitted despite unverified failure."
                    )

                triplet = {
                    "id": r["id"],
                    "module": mod,
                    "anchor": anchor,
                    "positive": positive,
                    "negative": negative,
                    "ground_truth": label,
                    "confidence": r["confidence"]
                }
                f.write(json.dumps(triplet) + "\n")
                count += 1

        return count

    def export_instruction_tuning(
        self,
        output_path: str,
        format_type: str = "alpaca",
        module: Optional[str] = None
    ) -> int:
        """
        Export instruction tuning dataset (Alpaca or ShareGPT format)
        for training small parameter distilled models.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        rows = self.fetch_labeled_decisions(module=module)

        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for r in rows:
                mod = r["module"]
                label = r["label"]
                is_pass = label in ("test_pass", "user_approved", "diff_survived", "task_resolved")

                instruction = (
                    f"You are the ARMA Metacognitive Gatekeeper for {mod}. "
                    f"Evaluate whether the agent's requested action satisfies correctness invariants."
                )
                input_context = (
                    f"Task: {r['task_text']}\n"
                    f"State: {r['raw_payload_summary']}\n"
                    f"Criterion: {r['question_text']}"
                )

                output_text = (
                    f"DECISION: {'ALLOW' if is_pass else 'BLOCK'}\n"
                    f"VERIFICATION_LABEL: {label}\n"
                    f"REASON: {'Verified safe and verified passing.' if is_pass else 'Premature exit or policy breach detected.'}"
                )

                if format_type == "alpaca":
                    record = {
                        "instruction": instruction,
                        "input": input_context,
                        "output": output_text
                    }
                else:
                    # ShareGPT format
                    record = {
                        "messages": [
                            {"role": "system", "content": instruction},
                            {"role": "user", "content": input_context},
                            {"role": "assistant", "content": output_text}
                        ]
                    }

                f.write(json.dumps(record) + "\n")
                count += 1

        return count
