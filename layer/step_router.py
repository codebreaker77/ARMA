"""
ARMA Cache-Aware Step Router (layer/step_router.py)
Per-step model routing controller that cuts API costs while guarding prompt cache prefixes.
Incorporates the empirical findings from 1,000 OpenHands SWE-rebench trajectories:
- Trivial read-only operations account for 16.4% of steps and 13.3% of input tokens.
- Naive per-step switching incurs 13,563 model switches and +$1,167 in cache invalidation penalties.
- Cache Hysteresis Guard: only routes to cheap tiers when savings exceed cold cache rewrite penalties.
"""

from enum import Enum
from typing import Dict, Any, Optional, Tuple


class StepTier(str, Enum):
    FRONTIER = "frontier"  # High reasoning: Claude 3.5 Sonnet / GPT-4o
    CHEAP = "cheap"        # Fast / low-cost: Claude 3.5 Haiku / Gemini 2.5 Flash


class StepCategory(str, Enum):
    TRIVIAL_READ = "trivial_read"
    TEST_VERIFICATION = "test_verification"
    CODE_MODIFICATION = "code_modification"
    PLANNING_REASONING = "planning_reasoning"
    GENERAL_TERMINAL = "general_terminal"


class RoutingDecision:
    def __init__(
        self,
        tier: StepTier,
        category: StepCategory,
        reason: str,
        cache_warm: bool,
        consecutive_reads: int
    ):
        self.tier = tier
        self.category = category
        self.reason = reason
        self.cache_warm = cache_warm
        self.consecutive_reads = consecutive_reads

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "category": self.category.value,
            "reason": self.reason,
            "cache_warm": self.cache_warm,
            "consecutive_reads": self.consecutive_reads
        }


class CacheAwareStepRouter:
    """
    Per-step model router that optimizes cost under real prompt-caching economics.
    """

    # Default pricing per million tokens (Claude 3.5 Sonnet vs Haiku)
    FRONTIER_INPUT_BASE = 3.00
    FRONTIER_CACHE_WRITE = 3.75
    FRONTIER_CACHE_READ = 0.30
    FRONTIER_OUTPUT_BASE = 15.00

    CHEAP_INPUT_BASE = 0.80
    CHEAP_CACHE_WRITE = 1.00
    CHEAP_CACHE_READ = 0.08
    CHEAP_OUTPUT_BASE = 4.00

    # Minimum consecutive read-only steps required before model switch is economically viable
    # (Accounts for the $3.45/M penalty of rewriting the frontier cache upon return)
    MIN_CONSECUTIVE_READS_FOR_SWITCH = 4

    def __init__(self):
        self.consecutive_read_steps = 0
        self.current_tier = StepTier.FRONTIER
        self.is_frontier_cache_warm = False

    def classify_intent(self, tool_name: str, tool_args: Dict[str, Any]) -> StepCategory:
        """Categorize incoming tool intent into behavioral categories."""
        if not tool_name:
            return StepCategory.PLANNING_REASONING

        t_lower = tool_name.lower()
        args_str = str(tool_args).lower()

        # 1. Test execution
        if any(kw in args_str for kw in ("pytest", "python -m unittest", "tox", "nosetests", "test_")):
            return StepCategory.TEST_VERIFICATION

        # 2. Code modification
        if any(w in t_lower for w in ("edit", "write", "patch", "replace")) or "git checkout" in args_str:
            return StepCategory.CODE_MODIFICATION

        # 3. Trivial read-only inspection
        if any(r in t_lower for r in ("read", "view", "open")) or any(r in args_str for r in ("cat ", "head ", "tail ", "grep ", "find ", "ls ")):
            return StepCategory.TRIVIAL_READ

        return StepCategory.GENERAL_TERMINAL

    def route_step(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context_tokens: int = 15000
    ) -> RoutingDecision:
        """
        Computes the optimal model tier for the next step, guarding warm prompt cache prefixes.
        """
        category = self.classify_intent(tool_name, tool_args)

        if category == StepCategory.TRIVIAL_READ:
            self.consecutive_read_steps += 1
        else:
            self.consecutive_read_steps = 0

        # Critical or complex steps must always stay on the Frontier tier
        if category in (StepCategory.CODE_MODIFICATION, StepCategory.TEST_VERIFICATION, StepCategory.PLANNING_REASONING):
            self.current_tier = StepTier.FRONTIER
            self.is_frontier_cache_warm = True
            return RoutingDecision(
                tier=StepTier.FRONTIER,
                category=category,
                reason="High-complexity modification/verification requires frontier reasoning capability.",
                cache_warm=self.is_frontier_cache_warm,
                consecutive_reads=self.consecutive_read_steps
            )

        # For trivial read-only operations: evaluate Cache Hysteresis
        if category == StepCategory.TRIVIAL_READ:
            if not self.is_frontier_cache_warm:
                # Cold cache: safe to route to cheap model
                self.current_tier = StepTier.CHEAP
                return RoutingDecision(
                    tier=StepTier.CHEAP,
                    category=category,
                    reason="Frontier cache is cold; routing trivial read to cheap tier.",
                    cache_warm=False,
                    consecutive_reads=self.consecutive_read_steps
                )

            # If frontier cache is warm, check if we have enough batched reads to justify cache rewrite penalty
            if self.consecutive_read_steps >= self.MIN_CONSECUTIVE_READS_FOR_SWITCH:
                self.current_tier = StepTier.CHEAP
                return RoutingDecision(
                    tier=StepTier.CHEAP,
                    category=category,
                    reason=f"Batched read sequence ({self.consecutive_read_steps} turns) offsets cache invalidation penalty.",
                    cache_warm=True,
                    consecutive_reads=self.consecutive_read_steps
                )
            else:
                # Isolated read: Stay on frontier to maintain warm prompt cache
                return RoutingDecision(
                    tier=StepTier.FRONTIER,
                    category=category,
                    reason="Cache Hysteresis Guard: Preserving warm frontier cache ($0.30/M read) beats switching to cheap model ($3.75/M rewrite penalty).",
                    cache_warm=True,
                    consecutive_reads=self.consecutive_read_steps
                )

        # Default fallback
        return RoutingDecision(
            tier=StepTier.FRONTIER,
            category=category,
            reason="Defaulting to frontier tier for terminal execution.",
            cache_warm=self.is_frontier_cache_warm,
            consecutive_reads=self.consecutive_read_steps
        )
