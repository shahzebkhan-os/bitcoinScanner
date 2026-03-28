import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { WebsocketService } from './websocket.service';
import {
  Candle,
  IndicatorSnapshot,
  SignalResult,
  ConsensusResult,
  IntervalConsensusMap,
  IntervalStrategies,
  FiredSignal,
  SessionStats,
  OverallTrend,
  TradeLevels
} from '../models/scanner.models';

@Injectable({
  providedIn: 'root'
})
export class ScannerDataService {
  private static readonly DEFAULT_WS_URL = 'ws://localhost:8765/ws';
  private static readonly DEFAULT_API_URL = 'http://localhost:8765';

  public candles$ = new BehaviorSubject<Candle[]>([]);
  public latestIndicators$ = new BehaviorSubject<IndicatorSnapshot | null>(null);
  public strategyVotes$ = new BehaviorSubject<SignalResult[]>([]);
  public consensus$ = new BehaviorSubject<ConsensusResult | null>(null);
  public signalFeed$ = new BehaviorSubject<FiredSignal[]>([]);
  public overallTrend$ = new BehaviorSubject<OverallTrend | null>(null);
  public riskRewardRatio$ = new BehaviorSubject<number>(1.5);
  public defaultStopLossPct$ = new BehaviorSubject<number>(0.002);
  public strategiesByInterval$ = new BehaviorSubject<IntervalStrategies>({});
  public consensusByInterval$ = new BehaviorSubject<IntervalConsensusMap>({});
  public signalOverlays$ = new BehaviorSubject<TradeLevels[]>([]);
  public historyReplayConsumed$ = new BehaviorSubject<boolean>(false);
  public sessionStats$ = new BehaviorSubject<SessionStats>({
    total: 0,
    longs: 0,
    shorts: 0,
    lastSignalTime: null
  });

  constructor(private wsService: WebsocketService) {
    // Subscribe to WebSocket messages
    this.wsService.messages$.subscribe(message => {
      this.handleMessage(message);
    });

    this.loadConfig();
    this.loadSignalHistory();

    // Connect to WebSocket
    this.wsService.connect(ScannerDataService.DEFAULT_WS_URL);
  }

  private handleMessage(message: any): void {
    if (message.type === 'tick') {
      // Update candles
      if (message.candles) {
        this.candles$.next(message.candles);
      }

      // Update indicators
      if (message.indicators) {
        this.latestIndicators$.next(message.indicators);
      }

      // Update strategy votes
      if (message.strategies) {
        this.strategyVotes$.next(message.strategies);
      }

      // Update consensus
      if (message.consensus) {
        this.consensus$.next(message.consensus);
      }

      if (message.overallTrend) {
        this.overallTrend$.next(message.overallTrend);
      }
      if (message.strategiesByInterval) {
        this.strategiesByInterval$.next(message.strategiesByInterval);
      }
      if (message.consensusByInterval) {
        this.consensusByInterval$.next(message.consensusByInterval);
      }

    } else if (message.type === 'signal') {
      // Add to signal feed
      const signal: FiredSignal = {
        timestamp: message.timestamp,
        direction: message.direction,
        price: message.price,
        votes: message.votes,
        strategies: message.strategies,
        strength: message.strength,
        rsi: message.rsi,
        volumeRatio: message.volumeRatio ?? 0
      };

      const currentSignals = this.signalFeed$.value;
      const newSignals = [signal, ...currentSignals].slice(0, 100); // Keep last 100
      this.signalFeed$.next(newSignals);
      if (this.isTradeLevels(message.tradeLevels)) {
        const overlays = [message.tradeLevels, ...this.signalOverlays$.value].slice(0, 100);
        this.signalOverlays$.next(overlays);
      }

      // Update session stats
      this.updateSessionStats(signal);
    }
  }

  private updateSessionStats(signal: FiredSignal): void {
    const stats = this.sessionStats$.value;
    const newStats: SessionStats = {
      total: stats.total + 1,
      longs: stats.longs + (signal.direction === 'LONG' ? 1 : 0),
      shorts: stats.shorts + (signal.direction === 'SHORT' ? 1 : 0),
      lastSignalTime: signal.timestamp
    };
    this.sessionStats$.next(newStats);
  }

  private async loadConfig(): Promise<void> {
    try {
      const response = await fetch(`${ScannerDataService.DEFAULT_API_URL}/config`);
      if (!response.ok) return;
      const cfg = await response.json();
      const risk = cfg?.risk;
      if (risk?.targetRr !== undefined) {
        this.riskRewardRatio$.next(Number(risk.targetRr));
      }
      if (risk?.defaultStopLossPct !== undefined) {
        this.defaultStopLossPct$.next(Number(risk.defaultStopLossPct));
      }
    } catch {
      // keep defaults
    }
  }

  private async loadSignalHistory(): Promise<void> {
    try {
      const response = await fetch(`${ScannerDataService.DEFAULT_API_URL}/signals/history?limit=100`);
      if (!response.ok) return;
      const payload = await response.json();
      const signals = Array.isArray(payload?.signals) ? payload.signals : [];
      const overlays: TradeLevels[] = signals
        .filter((s: any) => s.entry && s.stopLoss && s.target)
        .map((s: any) => ({
          interval: s.interval || '1m',
          entry: Number(s.entry),
          stopLoss: Number(s.stopLoss),
          target: Number(s.target),
          targetRr: Number(s.targetRr || this.riskRewardRatio$.value || 1.5),
          timestamp: s.entryTimestamp || s.timestamp,
          direction: s.entryDirection || s.direction,
        }))
        .slice(0, 100);
      this.signalOverlays$.next(overlays);
    } catch {
      // optional bootstrap history
    }
  }

  private isTradeLevels(value: any): value is TradeLevels {
    return !!value
      && typeof value.interval === 'string'
      && typeof value.entry === 'number'
      && typeof value.stopLoss === 'number'
      && typeof value.target === 'number'
      && typeof value.targetRr === 'number';
  }
}
