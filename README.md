# Bitcoin Scanner

A real-time BTC futures scalping signal scanner with live Angular dashboard.

![Bitcoin Scanner](https://img.shields.io/badge/BTC-Scanner-orange?style=for-the-badge&logo=bitcoin)
![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)
![Angular](https://img.shields.io/badge/Angular-17+-red?style=for-the-badge&logo=angular)

## Overview

Bitcoin Scanner is a production-grade trading signal scanner that analyzes Bitcoin futures on a 1-minute timeframe using 6 technical indicators and 6 scalping strategies. The system employs a consensus filter that fires alerts only when 3 or more strategies agree on the same direction (LONG/SHORT).

### Architecture

- **Backend (Python/FastAPI)**: Polls CoinDCX API every second, calculates indicators, runs strategies, and broadcasts data via WebSocket
- **Frontend (Angular 17+)**: Real-time dashboard displaying price, indicators, strategy votes, and signal feed
- **Communication**: WebSocket for real-time data streaming, REST API for configuration and history

## Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- Angular CLI 17+
- npm or yarn

## Installation

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Configure settings in `config.yaml`:
   - Set trading pair (default: B-BTC_USDT)
   - Adjust indicator parameters
   - Configure alert channels (terminal, desktop, Telegram)
   - Set minimum votes for consensus (default: 3/6)

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install Node dependencies:
```bash
npm install
```

## Running the Application

### Start the Backend

From the `backend` directory:
```bash
python main.py
```

The scanner will start on `http://localhost:8765` with WebSocket at `ws://localhost:8765/ws`

### Start the Frontend

From the `frontend` directory (in a separate terminal):
```bash
ng serve
```

The dashboard will open at `http://localhost:4200`

## Features

### Technical Indicators (6)

1. **EMA (Exponential Moving Average)**: Fast (9) and Slow (21)
2. **RSI (Relative Strength Index)**: 14-period with overbought/oversold levels
3. **MACD (Moving Average Convergence Divergence)**: 12/26/9 configuration
4. **Bollinger Bands**: 20-period with 2 standard deviations
5. **VWAP (Volume Weighted Average Price)**: Daily reset
6. **Volume Analysis**: Current vs 20-period average

### Trading Strategies (7)

1. **EMA Crossover**: Signals on EMA fast/slow crossovers
2. **RSI + Bollinger**: Combines oversold/overbought RSI with BB extremes
3. **VWAP Bounce**: Price crosses VWAP with elevated volume
4. **Range Trading**: Identifies sideways markets and trades boundaries
5. **Breakout**: Detects range breakouts with volume confirmation
6. **MACD Momentum**: MACD crossover combined with histogram and VWAP
7. **Neural Network (ML)**: Lightweight neural-score vote using EMA, MACD, VWAP, RSI, and volume features

### Consensus Filter

Signals fire only when the configured minimum vote threshold is reached by enabled strategies.  
You can now choose exactly which strategies participate in consensus (including the ML strategy) from the Backtester UI.

### Alert Channels

- **Terminal**: Color-coded alerts (green for LONG, red for SHORT)
- **Desktop Notifications**: System notifications with price and votes
- **Telegram**: Optional bot notifications (configure in config.yaml)
- **WebSocket**: Real-time dashboard updates
- **CSV Log**: All signals logged to `signals_log.csv`

## WebSocket Protocol

### Tick Message (Every Second)
```json
{
  "type": "tick",
  "timestamp": "2025-03-28T14:32:01.000Z",
  "price": 84250.50,
  "candles": [...],
  "indicators": {...},
  "strategies": [...],
  "consensus": {...}
}
```

### Signal Message (When Consensus Fires)
```json
{
  "type": "signal",
  "timestamp": "2025-03-28T14:32:01.000Z",
  "direction": "LONG",
  "price": 84250.50,
  "votes": "4/7",
  "strategies": [...],
  "strength": 0.74
}
```

## REST API Endpoints

- `GET /config`: Current configuration (sanitized)
- `GET /signals/history?limit=50`: Last N signals from CSV log
- `GET /health`: Server health and uptime

## Configuration (`config.yaml`)

```yaml
pair: "B-BTC_USDT"          # Trading pair
interval: "1m"               # Candle interval
candle_buffer_size: 200      # Rolling buffer size
poll_interval_seconds: 1     # API polling frequency
min_votes: 3                 # Consensus threshold
enabled_strategies:          # Select only these strategies for consensus
  - "EMAcrossoverStrategy"
  - "RSIBollingerStrategy"
  - "VWAPBounceStrategy"
  - "RangeTradingStrategy"
  - "BreakoutStrategy"
  - "MACDMomentumStrategy"
  - "NeuralNetworkStrategy"

alerts:
  terminal: true             # Console alerts
  desktop: true              # System notifications
  telegram: false            # Telegram bot
  websocket: true            # Dashboard updates

indicators:
  ema_fast: 9
  ema_slow: 21
  rsi_period: 14
  rsi_overbought: 70
  rsi_oversold: 30
  # ... (see config.yaml for full schema)
```

## Signal Log (`signals_log.csv`)

Each signal is logged with:
- Timestamp
- Direction (LONG/SHORT)
- Price
- Vote count (e.g., "4/7", depends on enabled strategies)
- Strategy names
- Average strength
- RSI, MACD histogram, Volume ratio
- EMA, Bollinger Bands, VWAP values

## Production Build

### Frontend Production Build
```bash
cd frontend
ng build --configuration production
```

The compiled application will be in `frontend/dist/`. Serve with a static file server or integrate with FastAPI's `StaticFiles`.

## Development

### Backend Structure
```
backend/
├── scanner/          # Core scanner logic
│   ├── fetcher.py    # API polling and candle buffer
│   ├── indicators.py # Technical indicators
│   ├── strategies.py # Trading strategies
│   ├── consensus.py  # Vote aggregation
│   └── alerts.py     # Alert dispatchers
├── api/              # Web API
│   ├── websocket_server.py  # WebSocket broadcaster
│   └── rest_routes.py       # REST endpoints
├── logger/           # Signal logging
└── main.py           # Entry point
```

### Frontend Structure
```
frontend/src/app/
├── core/
│   ├── services/     # WebSocket and data services
│   └── models/       # TypeScript interfaces
└── app.component.*   # Main dashboard component
```

## Disclaimer

⚠️ **This is a research and educational tool. It does not place trades automatically. Past signals do not guarantee future performance. Always conduct your own analysis and risk assessment before trading.**

## License

MIT

## Support

For issues and questions, please open an issue on GitHub.
