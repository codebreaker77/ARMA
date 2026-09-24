"""Deterministic Test-Diff Interrogator.

Re-exports from standalone arma_veto package for backwards compatibility.
"""

from arma_veto.interrogator import (
    TEST_FILE_PATTERN,
    detect_file_language,
    TestViolation,
    InterrogationReport,
    TestDiffInterrogator,
    main_cli,
)

__all__ = [
    "TEST_FILE_PATTERN",
    "detect_file_language",
    "TestViolation",
    "InterrogationReport",
    "TestDiffInterrogator",
    "main_cli",
]

if __name__ == "__main__":
    import sys
    sys.exit(main_cli())
