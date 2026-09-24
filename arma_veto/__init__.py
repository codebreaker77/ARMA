"""arma-veto: Sub-50ms deterministic test-tampering and evasion linter for AI coding agents.

Catches reward-hacking patterns (deleted tests, injected skips, swallowed exceptions,
and stripped assertions) across Python, JavaScript/TypeScript, Go, and Rust.
"""

__version__ = "0.1.0"

from arma_veto.interrogator import (
    TestDiffInterrogator,
    TestViolation,
    InterrogationReport,
    detect_file_language,
    main_cli,
)

__all__ = [
    "TestDiffInterrogator",
    "TestViolation",
    "InterrogationReport",
    "detect_file_language",
    "main_cli",
    "__version__",
]
