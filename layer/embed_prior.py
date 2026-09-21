"""
ARMA Embedding Prior (layer/embed_prior.py)
An experimental zero-shot embedding-similarity heuristic.
Provides an uncalibrated lexical similarity prior.

Important Note:
Output probabilities for binary negation hypotheses (e.g. "Assertion is true: X" vs
"Assertion is false: X") are compressed near 0.5 due to lexical overlap.
Empirical AUROC on binary negation propositions is approximately 0.50 (chance level).
For discriminative classification, use SupervisedEmbedClassifier or LLMLogitClassifier.
"""

import time
import hashlib
import requests
import numpy as np
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Decision Primitives
# ---------------------------------------------------------------------------

class NoulResult(BaseModel):
    """Result of a Noul (binary truth) proposition."""
    probability: float = Field(..., description="Estimated probability (0.0 to 1.0) that the proposition is true.")
    boolean_value: bool = Field(..., description="Boolean thresholded at p >= threshold.")
    confidence: float = Field(..., description="Distance from uncertainty: |p - 0.5| * 2.")
    status: str = Field(default="ok", description="Status code: 'ok' or 'backend_error'.")


class ChoiceResult(BaseModel):
    """Result of a Choice (categorical) selection."""
    selected_option: str = Field(..., description="The option with highest probability.")
    distribution: Dict[str, float] = Field(..., description="Probability distribution across options.")
    confidence: float = Field(..., description="Confidence score of top choice.")
    status: str = Field(default="ok", description="Status code: 'ok' or 'backend_error'.")


class ScoreResult(BaseModel):
    """Result of a Score (ordinal rubric) assessment."""
    weighted_score: float = Field(..., description="Expected score value.")
    distribution: Dict[int, float] = Field(..., description="Probability assigned to each rubric level.")
    confidence: float = Field(..., description="Confidence in the modal score bin.")
    status: str = Field(default="ok", description="Status code: 'ok' or 'backend_error'.")


class Noul:
    """Binary question primitive: 'Is this proposition true?'"""
    def __init__(self, instructions: str, threshold: float = 0.5):
        self.instructions = instructions
        self.threshold = threshold


class Choice:
    """Categorical question primitive: Select one option from criteria."""
    def __init__(self, instructions: str, criteria: Dict[str, Optional[str]]):
        self.instructions = instructions
        self.criteria = criteria


class Score:
    """Ordinal question primitive: Rate against a 1-to-N rubric scale."""
    def __init__(self, instructions: str, min_score: int = 1, max_score: int = 5, rubric: Optional[Dict[int, str]] = None):
        self.instructions = instructions
        self.min_score = min_score
        self.max_score = max_score
        self.rubric = rubric or {
            1: "Very Low / Poor",
            2: "Low / Below Average",
            3: "Moderate / Neutral",
            4: "High / Good",
            5: "Very High / Excellent"
        }


class EmbedPriorResponse:
    """Container for EmbedPrior responses."""
    def __init__(self, answers: Dict[str, Union[NoulResult, ChoiceResult, ScoreResult]], latency_ms: float, input_tokens: int = 0):
        self.answers = answers
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens

    def __repr__(self):
        return f"<EmbedPriorResponse answers={list(self.answers.keys())} latency={self.latency_ms:.1f}ms>"


# ---------------------------------------------------------------------------
# EmbedPrior Scorer
# ---------------------------------------------------------------------------

class EmbedPrior:
    """
    Zero-shot embedding similarity prior.
    Computes cosine similarity between an action-first state context and candidate hypotheses.
    Uses persistent HTTP sessions, input length capping, and non-fatal fallback.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        embed_model: str = "mxbai-embed-large",
        temperature: float = 0.85,
        max_chars: int = 1500,
        request_timeout: float = 5.0
    ):
        self.ollama_url = ollama_url
        self.embed_model = embed_model
        self.temperature = temperature
        self.max_chars = max_chars
        self.request_timeout = request_timeout
        self.session = requests.Session()
        self._hypothesis_cache: Dict[str, np.ndarray] = {}

    def _serialize_state(self, state: Union[Dict[str, Any], str]) -> str:
        """
        Serializes state placing Action & Target at the front to prevent truncation
        of critical execution details by embedding model token limits.
        """
        if not isinstance(state, dict):
            return str(state)[:self.max_chars]

        # Prioritize action, target, tool, and command at the front
        priority_keys = ["action", "tool", "target", "file", "target_file", "command", "cmd", "edit"]
        front_parts = []
        rest_parts = []

        for k, v in state.items():
            line = f"{k}: {v}"
            if k.lower() in priority_keys:
                front_parts.append(line)
            else:
                rest_parts.append(line)

        combined = "\n".join(front_parts + rest_parts)
        return combined[:self.max_chars]

    def _get_embeddings(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Fetch dense embeddings via persistent session.
        Returns None on connection error or timeout instead of crashing.
        """
        url = f"{self.ollama_url}/api/embed"
        try:
            resp = self.session.post(
                url,
                json={"model": self.embed_model, "input": texts},
                timeout=self.request_timeout
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if "embeddings" not in data:
                return None
            embeddings = np.array(data["embeddings"], dtype=np.float32)
            # L2-normalize
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1e-8
            return embeddings / norms
        except Exception:
            return None

    def _cache_key_for_question(self, q_name: str, q_obj: Union[Noul, Choice, Score]) -> str:
        """Generates a stable cache key including instructions, criteria, and threshold."""
        if isinstance(q_obj, Noul):
            raw = f"noul:{q_obj.instructions}:{q_obj.threshold}"
        elif isinstance(q_obj, Choice):
            criteria_str = ",".join(f"{k}={v}" for k, v in sorted(q_obj.criteria.items()))
            raw = f"choice:{q_obj.instructions}:{criteria_str}"
        elif isinstance(q_obj, Score):
            raw = f"score:{q_obj.instructions}:{q_obj.min_score}:{q_obj.max_score}"
        else:
            raw = f"unknown:{str(q_obj)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _get_or_compute_question_vectors(self, questions: Dict[str, Union[Noul, Choice, Score]]) -> Optional[Dict[str, np.ndarray]]:
        """Fetch or compute hypothesis vectors."""
        needed_texts = []
        needed_keys = []

        for q_name, q_obj in questions.items():
            key = self._cache_key_for_question(q_name, q_obj)
            if key not in self._hypothesis_cache:
                if isinstance(q_obj, Noul):
                    needed_texts.extend([
                        f"Assertion is true: {q_obj.instructions}",
                        f"Assertion is false: {q_obj.instructions}"
                    ])
                    needed_keys.append((key, 2))
                elif isinstance(q_obj, Choice):
                    texts = [
                        f"Category {opt}: {desc}" if desc else f"Category {opt}"
                        for opt, desc in q_obj.criteria.items()
                    ]
                    needed_texts.extend(texts)
                    needed_keys.append((key, len(texts)))
                elif isinstance(q_obj, Score):
                    texts = [
                        f"Score level {s}: {q_obj.rubric.get(s, '')}. Context: {q_obj.instructions}"
                        for s in range(q_obj.min_score, q_obj.max_score + 1)
                    ]
                    needed_texts.extend(texts)
                    needed_keys.append((key, len(texts)))

        if needed_texts:
            new_embs = self._get_embeddings(needed_texts)
            if new_embs is None:
                return None
            curr = 0
            for key, count in needed_keys:
                self._hypothesis_cache[key] = new_embs[curr:curr+count]
                curr += count

        q_vectors = {}
        for q_name, q_obj in questions.items():
            key = self._cache_key_for_question(q_name, q_obj)
            q_vectors[q_name] = self._hypothesis_cache[key]

        return q_vectors

    def system_one(self, state: Dict[str, Any], questions: Dict[str, Union[Noul, Choice, Score]]) -> EmbedPriorResponse:
        """
        Evaluates state against questions using zero-shot cosine similarity.
        Falls back safely if embeddings backend is unavailable.
        """
        t0 = time.time()
        state_text = self._serialize_state(state)

        # 1. Fetch hypothesis vectors
        q_vectors = self._get_or_compute_question_vectors(questions)

        # 2. Fetch state embedding
        state_embs = self._get_embeddings([state_text]) if q_vectors is not None else None

        # Fallback if Ollama unavailable or errored
        if q_vectors is None or state_embs is None:
            return self._build_fallback_response(questions, (time.time() - t0) * 1000.0)

        state_vec = state_embs[0]
        answers: Dict[str, Union[NoulResult, ChoiceResult, ScoreResult]] = {}

        for q_name, q_obj in questions.items():
            cand_vecs = q_vectors[q_name]
            sims = np.dot(cand_vecs, state_vec)

            # Softmax with temperature
            scaled_logits = sims / self.temperature
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
            probs = exp_logits / np.sum(exp_logits)

            if isinstance(q_obj, Noul):
                p_true = float(probs[0])
                answers[q_name] = NoulResult(
                    probability=round(p_true, 4),
                    boolean_value=(p_true >= q_obj.threshold),
                    confidence=round(abs(p_true - 0.5) * 2.0, 4),
                    status="ok"
                )
            elif isinstance(q_obj, Choice):
                options = list(q_obj.criteria.keys())
                dist = {opt: round(float(p), 4) for opt, p in zip(options, probs)}
                top_idx = int(np.argmax(probs))
                answers[q_name] = ChoiceResult(
                    selected_option=options[top_idx],
                    distribution=dist,
                    confidence=round(float(probs[top_idx]), 4),
                    status="ok"
                )
            elif isinstance(q_obj, Score):
                scores = list(range(q_obj.min_score, q_obj.max_score + 1))
                dist = {s: round(float(p), 4) for s, p in zip(scores, probs)}
                weighted_val = sum(s * p for s, p in zip(scores, probs))
                top_idx = int(np.argmax(probs))
                answers[q_name] = ScoreResult(
                    weighted_score=round(float(weighted_val), 2),
                    distribution=dist,
                    confidence=round(float(probs[top_idx]), 4),
                    status="ok"
                )

        latency_ms = (time.time() - t0) * 1000.0
        return EmbedPriorResponse(answers=answers, latency_ms=latency_ms)

    def _build_fallback_response(
        self,
        questions: Dict[str, Union[Noul, Choice, Score]],
        latency_ms: float
    ) -> EmbedPriorResponse:
        """Returns non-fatal neutral prior when embeddings backend is unreachable."""
        answers: Dict[str, Union[NoulResult, ChoiceResult, ScoreResult]] = {}
        for q_name, q_obj in questions.items():
            if isinstance(q_obj, Noul):
                answers[q_name] = NoulResult(
                    probability=0.5,
                    boolean_value=False,
                    confidence=0.0,
                    status="backend_error"
                )
            elif isinstance(q_obj, Choice):
                options = list(q_obj.criteria.keys())
                uniform_p = round(1.0 / max(len(options), 1), 4)
                answers[q_name] = ChoiceResult(
                    selected_option=options[0] if options else "unknown",
                    distribution={opt: uniform_p for opt in options},
                    confidence=uniform_p,
                    status="backend_error"
                )
            elif isinstance(q_obj, Score):
                scores = list(range(q_obj.min_score, q_obj.max_score + 1))
                mid = (q_obj.min_score + q_obj.max_score) / 2.0
                answers[q_name] = ScoreResult(
                    weighted_score=round(mid, 2),
                    distribution={s: round(1.0 / len(scores), 4) for s in scores},
                    confidence=0.0,
                    status="backend_error"
                )
        return EmbedPriorResponse(answers=answers, latency_ms=latency_ms)
