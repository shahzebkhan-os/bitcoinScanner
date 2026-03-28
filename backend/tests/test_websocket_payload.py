import json
from datetime import datetime, timezone

import pytest

from api.websocket_server import broadcast_tick, broadcast_signal, manager
from scanner.consensus import ConsensusResult
from scanner.indicators import IndicatorSnapshot
from scanner.strategies import SignalResult


class DummyWebSocket:
    def __init__(self):
        self.messages = []

    async def send_text(self, message: str):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_broadcast_tick_payload_contract_is_camelcase():
    ws = DummyWebSocket()
    manager.active_connections = [ws]

    snapshot = IndicatorSnapshot(
        ema_fast=1,
        ema_slow=1,
        ema_crossover="none",
        rsi=50,
        macd_line=0,
        macd_signal=0,
        macd_histogram=0,
        macd_cross="none",
        bb_upper=2,
        bb_middle=1,
        bb_lower=0.5,
        bb_bandwidth=0.2,
        close_vs_bb="inside",
        vwap=1,
        close_vs_vwap="above",
        current_volume=100,
        avg_volume=90,
        volume_ratio=1.1,
        current_price=100,
        timestamp=datetime.now(timezone.utc),
    )
    results = [SignalResult("S", "LONG", 0.7, "ok")]
    consensus = ConsensusResult("LONG", 3, 0, 3, 0.7, ["S"], True)

    await broadcast_tick(
        candles=[{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
        snapshot=snapshot,
        results=results,
        consensus=consensus,
        overall_trend={"timeHorizon": "next_1m"},
        strategies_by_interval={"1m": []},
        consensus_by_interval={"1m": consensus.to_dict()},
    )

    payload = json.loads(ws.messages[-1])
    assert payload["type"] == "tick"
    assert "signalFired" in payload
    assert "overallTrend" in payload
    assert "strategiesByInterval" in payload
    assert "consensusByInterval" in payload
    assert "volumeRatio" in payload["indicators"]
    assert "longVotes" in payload["consensus"]
    assert "shortVotes" in payload["consensus"]
    assert "avgStrength" in payload["consensus"]
    assert "agreeingStrategies" in payload["consensus"]
    assert "fired" in payload["consensus"]
    assert "long_votes" not in payload["consensus"]


@pytest.mark.asyncio
async def test_broadcast_signal_payload_contains_trade_levels():
    ws = DummyWebSocket()
    manager.active_connections = [ws]

    snapshot = IndicatorSnapshot(
        ema_fast=1,
        ema_slow=1,
        ema_crossover="none",
        rsi=50,
        macd_line=0,
        macd_signal=0,
        macd_histogram=0,
        macd_cross="none",
        bb_upper=2,
        bb_middle=1,
        bb_lower=0.5,
        bb_bandwidth=0.2,
        close_vs_bb="inside",
        vwap=1,
        close_vs_vwap="above",
        current_volume=100,
        avg_volume=90,
        volume_ratio=1.1,
        current_price=100,
        timestamp=datetime.now(timezone.utc),
    )
    consensus = ConsensusResult("LONG", 3, 0, 3, 0.7, ["S"], True)

    await broadcast_signal(
        consensus,
        snapshot,
        trade_levels={
            "entry": 100,
            "stopLoss": 99,
            "target": 101.5,
            "targetRr": 1.5,
            "interval": "1m",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "direction": "LONG",
        },
    )
    payload = json.loads(ws.messages[-1])
    assert payload["type"] == "signal"
    assert "volumeRatio" in payload
    assert "tradeLevels" in payload
    assert payload["tradeLevels"]["stopLoss"] == 99
