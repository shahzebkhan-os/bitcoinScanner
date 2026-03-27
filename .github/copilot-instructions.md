## Project overview

Build a **real-time BTC futures scalping signal scanner** with a live Angular dashboard. The system has two parts:

**Backend (Python):**
- Fetches 1-minute OHLCV candle data from the **CoinDCX public API** every second
- Calculates 6 technical indicators on a rolling 200-candle window
- Runs 6 scalping strategy evaluators in parallel, each voting LONG / SHORT / NEUTRAL
- Fires an alert only when **3 or more strategies agree** on the same direction (consensus filter)
- Outputs alerts to: **terminal (color-coded)**, **desktop notification**, optionally **Telegram**
- Broadcasts every tick (indicators + signals + candles) over a **WebSocket** served by FastAPI
- Logs every signal to a **CSV file** with full indicator snapshot
- Fully configurable via a **`config.yaml`** file — no hardcoded values anywhere

**Frontend (Angular 17+):**
- Single-page dashboard that connects to the Python WebSocket on `ws://localhost:8765`
- Live candlestick chart (last 100 candles) with EMA 9/21, Bollinger Bands, and VWAP overlaid
- Real-time indicator gauges: RSI dial, MACD histogram, volume bar
- Strategy vote panel showing all 6 strategies with their current LONG / SHORT / NEUTRAL status
- Signal alert feed — scrollable list of every fired signal with timestamp, direction, price, votes
- Connection status indicator and auto-reconnect on WebSocket drop

---

## Tech stack

**Backend:**
- **Language:** Python 3.10+
- **Web server:** `FastAPI` + `uvicorn` for REST + WebSocket
- **Data:** `aiohttp` for async candle polling, `pandas` for candle buffer + indicator math
- **Indicators:** `pandas-ta` library (preferred) or manual numpy implementations as fallback
- **Alerts:** `colorama` for terminal colors, `plyer` for desktop notifications, `python-telegram-bot` for Telegram
- **Config:** `PyYAML`
- **Scheduling:** `asyncio` for the 1-second polling loop

**Frontend:**
- **Framework:** Angular 17+ (standalone components, no NgModules)
- **Charting:** `lightweight-charts` by TradingView (npm package) for candlestick + overlay charts
- **Gauge / indicator charts:** `Chart.js` with `ng2-charts` wrapper
- **WebSocket client:** Angular built-in `WebSocket` API wrapped in an RxJS `Observable`
- **Styling:** Angular Material for layout + custom CSS variables for dark trading theme
- **State management:** RxJS `BehaviorSubject` streams — no NgRx needed for this scale
- **HTTP:** Angular `HttpClient` for REST calls to FastAPI config/history endpoints

---

## Project file structure

```
btc-scanner/
├── backend/
│   ├── main.py                    # Entry point — starts FastAPI + asyncio scanner loop
│   ├── config.yaml                # All user-configurable settings
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── fetcher.py             # CoinDCX API calls, candle buffer management
│   │   ├── indicators.py          # All indicator calculations
│   │   ├── strategies.py          # 6 strategy evaluators
│   │   ├── consensus.py           # Vote aggregation + consensus filter
│   │   └── alerts.py              # Terminal, desktop, Telegram alert dispatchers
│   ├── api/
│   │   ├── __init__.py
│   │   ├── websocket_server.py    # FastAPI WebSocket endpoint — broadcasts tick data
│   │   └── rest_routes.py         # REST endpoints: GET /config, GET /signals/history
│   ├── logger/
│   │   ├── __init__.py
│   │   └── signal_log.py          # Writes signals to signals_log.csv
│   └── requirements.txt
│
├── frontend/                      # Angular project root (ng new btc-dashboard)
│   ├── src/
│   │   ├── app/
│   │   │   ├── app.component.ts           # Root component — dashboard shell layout
│   │   │   ├── app.component.html
│   │   │   ├── app.component.scss
│   │   │   ├── core/
│   │   │   │   ├── services/
│   │   │   │   │   ├── websocket.service.ts       # WebSocket connection + RxJS stream
│   │   │   │   │   ├── scanner-data.service.ts    # Parses WS messages, exposes typed streams
│   │   │   │   │   └── config.service.ts          # Fetches config from FastAPI REST
│   │   │   │   └── models/
│   │   │   │       ├── candle.model.ts
│   │   │   │       ├── indicator-snapshot.model.ts
│   │   │   │       ├── signal-result.model.ts
│   │   │   │       └── consensus-result.model.ts
│   │   │   ├── components/
│   │   │   │   ├── price-chart/               # Candlestick + EMA/BB/VWAP chart
│   │   │   │   │   ├── price-chart.component.ts
│   │   │   │   │   ├── price-chart.component.html
│   │   │   │   │   └── price-chart.component.scss
│   │   │   │   ├── indicator-panel/           # RSI gauge, MACD histogram, Volume bar
│   │   │   │   │   ├── indicator-panel.component.ts
│   │   │   │   │   ├── indicator-panel.component.html
│   │   │   │   │   └── indicator-panel.component.scss
│   │   │   │   ├── strategy-votes/            # 6 strategy vote cards
│   │   │   │   │   ├── strategy-votes.component.ts
│   │   │   │   │   ├── strategy-votes.component.html
│   │   │   │   │   └── strategy-votes.component.scss
│   │   │   │   ├── signal-feed/               # Scrollable signal alert list
│   │   │   │   │   ├── signal-feed.component.ts
│   │   │   │   │   ├── signal-feed.component.html
│   │   │   │   │   └── signal-feed.component.scss
│   │   │   │   ├── status-bar/                # Connection status + scanner stats
│   │   │   │   │   ├── status-bar.component.ts
│   │   │   │   │   └── status-bar.component.html
│   │   │   │   └── stats-summary/             # Session stats: total signals, win rate
│   │   │   │       ├── stats-summary.component.ts
│   │   │   │       └── stats-summary.component.html
│   │   │   └── app.config.ts                  # provideHttpClient, provideRouter, etc.
│   │   ├── styles.scss                        # Global dark trading theme variables
│   │   └── environments/
│   │       ├── environment.ts
│   │       └── environment.prod.ts
│   ├── angular.json
│   ├── package.json
│   └── tsconfig.json
│
└── README.md
```

---

## `config.yaml` — full schema

```yaml
pair: "B-BTC_USDT"
interval: "1m"
candle_buffer_size: 200
poll_interval_seconds: 1

min_votes: 3

alerts:
  terminal: true
  desktop: true
  telegram: false
  websocket: true          # broadcast to Angular dashboard

websocket:
  host: "0.0.0.0"
  port: 8765               # Angular connects to ws://localhost:8765/ws

telegram:
  bot_token: ""
  chat_id: ""

indicators:
  ema_fast: 9
  ema_slow: 21
  rsi_period: 14
  rsi_overbought: 70
  rsi_oversold: 30
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  bb_period: 20
  bb_std: 2
  vwap_reset: "daily"

risk:
  max_leverage: 5
  risk_per_trade_pct: 1.0
```

---

## Backend module specifications

### `scanner/fetcher.py`

```python
"""
Responsibilities:
- Fetch candles from https://public.coindcx.com/market_data/candles
  with query params: pair, interval, limit=200
- Parse JSON response into a pandas DataFrame with columns:
  [time, open, high, low, close, volume]
  where 'time' is a UTC datetime index (parsed from millisecond timestamp)
- Maintain a rolling deque of candle DataFrames — on each poll,
  append the latest candle (if its timestamp is new) and drop oldest if > buffer_size
- Handle HTTP errors, timeouts, and connection resets with exponential backoff retry
  (3 retries, 1s / 2s / 4s delays)
- Return a pandas DataFrame ready for indicator calculation on each call

Key function signatures:
  async def fetch_candles(pair: str, interval: str, limit: int) -> pd.DataFrame
  class CandleBuffer:
      def update(self, new_candles: pd.DataFrame) -> bool  # returns True if new candle added
      def get(self) -> pd.DataFrame                         # returns current buffer as DataFrame
"""
```

### `scanner/indicators.py`

```python
"""
Responsibilities:
- Accept a pandas DataFrame (columns: open, high, low, close, volume, time index)
- Return an IndicatorSnapshot dataclass with all values calculated on the latest candle

Indicators to calculate:

1. EMA — ema_fast (9), ema_slow (21) via pandas .ewm(span=period, adjust=False).mean()
2. RSI — period 14, Wilder smoothing (consistent with TradingView)
3. MACD — macd_line, signal_line, histogram (12/26/9)
4. Bollinger Bands — middle, upper, lower, bandwidth (20/2)
5. VWAP — reset at UTC midnight, typical_price * volume cumsum approach
6. Volume — current_volume, avg_volume (20-candle), volume_ratio

@dataclass
class IndicatorSnapshot:
    ema_fast: float
    ema_slow: float
    ema_crossover: str       # "bullish", "bearish", "none"
    rsi: float
    macd_line: float
    macd_signal: float
    macd_histogram: float
    macd_cross: str          # "bullish", "bearish", "none"
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_bandwidth: float
    close_vs_bb: str         # "above_upper", "below_lower", "inside"
    vwap: float
    close_vs_vwap: str       # "above", "below"
    current_volume: float
    avg_volume: float
    volume_ratio: float
    current_price: float
    timestamp: datetime

    def to_dict(self) -> dict:
        # Serialize to JSON-safe dict for WebSocket broadcast
        # Convert datetime to ISO string
        # Round all floats to 4 decimal places
"""
```

### `scanner/strategies.py`

```python
"""
@dataclass
class SignalResult:
    strategy_name: str
    direction: str      # "LONG", "SHORT", "NEUTRAL"
    strength: float     # 0.0 to 1.0
    reason: str

Strategy 1 — EMAcrossoverStrategy:
  LONG  when ema_fast just crossed ABOVE ema_slow (within last 2 candles)
  SHORT when ema_fast just crossed BELOW ema_slow
  NEUTRAL otherwise

Strategy 2 — RSIBollingerStrategy:
  LONG  when rsi < rsi_oversold AND close_vs_bb == "below_lower"
  SHORT when rsi > rsi_overbought AND close_vs_bb == "above_upper"
  NEUTRAL otherwise

Strategy 3 — VWAPBounceStrategy:
  LONG  when price crossed from below VWAP to above VWAP on current candle
        AND volume_ratio > 1.2
  SHORT when price crossed from above VWAP to below VWAP on current candle
        AND volume_ratio > 1.2
  NEUTRAL otherwise

Strategy 4 — RangeTradingStrategy:
  Detect range over last 20 candles (range_size < 1.5% = sideways)
  LONG  when price within 0.1% of range_low AND rsi < 45
  SHORT when price within 0.1% of range_high AND rsi > 55
  NEUTRAL when trending (range_size > 1.5%)

Strategy 5 — BreakoutStrategy:
  LONG  when close > range_high * 1.002 AND volume_ratio > 1.5
  SHORT when close < range_low * 0.998  AND volume_ratio > 1.5
  NEUTRAL otherwise (complements Strategy 4)

Strategy 6 — MACDMomentumStrategy:
  LONG  when macd_cross == "bullish" AND macd_histogram > 0
        AND close_vs_vwap == "above"
  SHORT when macd_cross == "bearish" AND macd_histogram < 0
        AND close_vs_vwap == "below"
  NEUTRAL otherwise

def run_all_strategies(snapshot: IndicatorSnapshot, config: dict) -> list[SignalResult]:
    # Run all 6 and return list — no shared state, each is instantiated fresh
"""
```

### `scanner/consensus.py`

```python
"""
@dataclass
class ConsensusResult:
    direction: str
    long_votes: int
    short_votes: int
    neutral_votes: int
    avg_strength: float
    agreeing_strategies: list[str]
    fired: bool

    def to_dict(self) -> dict:
        # Serialize to JSON-safe dict for WebSocket broadcast
"""
```

### `api/websocket_server.py`

```python
"""
FastAPI WebSocket broadcaster. This is the bridge between Python scanner and Angular dashboard.

Implementation:

1. Create a FastAPI app instance shared with rest_routes.py

2. Maintain a ConnectionManager class:
   class ConnectionManager:
       active_connections: list[WebSocket] = []
       async def connect(self, ws: WebSocket)
       def disconnect(self, ws: WebSocket)
       async def broadcast(self, message: dict)
           # json.dumps the dict and send_text to all active connections
           # Skip disconnected clients silently

3. WebSocket endpoint:
   @app.websocket("/ws")
   async def websocket_endpoint(websocket: WebSocket):
       await manager.connect(websocket)
       try:
           while True:
               await websocket.receive_text()  # keep-alive — client sends pings
       except WebSocketDisconnect:
           manager.disconnect(websocket)

4. Broadcast function called from main scanner loop on every tick:
   async def broadcast_tick(
       candles: list[dict],          # last 100 candles as OHLCV dicts
       snapshot: IndicatorSnapshot,
       results: list[SignalResult],
       consensus: ConsensusResult
   ):
       payload = {
           "type": "tick",
           "timestamp": snapshot.timestamp.isoformat(),
           "price": snapshot.current_price,
           "candles": candles,            # array of {time, open, high, low, close, volume}
           "indicators": snapshot.to_dict(),
           "strategies": [r.__dict__ for r in results],
           "consensus": consensus.to_dict(),
           "signal_fired": consensus.fired
       }
       await manager.broadcast(payload)

5. On signal fire, also send a separate "signal" message type:
   payload = {
       "type": "signal",
       "timestamp": ...,
       "direction": consensus.direction,
       "price": snapshot.current_price,
       "votes": f"{max(consensus.long_votes, consensus.short_votes)}/6",
       "strategies": consensus.agreeing_strategies,
       "strength": consensus.avg_strength,
       "rsi": snapshot.rsi,
       "volume_ratio": snapshot.volume_ratio
   }

Note: broadcast both "tick" (every second) and "signal" (only when fired)
Angular dashboard subscribes to both message types and routes them separately.
"""
```

### `api/rest_routes.py`

```python
"""
FastAPI REST endpoints for Angular to fetch initial data and config.

GET /config
  Returns: current config.yaml contents as JSON (sanitize — omit telegram bot_token)

GET /signals/history?limit=50
  Reads signals_log.csv, returns last N rows as JSON array
  Each row: {timestamp, direction, price, votes, strategies, rsi, macd_histogram, volume_ratio}

GET /health
  Returns: {"status": "running", "uptime_seconds": N, "candles_buffered": N, "connected_clients": N}

CORS: Allow http://localhost:4200 (Angular dev server) and http://localhost in production
"""
```

### `main.py`

```python
"""
Entry point — runs FastAPI server and scanner loop concurrently via asyncio.

async def scanner_loop():
    buffer = CandleBuffer(config)
    while True:
        start = time.monotonic()
        try:
            candles = await fetch_candles(config)
            updated = buffer.update(candles)
            if updated and len(buffer.get()) >= 50:
                snapshot = calculate_indicators(buffer.get(), config)
                results  = run_all_strategies(snapshot, config)
                consensus = evaluate_consensus(results, config)

                # Always broadcast tick (Angular dashboard needs every second)
                await broadcast_tick(
                    candles=buffer.get_last_n_as_dicts(100),
                    snapshot=snapshot,
                    results=results,
                    consensus=consensus
                )

                if consensus.fired:
                    dispatch_alerts(consensus, snapshot, config)
                    log_signal(consensus, snapshot)
        except Exception as e:
            logging.error(f"Poll error: {e}")
        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0, config['poll_interval_seconds'] - elapsed))

async def startup():
    # Run FastAPI uvicorn server + scanner loop as concurrent asyncio tasks
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8765, log_level="warning"))
    await asyncio.gather(server.serve(), scanner_loop())

if __name__ == "__main__":
    asyncio.run(startup())
"""
```

---

## Backend `requirements.txt`

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
websockets>=12.0
aiohttp>=3.9.0
requests>=2.31.0
pandas>=2.0.0
pandas-ta>=0.3.14b
numpy>=1.24.0
PyYAML>=6.0
colorama>=0.4.6
plyer>=2.1.0
python-telegram-bot>=20.0
```

---

## Angular frontend specifications

### Global dark theme — `styles.scss`

```scss
/*
Define a dark trading terminal theme using CSS custom properties.
Apply to :root and body.

Color palette:
  --bg-primary:     #0d0e12   (deepest background — main page)
  --bg-surface:     #13151c   (card/panel background)
  --bg-elevated:    #1a1d27   (chart background, input fields)
  --border:         #2a2d3a   (subtle borders)
  --text-primary:   #e8eaf0   (main text)
  --text-secondary: #7b7f96   (labels, muted text)
  --long-color:     #00d4a3   (teal-green for LONG / bullish)
  --short-color:    #f04b5c   (red for SHORT / bearish)
  --neutral-color:  #7b7f96   (gray for NEUTRAL)
  --accent:         #f7931a   (Bitcoin orange — used for highlights)
  --chart-grid:     #1e2130   (chart grid lines)

Body: background --bg-primary, color --text-primary, font-family 'JetBrains Mono', monospace
All scrollbars: thin dark style (webkit scrollbar styling)
Remove default margins and paddings globally.
*/
```

### Dashboard layout — `app.component.html`

```html
<!--
Full-screen dark dashboard. No router-outlet needed — single page.
Layout using CSS Grid:

Desktop layout (>1400px):
  ┌─────────────────────────────────────────────────────┐
  │  status-bar (full width, 48px)                      │
  ├──────────────────────────────┬──────────────────────┤
  │  price-chart (70% width)     │  strategy-votes      │
  │  (candlestick + overlays)    │  (30% width)         │
  │                              │                      │
  ├──────────────┬───────────────┤                      │
  │ indicator-   │ stats-summary │                      │
  │ panel        │               │                      │
  ├──────────────┴───────────────┴──────────────────────┤
  │  signal-feed (full width, scrollable, 220px height) │
  └─────────────────────────────────────────────────────┘

Mobile layout (<768px): single column stack, same components.

All grid areas defined with grid-template-areas in app.component.scss.
Each panel is a mat-card with --bg-surface background and --border border.
-->
```

### `core/services/websocket.service.ts`

```typescript
/*
Injectable singleton service that manages the WebSocket connection.

Properties:
  private socket: WebSocket | null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 10
  private reconnectDelay = 2000  // ms, doubles on each failure

  // Public RxJS subjects
  public messages$ = new Subject<any>()           // raw parsed JSON messages
  public connectionStatus$ = new BehaviorSubject<'connecting' | 'connected' | 'disconnected'>('disconnected')

Methods:
  connect(url: string): void
    - Create new WebSocket(url)
    - onopen: set status 'connected', reset reconnectAttempts
    - onmessage: JSON.parse event.data, next() into messages$
    - onclose: set status 'disconnected', schedule reconnect with exponential backoff
    - onerror: log error, do not throw

  disconnect(): void
    - Close socket, clear reconnect timer

  private scheduleReconnect(): void
    - setTimeout(() => this.connect(url), this.reconnectDelay * 2^reconnectAttempts)
    - Cap reconnectAttempts at maxReconnectAttempts

ngOnDestroy: call disconnect()

Usage: inject this service, subscribe to messages$ and filter by message.type
*/
```

### `core/services/scanner-data.service.ts`

```typescript
/*
Injectable service that consumes WebSocketService.messages$ and
exposes typed, structured streams for components to consume.

Inject: WebSocketService

On init, subscribe to messages$ and route by message.type:
  "tick"   → update all BehaviorSubjects below
  "signal" → push to signalFeed$

Public BehaviorSubject streams (all initialized with null/empty):

  candles$: BehaviorSubject<Candle[]>
    - Updated on every tick message
    - Holds last 100 candles for chart rendering

  latestIndicators$: BehaviorSubject<IndicatorSnapshot | null>
    - Current indicator values from latest tick

  strategyVotes$: BehaviorSubject<SignalResult[]>
    - All 6 strategy results from latest tick

  consensus$: BehaviorSubject<ConsensusResult | null>
    - Current consensus result

  signalFeed$: BehaviorSubject<FiredSignal[]>
    - Grows over the session — new signals prepended (newest first)
    - Cap at 100 entries to avoid memory growth

  sessionStats$: BehaviorSubject<SessionStats>
    - Computed from signalFeed$: total, long count, short count, last signal time

Interface definitions to create in models/:
  Candle { time: number; open: number; high: number; low: number; close: number; volume: number }
  IndicatorSnapshot { emaFast, emaSlow, emaCrossover, rsi, macdLine, macdSignal, macdHistogram,
                      macdCross, bbUpper, bbMiddle, bbLower, bbBandwidth, closeVsBb, vwap,
                      closeVsVwap, currentVolume, avgVolume, volumeRatio, currentPrice, timestamp }
  SignalResult { strategyName, direction, strength, reason }
  ConsensusResult { direction, longVotes, shortVotes, neutralVotes, avgStrength,
                    agreeingStrategies, fired }
  FiredSignal { timestamp, direction, price, votes, strategies, strength, rsi, volumeRatio }
  SessionStats { total, longs, shorts, lastSignalTime }
*/
```

### `components/price-chart/price-chart.component.ts`

```typescript
/*
Candlestick chart with overlay indicators using TradingView lightweight-charts.

Template: single <div #chartContainer style="width:100%;height:420px"></div>

Inject: ScannerDataService, ElementRef

On ngAfterViewInit:
  1. Create chart with createChart(chartContainer, {
       layout: { background: { color: '#13151c' }, textColor: '#7b7f96' },
       grid: { vertLines: { color: '#1e2130' }, horzLines: { color: '#1e2130' } },
       crosshair: { mode: CrosshairMode.Normal },
       rightPriceScale: { borderColor: '#2a2d3a' },
       timeScale: { borderColor: '#2a2d3a', timeVisible: true, secondsVisible: false }
     })

  2. Add series:
     - candleSeries = chart.addCandlestickSeries({
         upColor: '#00d4a3', downColor: '#f04b5c',
         borderUpColor: '#00d4a3', borderDownColor: '#f04b5c',
         wickUpColor: '#00d4a3', wickDownColor: '#f04b5c'
       })
     - emaFastSeries = chart.addLineSeries({ color: '#f7931a', lineWidth: 1, title: 'EMA 9' })
     - emaSlowSeries = chart.addLineSeries({ color: '#7b7f96', lineWidth: 1, title: 'EMA 21' })
     - vwapSeries    = chart.addLineSeries({ color: '#4a9eff', lineWidth: 1, lineStyle: LineStyle.Dashed, title: 'VWAP' })
     - bbUpperSeries = chart.addLineSeries({ color: '#2a2d3a', lineWidth: 1, title: 'BB Upper' })
     - bbLowerSeries = chart.addLineSeries({ color: '#2a2d3a', lineWidth: 1, title: 'BB Lower' })

  3. Subscribe to scannerData.candles$ — on each emission:
     - Map Candle[] to lightweight-charts format: { time: c.time/1000, open, high, low, close }
     - Call candleSeries.setData(mapped)
     - Update EMA fast/slow lines from last N candle timestamps + emaFast/emaSlow values
       (Note: EMA data for the chart must be reconstructed from candle timestamps and
        each tick's emaFast/emaSlow value — store a rolling array of {time, value} pairs)

  4. Subscribe to scannerData.latestIndicators$ — on each emission:
     - Append latest VWAP point to vwapSeries
     - Append latest BB upper/lower points to bbSeries

  5. Subscribe to scannerData.consensus$ — when fired=true:
     - Add a marker on the candleSeries at current time:
       { time: ..., position: 'belowBar'/'aboveBar', color: longColor/shortColor,
         shape: 'arrowUp'/'arrowDown', text: 'LONG'/'SHORT' }

  6. Handle resize: use ResizeObserver on chartContainer, call chart.resize() on size change

  7. ngOnDestroy: chart.remove(), unsubscribe all subscriptions
*/
```

### `components/indicator-panel/indicator-panel.component.ts`

```typescript
/*
Panel showing RSI, MACD histogram, and Volume bar — updates every tick.

Template layout (horizontal flex row, 3 equal sections):

Section 1 — RSI Gauge (arc gauge using Chart.js doughnut):
  - Doughnut chart showing RSI as a needle gauge (0–100)
  - Color: green if RSI < 30 (oversold), red if RSI > 70 (overbought), gray otherwise
  - Display RSI value as large number in center of gauge
  - Labels: "Oversold" at left, "Overbought" at right

Section 2 — MACD Histogram (Chart.js bar chart):
  - Show last 30 histogram values as vertical bars
  - Bar color: --long-color if value > 0, --short-color if value < 0
  - Zero line visible
  - MACD cross indicator: show "BULLISH CROSS" or "BEARISH CROSS" badge when macd_cross != "none"

Section 3 — Volume Bar:
  - Current volume as a horizontal bar relative to avg_volume
  - Fill color: --long-color if volume_ratio > 1.5 (elevated), --neutral-color otherwise
  - Display: "1.8x avg" text below bar
  - Show "HIGH VOLUME" badge if volume_ratio > 2.0

Inject: ScannerDataService
Subscribe to latestIndicators$ — update all three charts on each emission.
Use ng2-charts (BaseChartDirective) for Chart.js integration.
All Chart.js canvases: transparent background, no legends, minimal labels.
*/
```

### `components/strategy-votes/strategy-votes.component.ts`

```typescript
/*
6 strategy vote cards displayed in a vertical list (right panel).

For each of the 6 strategies, render a card showing:
  - Strategy name (e.g. "EMA Crossover")
  - Direction badge: LONG (teal bg), SHORT (red bg), NEUTRAL (gray bg)
  - Strength bar: horizontal progress bar 0–100% width using strength * 100
  - Reason text: small muted text showing strategy.reason
  - Pulsing animation on the card border when direction != NEUTRAL

At the top of the panel, show consensus summary:
  - Large direction label: "LONG 4/6" or "SHORT 3/6" or "NEUTRAL"
  - Color matches direction
  - Pulsing glow effect when consensus.fired == true

Inject: ScannerDataService
Subscribe to strategyVotes$ and consensus$.

Animation: when a card's direction changes (NEUTRAL → LONG etc), animate the background
color transition with a 300ms CSS transition. Use Angular animations (@fadeIn, @slideIn)
for new signals appearing.

Template: *ngFor over strategyVotes$ | async
Use trackBy: trackByStrategy (by strategyName) to avoid unnecessary DOM re-renders.
*/
```

### `components/signal-feed/signal-feed.component.ts`

```typescript
/*
Scrollable list of fired signals — newest at top.

Each signal row displays:
  - Direction icon: triangle up (LONG) or triangle down (SHORT) colored accordingly
  - Timestamp: HH:MM:SS format
  - Direction text: "LONG" or "SHORT"
  - Price: "$84,250.00" formatted with Intl.NumberFormat
  - Vote count: "4/6"
  - Strategy badges: small pills for each agreeing strategy name
  - Signal strength: small text "(strength: 0.82)"

Visual behavior:
  - New signal rows slide in from the top with a 200ms animation
  - LONG rows have a subtle left border: 3px solid --long-color
  - SHORT rows have a subtle left border: 3px solid --short-color
  - Alternating row backgrounds for readability
  - Smooth scroll — do not auto-scroll if user has manually scrolled up

Inject: ScannerDataService
Subscribe to signalFeed$ | async.

If no signals yet: show centered empty state "Scanning... waiting for consensus signal"
with a pulsing dot animation.

Max rendered rows: 100 (use virtual scrolling via CdkVirtualScrollViewport from @angular/cdk
if list grows — import ScrollingModule from @angular/cdk/scrolling)
*/
```

### `components/status-bar/status-bar.component.ts`

```typescript
/*
Top bar showing scanner status. Full width, 48px height.

Left section:
  - BTC/USDT logo text in --accent (orange)
  - Current price: large monospace number, updated every tick
  - Price change indicator: colored arrow + percentage vs open

Center section:
  - Connection status dot: pulsing green when connected, red when disconnected
  - Status text: "Live — 127 candles buffered" or "Reconnecting..."
  - Last update timestamp: "Updated 0.3s ago" (computed from latest tick timestamp)

Right section:
  - Session stats: "12 signals · 8 LONG · 4 SHORT"
  - Session duration: "Running 01:24:07" (timer from component init)
  - Pair and interval display: "B-BTC_USDT · 1m"

Inject: WebSocketService (for connectionStatus$), ScannerDataService (for price + stats)

The "Updated Xs ago" counter: use setInterval(1000) to recompute elapsed seconds
since last tick timestamp. Resets to 0 on each new tick.
*/
```

### `components/stats-summary/stats-summary.component.ts`

```typescript
/*
Small stats panel below the indicator panel.

Display metric cards in a 2x2 grid:
  - Total signals fired (session)
  - Long signals count
  - Short signals count
  - Last signal time: "3m 24s ago"

Each card: dark background, small muted label, large number.

Also show a mini bar showing LONG vs SHORT ratio as a horizontal split bar:
  [====LONG 67%====|=SHORT 33%=]
  Teal fill for LONG portion, red for SHORT.

Inject: ScannerDataService
Subscribe to sessionStats$.
*/
```

### Angular `package.json` — key dependencies

```json
{
  "dependencies": {
    "@angular/animations": "^17.0.0",
    "@angular/cdk": "^17.0.0",
    "@angular/common": "^17.0.0",
    "@angular/compiler": "^17.0.0",
    "@angular/core": "^17.0.0",
    "@angular/forms": "^17.0.0",
    "@angular/material": "^17.0.0",
    "@angular/platform-browser": "^17.0.0",
    "@angular/platform-browser-dynamic": "^17.0.0",
    "@angular/router": "^17.0.0",
    "chart.js": "^4.4.0",
    "lightweight-charts": "^4.1.0",
    "ng2-charts": "^5.0.0",
    "rxjs": "~7.8.0",
    "zone.js": "~0.14.0"
  },
  "devDependencies": {
    "@angular-devkit/build-angular": "^17.0.0",
    "@angular/cli": "^17.0.0",
    "@types/node": "^18.0.0",
    "typescript": "~5.2.0"
  }
}
```

### `environments/environment.ts`

```typescript
export const environment = {
  production: false,
  wsUrl: 'ws://localhost:8765/ws',
  apiUrl: 'http://localhost:8765'
};
```

---

## WebSocket message protocol

Python backend sends two message types. Angular must handle both:

### Tick message (every second)

```json
{
  "type": "tick",
  "timestamp": "2025-03-28T14:32:01.000Z",
  "price": 84250.50,
  "candles": [
    { "time": 1711632600000, "open": 84100, "high": 84380, "low": 84050, "close": 84250, "volume": 12.4 }
  ],
  "indicators": {
    "ema_fast": 84180.2,
    "ema_slow": 83950.8,
    "ema_crossover": "bullish",
    "rsi": 58.3,
    "macd_line": 112.4,
    "macd_signal": 98.2,
    "macd_histogram": 14.2,
    "macd_cross": "none",
    "bb_upper": 85100.0,
    "bb_middle": 84000.0,
    "bb_lower": 82900.0,
    "bb_bandwidth": 0.026,
    "close_vs_bb": "inside",
    "vwap": 84050.3,
    "close_vs_vwap": "above",
    "current_volume": 18.7,
    "avg_volume": 11.2,
    "volume_ratio": 1.67,
    "current_price": 84250.50,
    "timestamp": "2025-03-28T14:32:01.000Z"
  },
  "strategies": [
    { "strategy_name": "EMAcrossoverStrategy", "direction": "LONG", "strength": 0.72, "reason": "EMA 9 crossed above EMA 21" },
    { "strategy_name": "RSIBollingerStrategy", "direction": "NEUTRAL", "strength": 0.0, "reason": "RSI at 58 — no extreme" }
  ],
  "consensus": {
    "direction": "LONG",
    "long_votes": 4,
    "short_votes": 0,
    "neutral_votes": 2,
    "avg_strength": 0.74,
    "agreeing_strategies": ["EMAcrossoverStrategy", "VWAPBounceStrategy", "BreakoutStrategy", "MACDMomentumStrategy"],
    "fired": true
  },
  "signal_fired": true
}
```

### Signal message (only when consensus fires)

```json
{
  "type": "signal",
  "timestamp": "2025-03-28T14:32:01.000Z",
  "direction": "LONG",
  "price": 84250.50,
  "votes": "4/6",
  "strategies": ["EMAcrossoverStrategy", "VWAPBounceStrategy", "BreakoutStrategy", "MACDMomentumStrategy"],
  "strength": 0.74,
  "rsi": 58.3,
  "volume_ratio": 1.67
}
```

---

## Error handling requirements

**Backend:**
- API rate limiting (429): back off 5 seconds, log event
- Network drops: exponential backoff retry, never crash
- Bad candle data: validate non-null OHLCV before adding to buffer
- Indicator NaN: mark that strategy NEUTRAL for that tick
- Alert failures: try/except around every alert — Telegram timeout must not kill loop
- WebSocket client disconnect: remove from ConnectionManager silently, never throw

**Frontend:**
- WebSocket disconnect: show red status dot, auto-reconnect with exponential backoff (max 10 attempts)
- Malformed JSON from server: catch JSON.parse errors, skip message, log to console
- Chart initialization failure: show error placeholder in chart container, retry on next tick
- Empty data state: show meaningful empty states in all components during warmup
- Memory growth: cap signalFeed$ at 100 entries, candle chart at 100 points

---

## Testing requirements

**Backend tests (`tests/`):**
- `test_indicators.py`: unit test each indicator against fixed synthetic DataFrame
- `test_strategies.py`: synthetic IndicatorSnapshots triggering LONG, SHORT, NEUTRAL per strategy
- `test_consensus.py`: vote counting edge cases (0–6 votes, ties)
- `test_fetcher.py`: mock HTTP with `unittest.mock`
- `test_websocket.py`: mock WebSocket connections, assert broadcast_tick sends correct JSON shape

**Frontend tests (`src/app/`):**
- `websocket.service.spec.ts`: mock WebSocket, test connect/disconnect/reconnect/message routing
- `scanner-data.service.spec.ts`: feed mock messages, assert BehaviorSubjects update correctly
- `strategy-votes.component.spec.ts`: render with mock data, assert correct badge colors
- `signal-feed.component.spec.ts`: assert new signal prepends correctly, empty state renders

---

## Running the full stack

Add these scripts to the README:

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py
# Scanner starts on http://localhost:8765 — WebSocket at ws://localhost:8765/ws

# Frontend (separate terminal)
cd frontend
npm install
ng serve
# Dashboard opens at http://localhost:4200
```

---

## README.md requirements

The README must include:
1. System overview with architecture diagram description (backend + WebSocket + Angular)
2. Prerequisites: Python 3.10+, Node 18+, Angular CLI 17+
3. Setup: clone → install backend → install frontend → run both → open browser
4. Screenshot placeholder section: `![Dashboard Screenshot](docs/screenshot.png)`
5. Description of all 6 strategies with signal conditions
6. WebSocket message protocol summary
7. How to enable Telegram alerts
8. What each column in `signals_log.csv` means
9. How to build Angular for production: `ng build --configuration production`
   and serve the `dist/` folder with a static server or serve via FastAPI's StaticFiles
10. Disclaimer: "This is a research and educational tool. It does not place trades automatically.
    Past signals do not guarantee future performance."

---

## Important implementation notes for Copilot

**Backend:**
- Use `asyncio.sleep()` never `time.sleep()` in main loop
- Candle deduplication: only append if timestamp is genuinely newer than last stored candle
- VWAP resets at UTC midnight — track current UTC date, reset cumulative sums on date change
- EMA crossover: detect the flip moment only (store previous ema_fast > ema_slow bool)
- MACD crossover: detect histogram sign flip only — do not signal on every negative histogram
- Signal cooldown: suppress same-direction signals for 60 seconds after firing
- broadcast_tick runs every second even when no new candle — Angular needs consistent ticks
- Run uvicorn with `loop="asyncio"` to share the event loop with the scanner

**Frontend:**
- Use `takeUntilDestroyed()` (Angular 16+) or `ngOnDestroy` + `Subject.complete()` to unsubscribe all observables — memory leaks from hot BehaviorSubject subscriptions will corrupt the chart over time
- lightweight-charts requires `time` in UNIX seconds (not milliseconds) — divide CoinDCX timestamps by 1000
- Chart.js canvases must be destroyed and recreated if the component is destroyed — call `chart.destroy()` in ngOnDestroy
- Use Angular's `OnPush` change detection strategy on all components — data arrives every second and default detection will hammer the DOM
- The price display should use `Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })` — never manually format currency strings
- Do not store candle history in the component — store it only in ScannerDataService and pass it down via the BehaviorSubject
- Use `@defer` blocks (Angular 17) for the chart components to lazy-load lightweight-charts only when the chart panel is in view

---

## Suggested future improvements (mention in README)

- Multi-pair scanning tab: add BTC, ETH, BNB tabs in Angular with separate WebSocket streams per pair
- Backtesting page: Angular form to select date range, calls a Python `/backtest` endpoint, renders historical signal overlay on chart
- Sound alerts in Angular: play audio via Web Audio API when a signal fires in the browser tab
- Alert configuration UI: Angular settings panel to adjust min_votes, indicator periods without editing config.yaml directly
- Signal accuracy tracker: after each signal, record price 5m/15m later, compute if direction was correct — show win rate in stats panel
- Export button: download `signals_log.csv` directly from Angular via the FastAPI `/signals/history` endpoint

---
