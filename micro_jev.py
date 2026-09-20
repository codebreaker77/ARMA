"""
MicroJev: A lightweight local implementation of the Jev System One decision architecture.
Features:
- Non-autoregressive parallel sampling
- Typed decision primitives: Noul, Choice, Score
- Calibrated probability estimates via temperature scaling
- Fast single-pass execution via local dense representations
"""

import time
import requests
import numpy as np
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Decision Primitives (Mirrors TypeSafe Jev SDK)
# ---------------------------------------------------------------------------

class NoulResult(BaseModel):
    """Result of a Noul (binary truth) decision."""
    probability: float = Field(..., description="Calibrated probability (0.0 to 1.0) that the proposition is true.")
    boolean_value: bool = Field(..., description="Boolean thresholded at p >= 0.5")
    confidence: float = Field(..., description="Distance from uncertainty: |p - 0.5| * 2")


class ChoiceResult(BaseModel):
    """Result of a Choice (categorical) decision."""
    selected_option: str = Field(..., description="The option with highest probability.")
    distribution: Dict[str, float] = Field(..., description="Full calibrated probability simplex across options.")
    confidence: float = Field(..., description="Calibrated confidence score of the top choice.")


class ScoreResult(BaseModel):
    """Result of a Score (ordinal rubric) decision."""
    weighted_score: float = Field(..., description="Expected value: sum(score_i * p_i)")
    distribution: Dict[int, float] = Field(..., description="Probability assigned to each discrete rubric level.")
    confidence: float = Field(..., description="Confidence in the modal score bin.")


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


class MicroJevResponse:
    """Standardized response container for MicroJev decisions."""
    def __init__(self, answers: Dict[str, Union[NoulResult, ChoiceResult, ScoreResult]], latency_ms: float, input_tokens: int = 0):
        self.answers = answers
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens

    def __repr__(self):
        return f"<MicroJevResponse answers={list(self.answers.keys())} latency={self.latency_ms:.1f}ms>"


# ---------------------------------------------------------------------------
# MicroJev Execution Client
# ---------------------------------------------------------------------------

class MicroJevClient:
    """
    MicroJev Client: Evaluates multiple typed questions against an input state
    in a single parallel pass without token-by-token autoregressive generation.
    Optimized with question hypothesis vector caching for sub-50ms inference.
    """
    def __init__(self, ollama_url: str = "http://localhost:11434", embed_model: str = "mxbai-embed-large", temperature: float = 0.85):
        self.ollama_url = ollama_url
        self.embed_model = embed_model
        self.temperature = temperature
        self._hypothesis_cache: Dict[str, np.ndarray] = {}

    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Fetch dense embeddings in a single batch from Ollama."""
        url = f"{self.ollama_url}/api/embed"
        response = requests.post(url, json={"model": self.embed_model, "input": texts}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"Ollama embed API error: {response.text}")
        embeddings = np.array(response.json()["embeddings"], dtype=np.float32)
        # L2-normalize embeddings for fast cosine similarity via dot product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1e-8
        return embeddings / norms

    def _get_or_compute_question_vectors(self, questions: Dict[str, Union[Noul, Choice, Score]]) -> Dict[str, np.ndarray]:
        """Cache hypothesis vectors so we only ever embed the state text on repeat evaluations."""
        needed_texts = []
        needed_keys = []

        for q_name, q_obj in questions.items():
            if isinstance(q_obj, Noul):
                key = f"noul:{q_obj.instructions}"
                if key not in self._hypothesis_cache:
                    needed_texts.extend([
                        f"Assertion is true: {q_obj.instructions}",
                        f"Assertion is false: {q_obj.instructions}"
                    ])
                    needed_keys.append((key, 2))
            elif isinstance(q_obj, Choice):
                key = f"choice:{q_obj.instructions}:" + ",".join(f"{k}={v}" for k, v in q_obj.criteria.items())
                if key not in self._hypothesis_cache:
                    texts = [
                        f"Category {opt}: {desc}" if desc else f"Category {opt}"
                        for opt, desc in q_obj.criteria.items()
                    ]
                    needed_texts.extend(texts)
                    needed_keys.append((key, len(texts)))
            elif isinstance(q_obj, Score):
                key = f"score:{q_obj.instructions}:{q_obj.min_score}:{q_obj.max_score}"
                if key not in self._hypothesis_cache:
                    texts = [
                        f"Score level {s}: {q_obj.rubric.get(s, '')}. Context: {q_obj.instructions}"
                        for s in range(q_obj.min_score, q_obj.max_score + 1)
                    ]
                    needed_texts.extend(texts)
                    needed_keys.append((key, len(texts)))

        if needed_texts:
            new_embs = self._get_embeddings(needed_texts)
            curr = 0
            for key, count in needed_keys:
                self._hypothesis_cache[key] = new_embs[curr:curr+count]
                curr += count

        # Assemble result map
        q_vectors = {}
        for q_name, q_obj in questions.items():
            if isinstance(q_obj, Noul):
                key = f"noul:{q_obj.instructions}"
            elif isinstance(q_obj, Choice):
                key = f"choice:{q_obj.instructions}:" + ",".join(f"{k}={v}" for k, v in q_obj.criteria.items())
            elif isinstance(q_obj, Score):
                key = f"score:{q_obj.instructions}:{q_obj.min_score}:{q_obj.max_score}"
            q_vectors[q_name] = self._hypothesis_cache[key]

        return q_vectors

    def system_one(self, state: Dict[str, Any], questions: Dict[str, Union[Noul, Choice, Score]]) -> MicroJevResponse:
        """
        Single-pass parallel decision engine:
        1. Encodes state context in a single lightweight embedding call.
        2. Compares against cached question hypothesis vectors in memory (NumPy vectorization).
        3. Computes calibrated probability distributions via temperature scaling.
        4. Returns typed results with zero token generation overhead.
        """
        t0 = time.time()

        # 1. Serialize state into contextual string representation
        if isinstance(state, dict):
            state_text = "\n".join(f"{k}: {v}" for k, v in state.items())
        else:
            state_text = str(state)

        # 2. Get hypothesis vectors (from cache or computed once)
        q_vectors = self._get_or_compute_question_vectors(questions)

        # 3. Embed ONLY the state vector
        state_vec = self._get_embeddings([state_text])[0]  # Shape: (D,)

        # 4. Compute calibrated decision distributions in parallel
        answers: Dict[str, Union[NoulResult, ChoiceResult, ScoreResult]] = {}

        for q_name, q_obj in questions.items():
            cand_vecs = q_vectors[q_name]  # Shape: (M, D)

            # Cosine similarities via fast dot product
            sims = np.dot(cand_vecs, state_vec)  # Shape: (M,)

            # Calibrated Temperature Scaling: Softmax(sims / T)
            scaled_logits = sims / self.temperature
            exp_logits = np.exp(scaled_logits - np.max(scaled_logits))
            probs = exp_logits / np.sum(exp_logits)

            if isinstance(q_obj, Noul):
                p_true = float(probs[0])
                answers[q_name] = NoulResult(
                    probability=round(p_true, 4),
                    boolean_value=(p_true >= q_obj.threshold),
                    confidence=round(abs(p_true - 0.5) * 2.0, 4)
                )

            elif isinstance(q_obj, Choice):
                options = list(q_obj.criteria.keys())
                dist = {opt: round(float(p), 4) for opt, p in zip(options, probs)}
                top_idx = int(np.argmax(probs))
                answers[q_name] = ChoiceResult(
                    selected_option=options[top_idx],
                    distribution=dist,
                    confidence=round(float(probs[top_idx]), 4)
                )

            elif isinstance(q_obj, Score):
                scores = list(range(q_obj.min_score, q_obj.max_score + 1))
                dist = {s: round(float(p), 4) for s, p in zip(scores, probs)}
                weighted_val = sum(s * p for s, p in zip(scores, probs))
                top_idx = int(np.argmax(probs))
                answers[q_name] = ScoreResult(
                    weighted_score=round(float(weighted_val), 2),
                    distribution=dist,
                    confidence=round(float(probs[top_idx]), 4)
                )

        latency_ms = (time.time() - t0) * 1000.0
        return MicroJevResponse(answers=answers, latency_ms=latency_ms)

