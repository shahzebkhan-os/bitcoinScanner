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
        """Serialize to JSON-safe dict for WebSocket broadcast."""
        return asdict(self)


def evaluate_consensus(results: List[SignalResult], config: dict) -> ConsensusResult:
    """
    Evaluate consensus from strategy results.

    Args:
        results: List of SignalResult from all strategies
        config: Configuration dict with min_votes threshold

    Returns:
        ConsensusResult with vote counts and final direction
    """
    try:
        # Count votes
        long_votes = sum(1 for r in results if r.direction == "LONG")
        short_votes = sum(1 for r in results if r.direction == "SHORT")
        neutral_votes = sum(1 for r in results if r.direction == "NEUTRAL")

        # Get min_votes threshold
        min_votes = config.get('min_votes', 3)

        # Determine consensus direction
        fired = False
        direction = "NEUTRAL"
        agreeing_strategies = []
        avg_strength = 0.0

        if long_votes >= min_votes:
            direction = "LONG"
            fired = True
            agreeing_strategies = [r.strategy_name for r in results if r.direction == "LONG"]
            avg_strength = sum(r.strength for r in results if r.direction == "LONG") / long_votes

        elif short_votes >= min_votes:
            direction = "SHORT"
            fired = True
            agreeing_strategies = [r.strategy_name for r in results if r.direction == "SHORT"]
            avg_strength = sum(r.strength for r in results if r.direction == "SHORT") / short_votes

        else:
            # No consensus
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
