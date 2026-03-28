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
    config["min_votes"] = 4
    results = [
        _result("s1", "LONG"),
        _result("s2", "LONG"),
        _result("s3", "SHORT"),
        _result("s4", "SHORT"),
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
