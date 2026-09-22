"""Export random sample of 100 steps to sample_for_human_labels.csv for human validation."""

import csv
import json
import os
import random
import pandas as pd

from experiments.offline.config import SAMPLED_DATA_PATH, RESULTS_DIR, RANDOM_SEED
from experiments.offline.parser import extract_step_action

def export_human_sample(n_steps: int = 100, seed: int = RANDOM_SEED):
    df = pd.read_parquet(SAMPLED_DATA_PATH)
    rng = random.Random(seed)
    
    # Collect all steps with tool calls
    all_steps = []
    for traj_idx, row in df.iterrows():
        traj_id = row["trajectory_id"]
        repo = row["repo"]
        traj = row["trajectory"]
        for step_idx, msg in enumerate(traj):
            res = extract_step_action(msg)
            if res is not None:
                cls, summary = res
                all_steps.append({
                    "trajectory_id": traj_id,
                    "repo": repo,
                    "step_idx": step_idx,
                    "step_text": summary,
                    "predicted_class": cls,
                })
                
    print(f"Total tool call steps across {len(df)} trajectories: {len(all_steps)}")
    
    # Stratified or random sample of 100 steps
    # To ensure good coverage of all 4 classes in the human sample, sample ~25 from each class if possible, or uniform random
    # The prompt specifies: "Export a random sample of 100 steps to sample_for_human_labels.csv (step text, predicted class)"
    chosen = rng.sample(all_steps, n_steps)
    
    out_csv = os.path.join(RESULTS_DIR, "sample_for_human_labels.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_id", "trajectory_id", "repo", "step_idx", "step_text", "predicted_class", "human_label"])
        for i, item in enumerate(chosen, 1):
            writer.writerow([
                i,
                item["trajectory_id"],
                item["repo"],
                item["step_idx"],
                item["step_text"],
                item["predicted_class"],
                ""  # empty for user to label
            ])
            
    print(f"Exported {n_steps} sampled steps to {out_csv}")
    
    # Print class distribution of the 100 samples
    counts = {}
    for item in chosen:
        c = item["predicted_class"]
        counts[c] = counts.get(c, 0) + 1
    print("Class distribution in sample:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

if __name__ == "__main__":
    export_human_sample()
