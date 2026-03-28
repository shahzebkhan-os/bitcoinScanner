import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { createChart, IChartApi, ISeriesApi, CandlestickData, SeriesMarker, LineStyle } from 'lightweight-charts';
import { Candle, ConsensusResult } from '../core/models/scanner.models';
import { ScannerDataService } from '../core/services/scanner-data.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-candlestick-chart',
  standalone: true,
  imports: [CommonModule],
  template: `<div #chartContainer class="chart-container"></div>`,
  styles: [`
    .chart-container {
      width: 100%;
      height: 400px;
      border-radius: 8px;
      overflow: hidden;
    }
  `]
})
export class CandlestickChartComponent implements OnInit, OnDestroy {
  private static readonly MAX_MARKERS = 50;
  private static readonly HORIZONTAL_WINDOW_CANDLES = 120;
  private static readonly DEFAULT_STOP_LOSS_PCT = 0.002;

  @ViewChild('chartContainer', { static: true }) chartContainer!: ElementRef;

  private chart!: IChartApi;
  private candlestickSeries!: ISeriesApi<'Candlestick'>;
  private entryLineSeries!: ISeriesApi<'Line'>;
  private stopLineSeries!: ISeriesApi<'Line'>;
  private targetLineSeries!: ISeriesApi<'Line'>;
  private subscriptions: Subscription[] = [];
  private resizeObserver!: ResizeObserver;
  private markers: SeriesMarker<any>[] = [];

  constructor(private scannerData: ScannerDataService) {}

  ngOnInit(): void {
    this.initChart();
    
    // Subscribe to candles
    let isInitialData = true;
    this.subscriptions.push(
      this.scannerData.candles$.subscribe(candles => {
        if (candles && candles.length > 0) {
          if (isInitialData) {
            const chartData: CandlestickData[] = candles.map(c => ({
              time: Math.floor(c.time / 1000) as any,
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
              time: Math.floor(latest.time / 1000) as any,
              open: latest.open,
              high: latest.high,
              low: latest.low,
              close: latest.close
            });
          }
        }
      })
    );

    // Subscribe to consensus for markers
    this.subscriptions.push(
      this.scannerData.consensus$.subscribe(consensus => {
        if (consensus && consensus.fired) {
          this.addMarker(consensus);
        }
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

    this.entryLineSeries = this.chart.addLineSeries({
      color: '#f7931a',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Entry',
    });

    this.stopLineSeries = this.chart.addLineSeries({
      color: '#f04b5c',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Stop',
    });

    this.targetLineSeries = this.chart.addLineSeries({
      color: '#00d4a3',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: 'Target',
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

  private addMarker(consensus: ConsensusResult): void {
    const color = consensus.direction === 'LONG' ? '#00d4a3' : '#f04b5c';
    const shape = consensus.direction === 'LONG' ? 'arrowUp' : 'arrowDown';
    const candles = this.scannerData.candles$.value;
    if (candles.length === 0) {
      return;
    }

    const latest = candles[candles.length - 1];
    const latestTime = latest.time / 1000;
    const entry = latest.close;
    const candleStop = consensus.direction === 'LONG' ? latest.low : latest.high;
    const pctStop = consensus.direction === 'LONG'
      ? entry * (1 - CandlestickChartComponent.DEFAULT_STOP_LOSS_PCT)
      : entry * (1 + CandlestickChartComponent.DEFAULT_STOP_LOSS_PCT);
    const stopLoss = consensus.direction === 'LONG'
      ? Math.min(candleStop, pctStop)
      : Math.max(candleStop, pctStop);
    const risk = Math.max(0.0001, Math.abs(entry - stopLoss));
    const targetRr = this.scannerData.riskRewardRatio$.value || 1.5;
    const target = consensus.direction === 'LONG' ? entry + (risk * targetRr) : entry - (risk * targetRr);

    const text = `${consensus.direction} E:${entry.toFixed(2)} SL:${stopLoss.toFixed(2)} TP:${target.toFixed(2)}`;
    this.markers.push({
      time: latestTime as any,
      position: consensus.direction === 'LONG' ? 'belowBar' : 'aboveBar',
      color,
      shape,
      text,
    });
    this.markers = this.markers.slice(-CandlestickChartComponent.MAX_MARKERS);
    this.candlestickSeries.setMarkers(this.markers);

    const horizontalWindow = candles
      .slice(-CandlestickChartComponent.HORIZONTAL_WINDOW_CANDLES)
      .map((c) => ({ time: Math.floor(c.time / 1000) as any }));
    this.entryLineSeries.setData(horizontalWindow.map((p) => ({ ...p, value: entry })));
    this.stopLineSeries.setData(horizontalWindow.map((p) => ({ ...p, value: stopLoss })));
    this.targetLineSeries.setData(horizontalWindow.map((p) => ({ ...p, value: target })));
  }
}
