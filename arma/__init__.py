"""ARMA: Autonomous Reliability & Metacognitive Architecture for AI Coding Agents.

Public Python SDK:
- AgentGuard: Active reliability guardrail and verification gate.
- RepoWatcher: Real-time workspace monitor.
- TestDiffInterrogator: Sub-50ms polyglot test diff interrogator.
"""

__version__ = "0.2.0"

from arma.guard import AgentGuard, GuardVerdict, CommandVerdict
from arma.watcher import RepoWatcher
from arma_veto.interrogator import (
    TestDiffInterrogator,
    TestViolation,
    InterrogationReport,
    detect_file_language,
)

__all__ = [
    "AgentGuard",
    "GuardVerdict",
    "CommandVerdict",
    "RepoWatcher",
    "TestDiffInterrogator",
    "TestViolation",
    "InterrogationReport",
    "detect_file_language",
    "__version__",
]
