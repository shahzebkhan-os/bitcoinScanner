import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ScannerDataService } from './core/services/scanner-data.service';
import { WebsocketService } from './core/services/websocket.service';
import { IndicatorSnapshot, ConsensusResult } from './core/models/scanner.models';
import { CandlestickChartComponent } from './candlestick-chart/candlestick-chart.component';
import { Subject, takeUntil } from 'rxjs';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, CandlestickChartComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  providers: [WebsocketService, ScannerDataService]
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Bitcoin Scanner Dashboard';

  // Price tracking for change calculation
  private previousPrice: number = 0;
  private sessionStartPrice: number = 0;
  priceChange: number = 0;
  priceChangePercent: number = 0;

  // Consensus tracking for timestamp
  lastConsensusChangeTime: Date | null = null;
  private destroy$ = new Subject<void>();

  constructor(
    public scannerData: ScannerDataService,
    public wsService: WebsocketService
  ) {}

  ngOnInit(): void {
    // Track price changes
    this.scannerData.latestIndicators$
      .pipe(takeUntil(this.destroy$))
      .subscribe(indicators => {
        if (indicators && indicators.currentPrice) {
          if (this.sessionStartPrice === 0) {
            this.sessionStartPrice = indicators.currentPrice;
          }
          if (this.previousPrice !== 0) {
            this.priceChange = indicators.currentPrice - this.previousPrice;
            this.priceChangePercent = (this.priceChange / this.previousPrice) * 100;
          }
          this.previousPrice = indicators.currentPrice;
        }
      });

    // Track consensus changes
    let previousConsensus: ConsensusResult | null = null;
    this.scannerData.consensus$
      .pipe(takeUntil(this.destroy$))
      .subscribe(consensus => {
        if (consensus && previousConsensus) {
          if (consensus.direction !== previousConsensus.direction) {
            this.lastConsensusChangeTime = new Date();
          }
        }
        previousConsensus = consensus;
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  // Trend indicator helper methods
  getEmaTrend(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return '—';
    return indicators.emaFast > indicators.emaSlow ? '↑' : indicators.emaFast < indicators.emaSlow ? '↓' : '—';
  }

  getEmaTrendClass(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'neutral';
    return indicators.emaFast > indicators.emaSlow ? 'bullish' : indicators.emaFast < indicators.emaSlow ? 'bearish' : 'neutral';
  }

  getMacdTrend(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return '—';
    return indicators.macdHistogram > 0 ? '↑' : indicators.macdHistogram < 0 ? '↓' : '—';
  }

  getMacdTrendClass(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'neutral';
    return indicators.macdHistogram > 0 ? 'bullish' : indicators.macdHistogram < 0 ? 'bearish' : 'neutral';
  }

  getRsiZone(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'NEUTRAL';
    if (indicators.rsi < 30) return 'OVERSOLD';
    if (indicators.rsi > 70) return 'OVERBOUGHT';
    return 'NEUTRAL';
  }

  getRsiZoneClass(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'neutral';
    if (indicators.rsi < 30) return 'bullish'; // Oversold is bullish opportunity
    if (indicators.rsi > 70) return 'bearish'; // Overbought is bearish signal
    return 'neutral';
  }

  getVwapTrend(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return '—';
    return indicators.closeVsVwap === 'above' ? '↑' : indicators.closeVsVwap === 'below' ? '↓' : '—';
  }

  getVwapTrendClass(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'neutral';
    return indicators.closeVsVwap === 'above' ? 'bullish' : indicators.closeVsVwap === 'below' ? 'bearish' : 'neutral';
  }

  getBollingerBandsStatus(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'INSIDE';
    return indicators.closeVsBb.toUpperCase().replace('_', ' ');
  }

  getBollingerBandsClass(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'neutral';
    if (indicators.closeVsBb === 'above_upper') return 'bearish'; // Above upper band = overbought
    if (indicators.closeVsBb === 'below_lower') return 'bullish'; // Below lower band = oversold
    return 'neutral';
  }

  getVolumeTrend(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return '—';
    return indicators.volumeRatio > 1.5 ? '↑' : indicators.volumeRatio < 0.8 ? '↓' : '—';
  }

  getVolumeTrendClass(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'neutral';
    return indicators.volumeRatio > 1.5 ? 'bullish' : indicators.volumeRatio < 0.8 ? 'bearish' : 'neutral';
  }

  // Phase 2: Overall trend summary — uses strategy votes + key indicators
  getOverallTrend(indicators: IndicatorSnapshot | null): string {
    if (!indicators) return 'NEUTRAL';

    let bullishScore = 0;
    let bearishScore = 0;

    // 1. Strategy votes (most important — they are 6 independent evaluators)
    const votes = this.scannerData.strategyVotes$.value;
    if (votes && votes.length > 0) {
      for (const vote of votes) {
        if (vote.direction === 'LONG') bullishScore += 2;
        else if (vote.direction === 'SHORT') bearishScore += 2;
      }
    }

    // 2. EMA trend (trend-following)
    if (indicators.emaFast > indicators.emaSlow) bullishScore++;
    else if (indicators.emaFast < indicators.emaSlow) bearishScore++;

    // 3. RSI zone (mean-reversion — contrarian)
    if (indicators.rsi < 30) bullishScore += 2; // Oversold = strong bullish opportunity
    else if (indicators.rsi < 40) bullishScore++;
    else if (indicators.rsi > 70) bearishScore += 2; // Overbought = strong bearish signal
    else if (indicators.rsi > 60) bearishScore++;

    // 4. Bollinger Band position (mean-reversion — contrarian)
    if (indicators.closeVsBb === 'below_lower') bullishScore += 2; // Oversold bounce
    else if (indicators.closeVsBb === 'above_upper') bearishScore += 2; // Overbought rejection

    // 5. MACD momentum
    if (indicators.macdHistogram > 0) bullishScore++;
    else if (indicators.macdHistogram < 0) bearishScore++;

    // 6. Price action (tick-to-tick)
    if (this.priceChange > 0) bullishScore++;
    else if (this.priceChange < 0) bearishScore++;

    if (bullishScore > bearishScore) return 'BULLISH';
    if (bearishScore > bullishScore) return 'BEARISH';
    return 'NEUTRAL';
  }

  getOverallTrendClass(indicators: IndicatorSnapshot | null): string {
    const trend = this.getOverallTrend(indicators);
    return trend.toLowerCase();
  }

  // Phase 3: Consensus strength indicator
  getConsensusStrengthPercent(consensus: ConsensusResult | null): number {
    if (!consensus) return 0;
    const activeVotes = consensus.longVotes + consensus.shortVotes;
    return (activeVotes / 6) * 100;
  }

  getConsensusStrengthClass(consensus: ConsensusResult | null): string {
    if (!consensus) return 'weak';
    const percent = this.getConsensusStrengthPercent(consensus);
    if (percent >= 66) return 'strong'; // 4+ votes
    if (percent >= 50) return 'moderate'; // 3 votes
    return 'weak';
  }

  // Format elapsed time since last consensus change
  getTimeSinceLastChange(): string {
    if (!this.lastConsensusChangeTime) return 'No changes yet';

    const now = new Date();
    const diff = now.getTime() - this.lastConsensusChangeTime.getTime();
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ${minutes % 60}m ago`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s ago`;
    return `${seconds}s ago`;
  }
}
