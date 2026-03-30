"""
Consensus Module - scanner/consensus.py

Responsibilities:
- Aggregate strategy votes
- Apply min_votes threshold (consensus filter)
- Calculate average strength
"""

import logging
from dataclasses import dataclass, asdict
from typing import List

from scanner.strategies import SignalResult

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    """Result of consensus vote aggregation."""
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    long_votes: int
    short_votes: int
    neutral_votes: int
    avg_strength: float
    agreeing_strategies: list[str]
    fired: bool

    def to_dict(self) -> dict:
        """Serialize to JSON-safe camelCase dict for WebSocket broadcast."""
        return {
            "direction": self.direction,
            "longVotes": self.long_votes,
            "shortVotes": self.short_votes,
            "neutralVotes": self.neutral_votes,
            "avgStrength": round(self.avg_strength, 4),
            "agreeingStrategies": self.agreeing_strategies,
            "fired": self.fired
        }


def evaluate_consensus(results: List[SignalResult], config: dict) -> ConsensusResult:
    """
    Evaluate consensus from strategy results.

    Args:
        results: List of SignalResult from all strategies
        config: Configuration dict with min_votes threshold

    Returns:
        ConsensusResult with vote counts and final direction

    Accuracy improvements:
    - Optional min_signal_strength filter: strategies with strength below the
      threshold do not count towards the vote (avoids weak/uncertain votes
      inflating consensus counts).
    - Tie-breaking: LONG only fires when long_votes > short_votes; when both
      directions meet min_votes with equal counts the result is NEUTRAL (no
      signal). This is intentional: ambiguous markets should not fire a trade.
      The rationale is that a genuine consensus requires one side to dominate.
    """
    try:
        # Get min_votes threshold and optional strength filter
        min_votes = config.get('min_votes', 3)
        filters = config.get('signal_filters', {})
        min_strength = float(filters.get('min_signal_strength', 0.0))

        # Count votes, optionally filtering by minimum strength
        long_results = [r for r in results if r.direction == "LONG" and r.strength >= min_strength]
        short_results = [r for r in results if r.direction == "SHORT" and r.strength >= min_strength]
        # Neutral includes both genuine neutrals and votes filtered out by strength threshold
        long_votes = len(long_results)
        short_votes = len(short_results)
        neutral_votes = len(results) - long_votes - short_votes

        # Determine consensus direction
        fired = False
        direction = "NEUTRAL"
        agreeing_strategies = []
        avg_strength = 0.0

        if long_votes >= min_votes and long_votes > short_votes:
            direction = "LONG"
            fired = True
            agreeing_strategies = [r.strategy_name for r in long_results]
            avg_strength = sum(r.strength for r in long_results) / long_votes

        elif short_votes >= min_votes and short_votes > long_votes:
            direction = "SHORT"
            fired = True
            agreeing_strategies = [r.strategy_name for r in short_results]
            avg_strength = sum(r.strength for r in short_results) / short_votes

        else:
            # No consensus or tied
            direction = "NEUTRAL"
            fired = False
            agreeing_strategies = []
            avg_strength = 0.0

        consensus = ConsensusResult(
            direction=direction,
            long_votes=long_votes,
            short_votes=short_votes,
            neutral_votes=neutral_votes,
            avg_strength=avg_strength,
            agreeing_strategies=agreeing_strategies,
            fired=fired
        )

        if fired:
            logger.info(f"Consensus FIRED: {direction} with {len(agreeing_strategies)} votes (strength: {avg_strength:.2f})")

        return consensus

    except Exception as e:
        logger.error(f"Error evaluating consensus: {e}", exc_info=True)
        # Return neutral consensus on error
        return ConsensusResult(
            direction="NEUTRAL",
            long_votes=0,
            short_votes=0,
            neutral_votes=len(results),
            avg_strength=0.0,
            agreeing_strategies=[],
            fired=False
        )
