"""Configuration, constants, splitting, and statistical utilities for ARMA offline experiments."""

import hashlib
import os
from typing import Callable, Tuple, List, Dict, Any
import numpy as np
import pandas as pd
import tiktoken

DATASET_NAME = "nebius/SWE-rebench-openhands-trajectories"
DATASET_REVISION = "35455389ab51bf5e2306bfd436ef72d0f98bf882"
SAMPLE_N = 2000
RANDOM_SEED = 42
DEV_RATIO = 0.70

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
SAMPLED_DATA_PATH = os.path.join(DATA_DIR, "sampled_trajectories_2000.parquet")
PARQUET_CACHE_DIR = DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

_TOKEN_ENCODER = None

def estimate_tokens(text: str) -> int:
    """Estimate token count using tiktoken cl100k_base proxy."""
    global _TOKEN_ENCODER
    if _TOKEN_ENCODER is None:
        _TOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
    if not text:
        return 0
    return len(_TOKEN_ENCODER.encode(str(text), disallowed_special=()))

def estimate_message_tokens(message: Dict[str, Any]) -> int:
    """Estimate tokens for an entire trajectory message dict."""
    total = 0
    content = message.get("content")
    if content:
        total += estimate_tokens(content)
    tool_calls = message.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict):
                func = tc.get("function", {})
                if isinstance(func, dict):
                    total += estimate_tokens(func.get("name", ""))
                    total += estimate_tokens(func.get("arguments", ""))
    return total

def get_repo_hash_val(repo: str) -> int:
    """Deterministic hash of repo name into integer [0, 999]."""
    return int(hashlib.sha256(repo.encode("utf-8")).hexdigest(), 16) % 1000

def is_dev_repo(repo: str) -> bool:
    """70% dev / 30% test split based strictly on repo hash."""
    return get_repo_hash_val(repo) < int(DEV_RATIO * 1000)

def cluster_bootstrap_ci(
    df: pd.DataFrame,
    metric_fn: Callable[[pd.DataFrame], float],
    group_col: str = "repo",
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = RANDOM_SEED,
) -> Tuple[float, float]:
    """Compute 95% Confidence Interval using cluster bootstrap by group (repo)."""
    rng = np.random.RandomState(seed)
    # Pre-group row indices by repo for high performance
    grouped_indices = df.groupby(group_col).indices
    group_names = np.array(list(grouped_indices.keys()))
    n_groups = len(group_names)

    boot_vals = np.empty(n_resamples, dtype=float)
    for i in range(n_resamples):
        sampled_groups = rng.choice(group_names, size=n_groups, replace=True)
        sampled_idx = np.concatenate([grouped_indices[g] for g in sampled_groups])
        sampled_df = df.iloc[sampled_idx]
        boot_vals[i] = metric_fn(sampled_df)

    lower = float(np.percentile(boot_vals, 100 * (alpha / 2)))
    upper = float(np.percentile(boot_vals, 100 * (1 - alpha / 2)))
    return lower, upper
