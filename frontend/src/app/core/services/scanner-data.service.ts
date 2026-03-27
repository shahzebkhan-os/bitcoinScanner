import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { WebsocketService } from './websocket.service';
import {
  Candle,
  IndicatorSnapshot,
  SignalResult,
  ConsensusResult,
  FiredSignal,
  SessionStats
} from '../models/scanner.models';

@Injectable({
  providedIn: 'root'
})
export class ScannerDataService {
  public candles$ = new BehaviorSubject<Candle[]>([]);
  public latestIndicators$ = new BehaviorSubject<IndicatorSnapshot | null>(null);
  public strategyVotes$ = new BehaviorSubject<SignalResult[]>([]);
  public consensus$ = new BehaviorSubject<ConsensusResult | null>(null);
  public signalFeed$ = new BehaviorSubject<FiredSignal[]>([]);
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

    // Connect to WebSocket
    this.wsService.connect('ws://localhost:8765/ws');
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
        volumeRatio: message.volume_ratio
      };

      const currentSignals = this.signalFeed$.value;
      const newSignals = [signal, ...currentSignals].slice(0, 100); // Keep last 100
      this.signalFeed$.next(newSignals);

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
}
