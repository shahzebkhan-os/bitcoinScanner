export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorSnapshot {
  emaFast: number;
  emaSlow: number;
  emaCrossover: string;
  rsi: number;
  macdLine: number;
  macdSignal: number;
  macdHistogram: number;
  macdCross: string;
  bbUpper: number;
  bbMiddle: number;
  bbLower: number;
  bbBandwidth: number;
  closeVsBb: string;
  vwap: number;
  closeVsVwap: string;
  currentVolume: number;
  avgVolume: number;
  volumeRatio: number;
  currentPrice: number;
  timestamp: string;
}

export interface SignalResult {
  strategyName: string;
  direction: string;
  strength: number;
  reason: string;
}

export interface ConsensusResult {
  direction: string;
  longVotes: number;
  shortVotes: number;
  neutralVotes: number;
  avgStrength: number;
  agreeingStrategies: string[];
  fired: boolean;
}

export interface FiredSignal {
  timestamp: string;
  direction: string;
  price: number;
  votes: string;
  strategies: string[];
  strength: number;
  rsi: number;
  volumeRatio: number;
}

export interface SessionStats {
  total: number;
  longs: number;
  shorts: number;
  lastSignalTime: string | null;
}

export interface IntervalTrendBreakdown {
  longVotes: number;
  shortVotes: number;
  neutralVotes: number;
  consensus: string;
}

export interface OverallTrend {
  timeHorizon: string;
  direction: string;
  confidence: number;
  totalLongVotes: number;
  totalShortVotes: number;
  totalNeutralVotes: number;
  intervals: Record<string, IntervalTrendBreakdown>;
}
