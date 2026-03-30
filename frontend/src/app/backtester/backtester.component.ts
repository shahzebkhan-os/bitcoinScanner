import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule, DecimalPipe, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { createChart, IChartApi, ISeriesApi, CandlestickData, SeriesMarker } from 'lightweight-charts';

interface BacktestParams {
  pair: string;
  interval: string;
  limit: number;
  minVotes: number;
  minExitVotes: number;
  rsiOversold: number;
  rsiOverbought: number;
  emaFast: number;
  emaSlow: number;
  initialCapital: number;
  tradeAmount: number;       // Fixed $ per trade (0 = use % of capital)
  tradeSizePct: number;      // % of capital if tradeAmount is 0
  // Filters
  useTrendFilter: boolean;
  useVolumeFilter: boolean;
  volMultiplier: number;
  useHtfBias: boolean;
  htfEmaPeriod: number;
  // Exits
  useTrailingStop: boolean;
  trailingStopAtr: number;
  useFixedRiskReward: boolean;
  fixedStopLossPct: number;
  fixedTakeProfitPct: number;
  enabledStrategies: string[];
  mlLongThreshold: number;
  mlShortThreshold: number;
}

interface BacktestStats {
  totalTrades: number;
  wins: number;
  losses: number;
  openTrades: number;
  longWins: number;
  longTotal: number;
  shortWins: number;
  shortTotal: number;
  winRate: number;
  totalPnl: number;
  totalProfit: number;
  totalLoss: number;
  maxDrawdown: number;
  finalCapital: number;
  initialCapital: number;
  equityCurve?: Array<{ timestamp: string; capital: number }>;
  // Advanced risk metrics
  sortinoRatio?: number;
  calmarRatio?: number;
  maxWinStreak?: number;
  maxLossStreak?: number;
  avgWin?: number;
  avgLoss?: number;
  profitFactor?: number;
  // Buy-and-hold benchmark
  buyHoldReturn?: number;
  buyHoldFinal?: number;
  vsHoldPct?: number;
  strategyPerformance?: Array<{
    strategies: string;
    trades: number;
    wins: number;
    winRate: number;
    pnl: number;
  }>;
}

interface TradeRow {
  timestamp: string;
  direction: string;
  entry: number;
  exit: number;
  exitType: string;
  pnl: number;
  result: string;
  votes: string;
  strategies?: string;
}

@Component({
  selector: 'app-backtester',
  standalone: true,
  imports: [CommonModule, FormsModule, DecimalPipe, DatePipe],
  templateUrl: './backtester.component.html',
  styleUrl: './backtester.component.scss'
})
export class BacktesterComponent implements OnInit, OnDestroy {
  @ViewChild('btChartContainer', { static: true }) chartContainer!: ElementRef;
  @ViewChild('equityChartContainer', { static: false }) equityChartContainer?: ElementRef;

  private chart!: IChartApi;
  private candleSeries!: ISeriesApi<'Candlestick'>;
  private equityChart?: IChartApi;
  private equitySeries?: ISeriesApi<'Area'>;

  readonly API_URL = 'http://localhost:8765';

  params: BacktestParams = {
    pair: 'BTCUSDT',
    interval: '1m',
    limit: 1000,
    minVotes: 3,
    minExitVotes: 2,
    rsiOversold: 30,
    rsiOverbought: 70,
    emaFast: 9,
    emaSlow: 21,
    initialCapital: 10000,
    tradeAmount: 0,       // 0 = use % of capital
    tradeSizePct: 10,     // 10% of capital per trade
    useTrendFilter: false,
    useVolumeFilter: false,
    volMultiplier: 1.2,
    useHtfBias: false,
    htfEmaPeriod: 100,
    useTrailingStop: false,
    trailingStopAtr: 2.0,
    useFixedRiskReward: false,
    fixedStopLossPct: 1.0,      // 1%
    fixedTakeProfitPct: 2.0,    // 2%
    enabledStrategies: [
      'EMAcrossoverStrategy',
      'RSIBollingerStrategy',
      'VWAPBounceStrategy',
      'RangeTradingStrategy',
      'BreakoutStrategy',
      'MACDMomentumStrategy',
      'NeuralNetworkStrategy',
    ],
    mlLongThreshold: 0.60,
    mlShortThreshold: 0.40,
  };

  intervalOptions = ['1m', '3m', '5m', '15m'];
  limitOptions    = [1000, 5000, 10000, 20000, 50000];

  stats: BacktestStats | null = null;
  trades: TradeRow[] = [];
  allTrades: TradeRow[] = [];  // Store all trades
  currentPage = 1;
  tradesPerPage = 100;
  totalPages = 1;
  isLoading = false;
  errorMessage = '';
  selectionHint = '';

  private candleTimes: number[] = [];
  readonly availableStrategies = [
    { key: 'EMAcrossoverStrategy', label: 'EMA Crossover' },
    { key: 'RSIBollingerStrategy', label: 'RSI + Bollinger' },
    { key: 'VWAPBounceStrategy', label: 'VWAP Bounce' },
    { key: 'RangeTradingStrategy', label: 'Range Trading' },
    { key: 'BreakoutStrategy', label: 'Breakout' },
    { key: 'MACDMomentumStrategy', label: 'MACD Momentum' },
    { key: 'NeuralNetworkStrategy', label: 'Neural Network (ML)' },
  ];

  ngOnInit(): void {
    this.chart = createChart(this.chartContainer.nativeElement, {
      layout:     { background: { color: '#0d0f17' }, textColor: '#9498b0' },
      grid:       { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
      crosshair:  { mode: 1 },
      rightPriceScale: { borderColor: '#1e2130' },
      timeScale:  { borderColor: '#1e2130', timeVisible: true },
      width:  this.chartContainer.nativeElement.clientWidth,
      height: 420,
    });
    this.candleSeries = this.chart.addCandlestickSeries({
      upColor: '#00d4a3', downColor: '#f04b5c',
      borderUpColor: '#00d4a3', borderDownColor: '#f04b5c',
      wickUpColor: '#00d4a3',   wickDownColor: '#f04b5c',
    });
    // Auto-resize
    const ro = new ResizeObserver(() => {
      this.chart.applyOptions({ width: this.chartContainer.nativeElement.clientWidth });
    });
    ro.observe(this.chartContainer.nativeElement);
    // Note: Don't auto-run on init - let user configure first and click "Run Backtest"
  }

  ngOnDestroy(): void {
    this.chart?.remove();
    this.equityChart?.remove();
  }

  async runBacktest(): Promise<void> {
    this.isLoading = true;
    this.errorMessage = '';
    this.stats = null;
    this.trades = [];

    try {
      const body = {
        pair:           this.params.pair,
        interval:       this.params.interval,
        limit:          this.params.limit,
        minVotes:       this.params.minVotes,
        minExitVotes:   this.params.minExitVotes,
        rsiOversold:    this.params.rsiOversold,
        rsiOverbought:  this.params.rsiOverbought,
        emaFast:        this.params.emaFast,
        emaSlow:        this.params.emaSlow,
        initialCapital: this.params.initialCapital,
        tradeAmount:    this.params.tradeAmount,
        tradeSizePct:   this.params.tradeSizePct / 100,
        useTrendFilter:  this.params.useTrendFilter,
        useVolumeFilter: this.params.useVolumeFilter,
        volMultiplier:   this.params.volMultiplier,
        useHtfBias:      this.params.useHtfBias,
        htfEmaPeriod:    this.params.htfEmaPeriod,
        useTrailingStop:    this.params.useTrailingStop,
        trailingStopAtr:    this.params.trailingStopAtr,
        useFixedRiskReward: this.params.useFixedRiskReward,
        fixedStopLossPct:   this.params.fixedStopLossPct,
        fixedTakeProfitPct: this.params.fixedTakeProfitPct,
        enabledStrategies:  this.params.enabledStrategies,
        mlLongThreshold:    this.params.mlLongThreshold,
        mlShortThreshold:   this.params.mlShortThreshold,
      };

      const resp = await fetch(`${this.API_URL}/backtest`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.error) throw new Error(data.error);

      // Render candles
      const chartData: CandlestickData[] = (data.candles || []).map((c: any) => ({
        time: Math.floor(c.time / 1000) as any,
        open: c.open, high: c.high, low: c.low, close: c.close,
      }));
      this.candleSeries.setData(chartData);
      this.chart.timeScale().fitContent();
      this.candleTimes = chartData.map(c => c.time as number);

      // Render markers (entry + exit)
      this.renderMarkers(data.signals || [], chartData);

      // Update stats & trades
      this.stats  = data.stats  || null;
      this.allTrades = data.trades || [];
      this.totalPages = Math.ceil(this.allTrades.length / this.tradesPerPage);
      this.currentPage = 1;
      this.updateDisplayedTrades();

      // Render equity curve if data available
      this.renderEquityCurve(data.stats?.equityCurve);

    } catch (err: any) {
      this.errorMessage = err?.message || 'Backtest failed';
    } finally {
      this.isLoading = false;
    }
  }

  private renderMarkers(signals: any[], chartData: CandlestickData[]): void {
    if (!signals.length || !chartData.length) return;
    const first = chartData[0].time as number;
    const last  = chartData[chartData.length - 1].time as number;
    const times = chartData.map(c => c.time as number);

    const snapToCandle = (sec: number): number => {
      const clamped = Math.min(Math.max(sec, first), last);
      let lo = 0, hi = times.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (times[mid] < clamped) lo = mid + 1; else hi = mid;
      }
      if (lo > 0) {
        return Math.abs(times[lo - 1] - clamped) <= Math.abs(times[lo] - clamped)
          ? times[lo - 1] : times[lo];
      }
      return times[lo];
    };

    const markers: SeriesMarker<any>[] = [];
    for (const s of signals) {
      if (!s.timestamp) continue;
      const entryMs = new Date(s.timestamp).getTime();
      if (isNaN(entryMs)) continue;
      const entryTime = snapToCandle(Math.floor(entryMs / 1000));
      const isLong = s.direction === 'LONG';

      markers.push({
        time: entryTime as any,
        position: (isLong ? 'belowBar' : 'aboveBar') as any,
        color: isLong ? '#00d4a3' : '#f04b5c',
        shape: (isLong ? 'arrowUp' : 'arrowDown') as any,
        text: isLong ? '▲ BUY' : '▼ SELL',
        size: 2,
      });

      if (s.exitTimestamp) {
        const exitMs  = new Date(s.exitTimestamp).getTime();
        const exitSec = Math.floor(exitMs / 1000);
        if (!isNaN(exitMs) && exitSec >= first && exitSec <= last) {
          const exitTime = snapToCandle(exitSec);
          // Color exit by P&L direction: green = profit, red = loss
          const isProfitable = isLong
            ? (s.exitPrice > s.entry)
            : (s.exitPrice < s.entry);
          markers.push({
            time: exitTime as any,
            position: (isLong ? 'aboveBar' : 'belowBar') as any,
            color: isProfitable ? '#00d4a3' : '#f04b5c',
            shape: 'circle' as any,
            text: isProfitable ? 'PROFIT' : 'LOSS',
            size: 1,
          });
        }
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    this.candleSeries.setMarkers(markers);
  }

  toggleStrategy(name: string, enabled: boolean): void {
    if (enabled) {
      if (!this.params.enabledStrategies.includes(name)) {
        this.params.enabledStrategies = [...this.params.enabledStrategies, name];
        this.selectionHint = '';
      }
      return;
    }
    if (this.params.enabledStrategies.length <= 1) {
      this.selectionHint = 'At least one strategy must remain enabled.';
      return;
    }
    this.params.enabledStrategies = this.params.enabledStrategies.filter(s => s !== name);
    this.selectionHint = '';
    if (this.params.minVotes > this.params.enabledStrategies.length) {
      this.params.minVotes = this.params.enabledStrategies.length;
    }
    if (this.params.minExitVotes > this.params.enabledStrategies.length) {
      this.params.minExitVotes = this.params.enabledStrategies.length;
    }
  }

  getPnlClass(val: number): string {
    return val > 0 ? 'positive' : val < 0 ? 'negative' : 'neutral';
  }

  getMlSignalCount(): number {
    return this.allTrades.filter((t: TradeRow) =>
      ((t.strategies || '') as string)
        .split(';')
        .map((s: string) => s.trim())
        .includes('NeuralNetworkStrategy')
    ).length;
  }

  getMlSignalPercent(): number {
    if (!this.allTrades.length) return 0;
    return (this.getMlSignalCount() / this.allTrades.length) * 100;
  }

  updateDisplayedTrades(): void {
    const start = (this.currentPage - 1) * this.tradesPerPage;
    const end = start + this.tradesPerPage;
    this.trades = this.allTrades.slice(start, end);
  }

  nextPage(): void {
    if (this.currentPage < this.totalPages) {
      this.currentPage++;
      this.updateDisplayedTrades();
    }
  }

  prevPage(): void {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.updateDisplayedTrades();
    }
  }

  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages) {
      this.currentPage = page;
      this.updateDisplayedTrades();
    }
  }

  get pageNumbers(): number[] {
    const pages: number[] = [];
    const maxPagesToShow = 5;
    let start = Math.max(1, this.currentPage - Math.floor(maxPagesToShow / 2));
    let end = Math.min(this.totalPages, start + maxPagesToShow - 1);

    if (end - start + 1 < maxPagesToShow) {
      start = Math.max(1, end - maxPagesToShow + 1);
    }

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  }

  exportToCSV(): void {
    if (!this.allTrades || this.allTrades.length === 0) {
      alert('No trades to export');
      return;
    }

    // Create CSV header
    const headers = ['Timestamp', 'Direction', 'Entry Price', 'Exit Price', 'Exit Type', 'P&L', 'Result', 'Votes'];

    // Create CSV rows - export ALL trades, not just current page
    const rows = this.allTrades.map(trade => [
      trade.timestamp,
      trade.direction,
      trade.entry.toString(),
      trade.exit.toString(),
      trade.exitType,
      trade.pnl.toString(),
      trade.result,
      trade.votes
    ]);

    // Combine headers and rows
    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.join(','))
    ].join('\n');

    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    link.setAttribute('href', url);
    link.setAttribute('download', `backtest_results_${new Date().getTime()}.csv`);
    link.style.visibility = 'hidden';

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  private renderEquityCurve(equityCurve?: Array<{ timestamp: string; capital: number }>): void {
    if (!equityCurve || equityCurve.length === 0 || !this.equityChartContainer) {
      return;
    }

    // Initialize equity chart if not already created
    if (!this.equityChart) {
      this.equityChart = createChart(this.equityChartContainer.nativeElement, {
        layout:     { background: { color: '#0d0f17' }, textColor: '#9498b0' },
        grid:       { vertLines: { color: '#1a1d2e' }, horzLines: { color: '#1a1d2e' } },
        crosshair:  { mode: 1 },
        rightPriceScale: { borderColor: '#1e2130' },
        timeScale:  { borderColor: '#1e2130', timeVisible: true },
        width:  this.equityChartContainer.nativeElement.clientWidth,
        height: 200,
      });
      this.equitySeries = this.equityChart.addAreaSeries({
        topColor: 'rgba(0, 212, 163, 0.56)',
        bottomColor: 'rgba(0, 212, 163, 0.04)',
        lineColor: '#00d4a3',
        lineWidth: 2,
      });

      // Auto-resize
      const ro = new ResizeObserver(() => {
        this.equityChart?.applyOptions({ width: this.equityChartContainer!.nativeElement.clientWidth });
      });
      ro.observe(this.equityChartContainer.nativeElement);
    }

    // Convert equity curve data to chart format
    const equityData = equityCurve.map(point => ({
      time: Math.floor(new Date(point.timestamp).getTime() / 1000) as any,
      value: point.capital,
    })).sort((a, b) => (a.time as number) - (b.time as number));

    this.equitySeries?.setData(equityData);
    this.equityChart?.timeScale().fitContent();
  }
}
