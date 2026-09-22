"""Entry point for E1: Loop Census."""
import sys
from experiments.offline.phase2_census import run_phase2_census

if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    run_phase2_census(split_filter=split)
