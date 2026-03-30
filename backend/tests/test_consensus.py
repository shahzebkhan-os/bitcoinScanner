from scanner.consensus import evaluate_consensus
from scanner.strategies import SignalResult


def _result(name, direction, strength=0.5):
    return SignalResult(strategy_name=name, direction=direction, strength=strength, reason="test")


def test_consensus_fires_long_when_threshold_met(base_config):
    results = [
        _result("s1", "LONG", 0.8),
        _result("s2", "LONG", 0.7),
        _result("s3", "LONG", 0.6),
        _result("s4", "NEUTRAL", 0),
    ]
    c = evaluate_consensus(results, base_config)
    assert c.direction == "LONG"
    assert c.fired is True
    assert c.long_votes == 3
    assert c.short_votes == 0
    assert c.neutral_votes == 1


def test_consensus_fires_short_when_threshold_met(base_config):
    results = [
        _result("s1", "SHORT", 0.8),
        _result("s2", "SHORT", 0.7),
        _result("s3", "SHORT", 0.6),
        _result("s4", "NEUTRAL", 0),
    ]
    c = evaluate_consensus(results, base_config)
    assert c.direction == "SHORT"
    assert c.fired is True


def test_consensus_neutral_on_tie(base_config):
    config = dict(base_config)
    config["min_votes"] = 3
    results = [
        _result("s1", "LONG"),
        _result("s2", "LONG"),
        _result("s3", "LONG"),
        _result("s4", "SHORT"),
        _result("s5", "SHORT"),
        _result("s6", "SHORT"),
    ]
    c = evaluate_consensus(results, config)
    assert c.direction == "NEUTRAL"
    assert c.fired is False


def test_consensus_to_dict_is_camelcase(base_config):
    results = [
        _result("s1", "LONG"),
        _result("s2", "LONG"),
        _result("s3", "LONG"),
    ]
    payload = evaluate_consensus(results, base_config).to_dict()
    assert "longVotes" in payload
    assert "shortVotes" in payload
    assert "avgStrength" in payload
    assert "agreeingStrategies" in payload


def test_consensus_strength_filter_reduces_vote_count(base_config):
    """Votes with strength below min_signal_strength are excluded from the count."""
    config = dict(base_config)
    config["signal_filters"] = {"min_signal_strength": 0.4}
    results = [
        _result("s1", "LONG", 0.8),
        _result("s2", "LONG", 0.7),
        _result("s3", "LONG", 0.2),   # below threshold — should not count
        _result("s4", "NEUTRAL", 0),
    ]
    c = evaluate_consensus(results, config)
    # Only 2 valid LONG votes (s3 excluded), below min_votes=3 → NEUTRAL
    assert c.long_votes == 2
    assert c.direction == "NEUTRAL"
    assert c.fired is False


def test_consensus_strength_filter_allows_signal_when_enough_votes(base_config):
    """Enough strong votes still fire even with the strength filter active."""
    config = dict(base_config)
    config["signal_filters"] = {"min_signal_strength": 0.4}
    results = [
        _result("s1", "LONG", 0.9),
        _result("s2", "LONG", 0.8),
        _result("s3", "LONG", 0.7),
        _result("s4", "NEUTRAL", 0),
    ]
    c = evaluate_consensus(results, config)
    assert c.direction == "LONG"
    assert c.fired is True
    assert c.long_votes == 3


def test_consensus_long_wins_over_short_when_more_votes(base_config):
    """LONG wins over SHORT when LONG has more qualifying votes."""
    results = [
        _result("s1", "LONG", 0.8),
        _result("s2", "LONG", 0.7),
        _result("s3", "LONG", 0.6),
        _result("s4", "SHORT", 0.8),
        _result("s5", "SHORT", 0.7),
        _result("s6", "NEUTRAL", 0),
    ]
    c = evaluate_consensus(results, base_config)
    assert c.direction == "LONG"
    assert c.fired is True
