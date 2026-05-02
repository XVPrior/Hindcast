// Typed fetch helpers — all backend calls go through this module so
// changes to the API surface only touch one place.

export interface Health {
  status: string;
  version: string;
}

export interface Market {
  exchange: string;
  symbol: string;
  timeframes: string[];
  fallback_since: string;
  bars_per_timeframe: Record<string, number>;
}

export interface Bar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BarsResponse {
  exchange: string;
  symbol: string;
  timeframe: string;
  count: number;
  bars: Bar[];
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => getJSON<Health>("/api/health"),
  markets: () => getJSON<Market[]>("/api/markets"),
  bars: (params: {
    exchange?: string;
    symbol: string;
    timeframe: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams({
      exchange: params.exchange ?? "binance",
      symbol: params.symbol,
      timeframe: params.timeframe,
      limit: String(params.limit ?? 2000),
    });
    return getJSON<BarsResponse>(`/api/markets/bars?${qs}`);
  },
};
