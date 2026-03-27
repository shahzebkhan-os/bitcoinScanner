import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ScannerDataService } from './core/services/scanner-data.service';
import { WebsocketService } from './core/services/websocket.service';
import { IndicatorSnapshot } from './core/models/scanner.models';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  providers: [WebsocketService, ScannerDataService]
})
export class AppComponent {
  title = 'Bitcoin Scanner Dashboard';

  constructor(
    public scannerData: ScannerDataService,
    public wsService: WebsocketService
  ) {}

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
}
