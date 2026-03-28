import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { createChart, IChartApi, ISeriesApi, CandlestickData, SeriesMarker, LineStyle } from 'lightweight-charts';
import { Candle, ConsensusResult, TradeLevels } from '../core/models/scanner.models';
import { ScannerDataService } from '../core/services/scanner-data.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-candlestick-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="chart-wrapper">
      <div class="chart-legend">
        <span class="legend-item ema-fast">● EMA 9</span>
        <span class="legend-item ema-slow">● EMA 21</span>
        <span class="legend-item vwap">- - VWAP</span>
        <span class="legend-item bb">▪ BB Bands</span>
        <span class="legend-item long-signal">▲ BUY</span>
        <span class="legend-item short-signal">▼ SELL</span>
      </div>
      <div #chartContainer class="chart-container"></div>
    </div>
  `,
  styles: [`
    .chart-wrapper {
      width: 100%;
      display: flex;
      flex-direction: column;
    }
    .chart-legend {
      display: flex;
      gap: 16px;
      padding: 6px 12px;
      background: #13151c;
      border-bottom: 1px solid #1e2130;
      flex-wrap: wrap;
    }
    .legend-item {
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
    }
    .ema-fast  { color: #f7931a; }
    .ema-slow  { color: #7b7f96; }
    .vwap      { color: #4a9eff; }
    .bb        { color: #3a3d4a; }
    .long-signal  { color: #00d4a3; font-weight: bold; }
    .short-signal { color: #f04b5c; font-weight: bold; }
    .chart-container {
      width: 100%;
      height: 400px;
      border-radius: 0 0 8px 8px;
      overflow: hidden;
    }
  `]
})
export class CandlestickChartComponent implements OnInit, OnDestroy {
  private static readonly MAX_MARKERS = 50;
  private static readonly HORIZONTAL_WINDOW_CANDLES = 120;
  private static readonly DEFAULT_STOP_LOSS_PCT = 0.002;
  private static readonly EMA_FAST_PERIOD = 9;
  private static readonly EMA_SLOW_PERIOD = 21;
  private static readonly BB_PERIOD = 20;
  private static readonly BB_STD = 2;
  private static readonly MS_PER_DAY = 24 * 60 * 60 * 1000;

  @ViewChild('chartContainer', { static: true }) chartContainer!: ElementRef;

  private chart!: IChartApi;
  private candlestickSeries!: ISeriesApi<'Candlestick'>;
  private emaFastSeries!: ISeriesApi<'Line'>;
  private emaSlowSeries!: ISeriesApi<'Line'>;
  private vwapSeries!: ISeriesApi<'Line'>;
  private bbUpperSeries!: ISeriesApi<'Line'>;
  private bbMiddleSeries!: ISeriesApi<'Line'>;
  private bbLowerSeries!: ISeriesApi<'Line'>;
  private entryLineSeries!: ISeriesApi<'Line'>;
  private stopLineSeries!: ISeriesApi<'Line'>;
  private targetLineSeries!: ISeriesApi<'Line'>;
  private subscriptions: Subscription[] = [];
  private resizeObserver!: ResizeObserver;
  private markers: SeriesMarker<any>[] = [];
  private lastMarkerTime = 0;

  constructor(private scannerData: ScannerDataService) {}

  ngOnInit(): void {
    this.initChart();

    // Subscribe to candles — update OHLCV series and recompute indicator overlays
    let isInitialData = true;
    this.subscriptions.push(
      this.scannerData.candles$.subscribe(candles => {
        if (candles && candles.length > 0) {
          if (isInitialData) {
            const chartData: CandlestickData[] = candles.map(c => ({
              time: this.candleTimeInSeconds(c) as any,
              open: c.open,
              high: c.high,
              low: c.low,
              close: c.close
            }));
            this.candlestickSeries.setData(chartData);
            this.chart.timeScale().fitContent();
            isInitialData = false;
          } else {
            // Incremental update for the latest candle
            const latest = candles[candles.length - 1];
            this.candlestickSeries.update({
              time: this.candleTimeInSeconds(latest) as any,
              open: latest.open,
              high: latest.high,
              low: latest.low,
              close: latest.close
            });
          }
          // Recompute EMA, BB, VWAP overlays on every candle update
          this.updateIndicatorOverlays(candles);
        }
      })
    );

    // Subscribe to consensus for markers — deduplicate by candle time
    this.subscriptions.push(
      this.scannerData.consensus$.subscribe(consensus => {
        if (consensus && consensus.fired) {
          this.addMarker(consensus);
        }
      })
    );

    this.subscriptions.push(
      this.scannerData.signalOverlays$.subscribe(overlays => {
        if (!overlays || overlays.length === 0) return;
        if (!this.scannerData.historyReplayConsumed$.value) {
          this.replayHistoryMarkers(overlays);
          this.scannerData.historyReplayConsumed$.next(true);
        }
        this.renderOverlay(overlays[0]);
      })
    );
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach(s => s.unsubscribe());
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
    if (this.chart) {
      this.chart.remove();
    }
  }

  private initChart(): void {
    const chartOptions: any = {
      layout: {
        background: { color: '#13151c' },
        textColor: '#7b7f96',
      },
      grid: {
        vertLines: { color: '#1e2130' },
        horzLines: { color: '#1e2130' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: '#2a2d3a',
        autoScale: true,
      },
      timeScale: {
        borderColor: '#2a2d3a',
        timeVisible: true,
        secondsVisible: false,
        shiftVisibleRangeOnNewBar: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    };

    this.chart = createChart(this.chartContainer.nativeElement, chartOptions);
    this.candlestickSeries = this.chart.addCandlestickSeries({
      upColor: '#00d4a3',
      downColor: '#f04b5c',
      borderVisible: false,
      wickUpColor: '#00d4a3',
      wickDownColor: '#f04b5c',
    });

    // Bollinger Bands (rendered first so they sit behind price)
    this.bbUpperSeries = this.chart.addLineSeries({
      color: 'rgba(58, 61, 74, 0.8)',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: 'BB Upper',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.bbMiddleSeries = this.chart.addLineSeries({
      color: 'rgba(58, 61, 74, 0.5)',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: 'BB Mid',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    this.bbLowerSeries = this.chart.addLineSeries({
      color: 'rgba(58, 61, 74, 0.8)',
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: 'BB Lower',
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // VWAP
    this.vwapSeries = this.chart.addLineSeries({
      color: '#4a9eff',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'VWAP',
      lastValueVisible: true,
      priceLineVisible: false,
    });

    // EMA lines
    this.emaFastSeries = this.chart.addLineSeries({
      color: '#f7931a',
      lineWidth: 1,
      title: 'EMA 9',
      lastValueVisible: true,
      priceLineVisible: false,
    });
    this.emaSlowSeries = this.chart.addLineSeries({
      color: '#7b7f96',
      lineWidth: 1,
      title: 'EMA 21',
      lastValueVisible: true,
      priceLineVisible: false,
    });

    // Trade level overlays (entry / stop / target)
    this.entryLineSeries = this.chart.addLineSeries({
      color: '#f7931a',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Entry',
      lastValueVisible: false,
      priceLineVisible: false,
    });

    this.stopLineSeries = this.chart.addLineSeries({
      color: '#f04b5c',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Stop',
      lastValueVisible: false,
      priceLineVisible: false,
    });

    this.targetLineSeries = this.chart.addLineSeries({
      color: '#00d4a3',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Target',
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Use ResizeObserver for more robust resizing
    this.resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || !entries[0].contentRect) return;
      const { width, height } = entries[0].contentRect;
      this.chart.applyOptions({ width, height });
    });
    this.resizeObserver.observe(this.chartContainer.nativeElement);

    // Fallback for window resize
    window.addEventListener('resize', () => {
      this.chart.applyOptions({
        width: this.chartContainer.nativeElement.clientWidth,
      });
    });
  }

  /** Convert candle millisecond timestamp to seconds (as required by lightweight-charts). */
  private candleTimeInSeconds(candle: Candle): number {
    return Math.floor(candle.time / 1000);
  }

  /** Compute EMA, Bollinger Bands, and VWAP from candle data and update chart series. */
  private updateIndicatorOverlays(candles: Candle[]): void {
    const times = candles.map(c => this.candleTimeInSeconds(c) as any);
    const closes = candles.map(c => c.close);

    // EMA 9 and EMA 21
    const emaFastValues = this.computeEMA(closes, CandlestickChartComponent.EMA_FAST_PERIOD);
    const emaSlowValues = this.computeEMA(closes, CandlestickChartComponent.EMA_SLOW_PERIOD);

    this.emaFastSeries.setData(
      times
        .map((t: any, i: number) => ({ time: t, value: emaFastValues[i] }))
        .filter((p: any) => isFinite(p.value))
    );
    this.emaSlowSeries.setData(
      times
        .map((t: any, i: number) => ({ time: t, value: emaSlowValues[i] }))
        .filter((p: any) => isFinite(p.value))
    );

    // Bollinger Bands
    const bbValues = this.computeBB(
      closes,
      CandlestickChartComponent.BB_PERIOD,
      CandlestickChartComponent.BB_STD
    );
    this.bbUpperSeries.setData(
      times
        .map((t: any, i: number) => ({ time: t, value: bbValues[i].upper }))
        .filter((p: any) => isFinite(p.value))
    );
    this.bbMiddleSeries.setData(
      times
        .map((t: any, i: number) => ({ time: t, value: bbValues[i].middle }))
        .filter((p: any) => isFinite(p.value))
    );
    this.bbLowerSeries.setData(
      times
        .map((t: any, i: number) => ({ time: t, value: bbValues[i].lower }))
        .filter((p: any) => isFinite(p.value))
    );

    // VWAP (reset at UTC midnight)
    const vwapValues = this.computeVWAP(candles);
    this.vwapSeries.setData(
      times
        .map((t: any, i: number) => ({ time: t, value: vwapValues[i] }))
        .filter((p: any) => isFinite(p.value))
    );
  }

  /** Exponential Moving Average using EMA formula (consistent with most charting platforms). */
  private computeEMA(closes: number[], period: number): number[] {
    const k = 2 / (period + 1);
    const result: number[] = new Array(closes.length).fill(NaN);
    if (closes.length < period) return result;
    // Seed with SMA of first `period` closes
    let prev = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
    result[period - 1] = prev;
    for (let i = period; i < closes.length; i++) {
      prev = closes[i] * k + prev * (1 - k);
      result[i] = prev;
    }
    return result;
  }

  /** Bollinger Bands: returns upper, middle, lower for each index. */
  private computeBB(
    closes: number[],
    period: number,
    stdMultiplier: number
  ): { upper: number; middle: number; lower: number }[] {
    return closes.map((_, i) => {
      if (i < period - 1) return { upper: NaN, middle: NaN, lower: NaN };
      const slice = closes.slice(i - period + 1, i + 1);
      const mean = slice.reduce((a, b) => a + b, 0) / period;
      const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period;
      const std = Math.sqrt(variance);
      return {
        upper: mean + stdMultiplier * std,
        middle: mean,
        lower: mean - stdMultiplier * std,
      };
    });
  }

  /** VWAP: typical price × volume cumulative sum, reset at each UTC day boundary. */
  private computeVWAP(candles: Candle[]): number[] {
    let cumPV = 0;
    let cumVol = 0;
    let currentDay = -1;
    return candles.map(c => {
      const day = Math.floor(c.time / CandlestickChartComponent.MS_PER_DAY);
      if (day !== currentDay) {
        cumPV = 0;
        cumVol = 0;
        currentDay = day;
      }
      const tp = (c.high + c.low + c.close) / 3;
      cumPV += tp * c.volume;
      cumVol += c.volume;
      return cumVol === 0 ? c.close : cumPV / cumVol;
    });
  }

  private addMarker(consensus: ConsensusResult): void {
    const color = consensus.direction === 'LONG' ? '#00d4a3' : '#f04b5c';
    const shape = consensus.direction === 'LONG' ? 'arrowUp' : 'arrowDown';
    const candles = this.scannerData.candles$.value;
    if (candles.length === 0) {
      return;
    }

    const latest = candles[candles.length - 1];
    const latestTime = this.candleTimeInSeconds(latest);

    // Deduplicate: skip if we already placed a marker for this candle
    if (latestTime <= this.lastMarkerTime) {
      return;
    }

    const entry = latest.close;
    const candleStop = consensus.direction === 'LONG' ? latest.low : latest.high;
    const stopPct = this.scannerData.defaultStopLossPct$.value || CandlestickChartComponent.DEFAULT_STOP_LOSS_PCT;
    const pctStop = consensus.direction === 'LONG'
      ? entry * (1 - stopPct)
      : entry * (1 + stopPct);
    const stopLoss = consensus.direction === 'LONG'
      ? Math.min(candleStop, pctStop)
      : Math.max(candleStop, pctStop);
    const risk = Math.max(0.0001, Math.abs(entry - stopLoss));
    const targetRr = this.scannerData.riskRewardRatio$.value || 1.5;
    const target = consensus.direction === 'LONG' ? entry + (risk * targetRr) : entry - (risk * targetRr);

    const votes = Math.max(consensus.longVotes, consensus.shortVotes);
    const text = `${consensus.direction} ${votes}/6 | E:${entry.toFixed(2)} SL:${stopLoss.toFixed(2)} TP:${target.toFixed(2)}`;

    this.markers.push({
      time: latestTime as any,
      position: consensus.direction === 'LONG' ? 'belowBar' : 'aboveBar',
      color,
      shape,
      text,
    });
    this.markers = this.markers
      .slice(-CandlestickChartComponent.MAX_MARKERS)
      .sort((a, b) => (a.time as number) - (b.time as number));
    this.candlestickSeries.setMarkers(this.markers);
    this.lastMarkerTime = latestTime;

    this.renderOverlay({ interval: '1m', entry, stopLoss, target, targetRr: targetRr });
  }

  private renderOverlay(overlay: TradeLevels): void {
    const candles = this.scannerData.candles$.value;
    if (candles.length === 0) return;
    const horizontalWindow = candles
      .slice(-CandlestickChartComponent.HORIZONTAL_WINDOW_CANDLES)
      .map((c) => ({ time: this.candleTimeInSeconds(c) as any }));
    this.entryLineSeries.setData(horizontalWindow.map((p) => ({ ...p, value: overlay.entry })));
    this.stopLineSeries.setData(horizontalWindow.map((p) => ({ ...p, value: overlay.stopLoss })));
    this.targetLineSeries.setData(horizontalWindow.map((p) => ({ ...p, value: overlay.target })));
  }

  private replayHistoryMarkers(overlays: TradeLevels[]): void {
    if (overlays.length === 0) return;
    const candles = this.scannerData.candles$.value;
    if (candles.length === 0) return;

    const firstCandleTime = this.candleTimeInSeconds(candles[0]);
    const lastCandleTime = this.candleTimeInSeconds(candles[candles.length - 1]);

    const rawHistoryMarkers = overlays
      .filter((overlay) => !!overlay.timestamp)
      .map((overlay) => {
        const ts = typeof overlay.timestamp === 'string' ? overlay.timestamp : '';
        const parsedTime = new Date(ts).getTime();
        if (Number.isNaN(parsedTime)) {
          return null;
        }
        const markerTime = Math.floor(parsedTime / 1000);
        const clampedTime = Math.min(Math.max(markerTime, firstCandleTime), lastCandleTime);
        const isLong = (overlay.direction || 'LONG') === 'LONG';
        return {
          time: clampedTime as any,
          position: (isLong ? 'belowBar' : 'aboveBar') as 'belowBar' | 'aboveBar',
          color: isLong ? '#00d4a3' : '#f04b5c',
          shape: (isLong ? 'arrowUp' : 'arrowDown') as 'arrowUp' | 'arrowDown',
          text: `${isLong ? 'LONG' : 'SHORT'} E:${overlay.entry.toFixed(2)} SL:${overlay.stopLoss.toFixed(2)} TP:${overlay.target.toFixed(2)}`,
        };
      })
      .filter((marker) => marker !== null)
      .slice(0, CandlestickChartComponent.MAX_MARKERS);

    const historyMarkers = (rawHistoryMarkers as SeriesMarker<any>[])
      .sort((a, b) => (a.time as number) - (b.time as number));

    if (historyMarkers.length > 0) {
      this.markers = historyMarkers;
      this.candlestickSeries.setMarkers(this.markers);
    }
  }
}
