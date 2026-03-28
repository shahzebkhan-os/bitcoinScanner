# 🔬 Backtesting Engine Guide

The Bitcoin Scanner Backtesting engine allows you to simulate your trading strategy on up to 50,000 historical candles. It uses a realistic **Position State Machine** to replicate live trading conditions and provides comprehensive analytics including an **equity curve** and **CSV export**.

## ✨ New Features

- **📈 Equity Curve Visualization**: See your capital growth over time with an interactive area chart
- **📥 CSV Export**: Download your backtest results for further analysis in Excel/Python
- **🎨 Improved UI/UX**: Enhanced loading states, empty states, and better layout that prevents chart overlap
- **🐛 Bug Fixes**: Fixed trade log overlapping chart, division-by-zero in volume filter
- **🧪 Comprehensive Tests**: Full test coverage for backtester engine (100+ test cases)

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

### 📈 Equity Curve
The equity curve shows your capital growth over time as a smooth area chart:
- **Green line**: Your account balance after each closed trade
- **Start → End**: Displays initial capital, final capital, and total return percentage
- **Visual insights**: Identify periods of consistent growth vs. drawdowns
- **Use cases**: Compare different parameter sets by their equity curve shape

### Chart Markers
- **▲ BUY / ▼ SELL**: Entry points.
- **🟢 PROFIT**: Position closed with a gain.
- **🔴 LOSS**: Position closed with a loss.

### Trade Log
The log shows a detailed row-by-row breakdown of every trade, including the **Consensus Votes** (e.g., `4/6`) that triggered the entry.

**Export Options:**
- Click **📥 Export CSV** to download the full trade log
- Open in Excel, Google Sheets, or Python for further analysis
- CSV includes all columns: Timestamp, Direction, Entry, Exit, P&L, Result, Votes

---

## 💡 Best Practices

### Finding Optimal Parameters

1. **Start with defaults**: Run a backtest with default settings on 5k candles to establish a baseline
2. **Test one variable at a time**: Change only one parameter per run to understand its impact
3. **Compare equity curves**: Parameters with smoother, steadier equity curves are more robust
4. **Consider win rate vs. risk/reward**: A 40% win rate with 2:1 R:R outperforms 60% with 1:1
5. **Test across market conditions**: Run backtests on different time periods (bull, bear, sideways)
6. **Use filters strategically**: Filters reduce trade frequency but can improve win rate

### Parameter Tuning Guidelines

| Parameter | Low Value | High Value | Effect |
|-----------|-----------|------------|---------|
| Min Votes | 1-2 | 5-6 | More trades vs. Higher quality |
| Min Exit Votes | 1-2 | 4-5 | Quick exits vs. Let winners run |
| RSI Oversold | 20-25 | 35-40 | Fewer signals vs. More signals |
| RSI Overbought | 60-65 | 75-80 | More signals vs. Fewer signals |
| Volume Multiplier | 1.0-1.2 | 2.0-3.0 | More trades vs. High conviction only |

### Common Pitfalls to Avoid

❌ **Over-optimization**: Don't tune parameters to perfectly fit historical data (curve fitting)
❌ **Cherry-picking**: Test on multiple time periods, not just bull runs
❌ **Ignoring drawdown**: High returns with 50% drawdown are unsustainable
❌ **Too few trades**: < 30 trades = statistically insignificant sample size
❌ **Ignoring market regime**: A strategy that works in trends fails in ranges

✅ **Best approach**: Find parameters that work consistently across different periods and market conditions

---

## 🔍 Advanced: Parameter Comparison Workflow

### Manual Comparison Method

1. Run backtest with Config A → Note final capital, win rate, max DD
2. Export CSV → Save as `backtest_configA.csv`
3. Run backtest with Config B → Note stats
4. Export CSV → Save as `backtest_configB.csv`
5. Compare equity curves visually
6. Compare stats side-by-side in a spreadsheet

### Key Metrics to Compare

- **Total Return %**: (Final - Initial) / Initial × 100
- **Sharpe-like Ratio**: Total Return / Max Drawdown (higher is better)
- **Win Rate**: Should be consistent across configs (±5%)
- **Average Win vs. Average Loss**: Aim for > 1.5:1
- **Trade Frequency**: More trades = more data = more statistical confidence

---

## 🐛 Troubleshooting

### "No trades generated"
- **Cause**: Filters too strict or min_votes too high
- **Fix**: Lower min_votes to 3, disable filters, try 5k+ candles

### "Only LONG trades" or "Only SHORT trades"
- **Cause**: Strong trending data or improper exit logic
- **Check**: Try a different time period with more varied price action

### "Chart overlap with trade log"
- **Status**: ✅ Fixed in latest version
- **Details**: Trade log now has fixed max-height and scrolls independently

### "Browser slowdown with 50k candles"
- **Workaround**: Start with 5k candles, increase gradually
- **Tip**: Close other browser tabs to free memory

---

## 📚 Technical Details

### Backend Implementation
- **File**: `backend/scanner/backtester.py`
- **Method**: Vectorized Pandas operations for speed
- **Performance**: 10k candles processed in < 2 seconds
- **Tests**: 100+ test cases covering indicators, strategies, filters, edge cases

### Frontend Implementation
- **File**: `frontend/src/app/backtester/backtester.component.ts`
- **Charts**: TradingView lightweight-charts for candlesticks + equity curve
- **Export**: Client-side CSV generation (no server round-trip)
- **Layout**: CSS Flexbox with fixed chart heights and scrollable trade log

### API Endpoint
- **Route**: `POST http://localhost:8765/backtest`
- **Max candles**: 50,000
- **Response**: Includes candles[], signals[], stats{}, trades[], equityCurve[]

---

## 🚀 Future Enhancements (Roadmap)

The following features are planned for future releases:

- [ ] **Multi-parameter grid search**: Run 100+ backtests automatically and compare results
- [ ] **Walk-forward optimization**: Test on in-sample data, validate on out-of-sample
- [ ] **Monte Carlo simulation**: Randomize trade order to test robustness
- [ ] **Benchmark comparison**: Compare strategy vs. buy-and-hold
- [ ] **Risk metrics**: Sortino ratio, Calmar ratio, win/loss streaks
- [ ] **Trade pagination**: Handle 1000+ trades with infinite scroll
- [ ] **Custom strategy builder**: Create your own indicator combinations in the UI

---

## 📝 Changelog

### Version 2.1.0 (Latest)
- ✨ Added equity curve visualization
- ✨ Added CSV export functionality
- 🐛 Fixed trade log overlapping chart
- 🐛 Fixed division-by-zero in volume filter
- 🎨 Improved loading and empty states
- 🧪 Added 100+ backend tests
- 📚 Updated documentation with best practices

### Version 2.0.0
- ✨ Added strategy filters (Trend, Volume, HTF Bias)
- ✨ Added min exit votes control
- 🎨 Complete UI overhaul with dark theme
- 🐛 Fixed consensus logic (EMA/MACD state-based)

---

**For additional help, please refer to the main [README.md](README.md) or open an issue on GitHub.**

