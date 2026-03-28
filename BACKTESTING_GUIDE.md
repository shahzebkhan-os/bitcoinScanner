# 🔬 Backtesting Engine Guide

The Bitcoin Scanner Backtesting engine allows you to simulate your trading strategy on up to 50,000 historical candles. It uses a realistic **Position State Machine** to replicate live trading conditions.

## 🛠️ How It Works (The Logic)

The backtester follows a high-performance 5-step process to ensure accuracy and speed:

1.  **Data Fetching**: The system retrieves the requested number of historical candles (1k to 50k) for the selected pair and interval from Binance.
2.  **Vectorized Indicators**: All 6 technical indicators (RSI, EMA, MACD, etc.) and strategy votes are calculated simultaneously using Pandas for maximum speed.
3.  **Consensus Scoring**: Each candle is assigned a "Long Vote" and "Short Vote" count (from 0 to 6) based on indicator alignment.
4.  **Position State Machine**: The engine then loops through every candle chronologically. It maintains a **State** (Flat, Long, or Short).
    - If **Flat**: Enter if votes ≥ `Min Votes`.
    - If **Open**: Exit if opposite votes ≥ `Min Exit Votes`.
5.  **P&L & Stats Generation**: After the simulation, the system calculates the final capital, max drawdown, and directional win rates for the report.

## 🚀 Core Engine Principles

Unlike simple backtesters that check every signal independently, this engine follows strict execution rules:
- **One-Trade-at-a-Time**: Only one position (LONG or SHORT) can be active. No new trades are entered until the current one is closed.
- **Signal-Based Exits**: Positions are closed based on technical reversals, not fixed Stop-Loss/Take-Profit levels.
- **Immediate Flipping**: If a SHORT signal reaches consensus while you are in a LONG, the system will close the LONG and immediately open the SHORT in the same candle.

---

## 📊 Strategy & Consensus

The system calculates **6 independent signals**. A trade is entered only when the **Min Votes** (Consensus) threshold is met.

### The 6 Strategies:
1. **EMA Alignment**: Bullish when `Fast EMA > Slow EMA`.
2. **RSI/Bollinger**: Bullish when oversold and below lower band.
3. **VWAP Position**: Bullish when trading above VWAP with volume.
4. **Range Trading**: Buying near support in sideways markets.
5. **Breakout**: Entering strong moves above 20-period highs.
6. **MACD Momentum**: Bullish when MACD histogram is positive.

> [!TIP]
> **Consensus Fix**: EMA and MACD are "State-Based." This means they contribute a vote as long as they are aligned, making `Min Votes = 4` a powerful filter for high-quality trend-following entries.

---

## 🛡️ Strategy Filters

Enable these in the sidebar to reduce "noise" and improve your win rate:

| Filter | Description |
|--------|-------------|
| **Trend Filter** | Blocks LONGs if `EMA Fast < EMA Slow` (and vice versa). |
| **Volume Confirm** | Requires volume to be X% above the 20-bar average. |
| **HTF Bias** | Uses a long-period EMA to ensure you are trading with the 15m/hourly trend. |

---

## 💰 Capital & Risk

- **Initial Capital**: Starting balance for the simulation.
- **Per-Trade Amount ($)**: Fixed dollar amount per position. If set to `0`, the system uses a percentage of your current capital.
- **Trade Size %**: The percentage of current capital used for each trade (enabled when Per-Trade Amount is 0).

---

## 📉 Interpreting Results

### Stats Grid
- **Gross Profit/Loss**: Total money made from winning trades vs. lost from losing trades.
- **Long/Short Performance**: Accuracy ratios (e.g., `3 W / 5 T` means 3 Wins out of 5 Total trades in that direction).
- **Max Drawdown**: The largest peak-to-trough decline in your capital.

### Chart Markers
- **▲ BUY / ▼ SELL**: Entry points.
- **🟢 PROFIT**: Position closed with a gain.
- **🔴 LOSS**: Position closed with a loss.

### Trade Log
The log shows a detailed row-by-row breakdown of every trade, including the **Consensus Votes** (e.g., `4/6`) that triggered the entry.
