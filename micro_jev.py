"""
micro_jev.py: Backwards-compatible legacy adapter for layer.embed_prior.

DEPRECATION & IMPLEMENTATION NOTICE:
This module is preserved for backwards compatibility with earlier prototypes.
Under the hood, it delegates to EmbedPrior (layer/embed_prior.py), which is an
uncalibrated zero-shot embedding-similarity heuristic.

As demonstrated empirically, Noul probabilities against binary negation pairs
are compressed near 0.5 (AUROC ~ 0.50). For discriminative classification,
use SupervisedEmbedClassifier or ClassifierLadder from layer.classifier_ladder.
"""

import warnings
from layer.embed_prior import (
    Noul,
    Choice,
    Score,
    NoulResult,
    ChoiceResult,
    ScoreResult,
    EmbedPrior,
    EmbedPriorResponse as MicroJevResponse
)


class MicroJevClient(EmbedPrior):
    """
    Legacy wrapper around EmbedPrior.
    Provides uncalibrated zero-shot embedding similarity prior.
    """
    def __init__(self, ollama_url: str = "http://localhost:11434", embed_model: str = "mxbai-embed-large", temperature: float = 0.85):
        super().__init__(
            ollama_url=ollama_url,
            embed_model=embed_model,
            temperature=temperature
        )


__all__ = [
    "Noul",
    "Choice",
    "Score",
    "NoulResult",
    "ChoiceResult",
    "ScoreResult",
    "MicroJevResponse",
    "MicroJevClient",
    "EmbedPrior"
]
