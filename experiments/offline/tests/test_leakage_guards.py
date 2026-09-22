"""Mandatory leakage guard unit tests.

Verifies:
1. Suffix-invariance: For any (trajectory, t), replacing everything in trajectory[t:]
   with arbitrary garbage, corrupted messages, or synthetic strings produces
   bit-for-bit identical features.
"""

import copy
import random
import numpy as np
import pandas as pd
import pytest

from experiments.offline.config import SAMPLED_DATA_PATH
from experiments.offline.features import extract_prefix_features, FEATURE_NAMES

def test_suffix_invariance():
    df = pd.read_parquet(SAMPLED_DATA_PATH)
    rng = random.Random(42)
    
    # Sample 20 random trajectories
    sample_indices = rng.sample(range(len(df)), 20)
    
    for idx in sample_indices:
        traj = df.iloc[idx]["trajectory"]
        n_msgs = len(traj)
        if n_msgs < 20:
            continue
            
        for t in [10, 20, 30, 40]:
            if t >= n_msgs:
                continue
                
            # Compute baseline features
            features_clean = extract_prefix_features(traj, t)
            
            # Corrupt everything after step t with adversarial garbage
            corrupted_traj = copy.deepcopy(traj)
            for k in range(t, n_msgs):
                corrupted_traj[k] = {
                    "role": rng.choice(["assistant", "tool", "user", "corrupted"]),
                    "content": f"GARBAGE_INJECTION_DATA_LEAK_TEST_TOKEN_{rng.randint(10000, 99999)}",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "execute_bash",
                                "arguments": '{"command": "pytest --fake-test-run-leakage"}'
                            }
                        }
                    ] if rng.random() > 0.5 else None,
                }
                
            features_corrupted = extract_prefix_features(corrupted_traj, t)
            
            # Invariant: Features must be bit-for-bit identical
            for f_name in FEATURE_NAMES:
                val_clean = features_clean[f_name]
                val_corrupt = features_corrupted[f_name]
                assert val_clean == val_corrupt, (
                    f"LEAKAGE DETECTED! Feature '{f_name}' changed at t={t} for traj {idx}: "
                    f"clean={val_clean} vs corrupt={val_corrupt}"
                )

def test_feature_count():
    sample_traj = [
        {"role": "system", "content": "You are OpenHands."},
        {"role": "user", "content": "Fix bug."},
        {"role": "assistant", "tool_calls": [{"function": {"name": "execute_bash", "arguments": '{"command": "ls"}'}}]},
        {"role": "tool", "content": "file1.py file2.py"},
    ]
    feat = extract_prefix_features(sample_traj, t=3)
    assert len(feat) == len(FEATURE_NAMES)
    for k in FEATURE_NAMES:
        assert k in feat
