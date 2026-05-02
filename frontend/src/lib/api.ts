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

// ----- live trading -----

export interface RunSummary {
  run_id: string;
  started_at: string;
  ended_at: string | null;
  strategy: string;
  symbol: string;
  timeframe: string;
  dry_run: boolean;
  params: string | null;
  n_orders: number;
  n_fills: number;
  n_equity_points: number;
  active: boolean;
  stop_requested: boolean;
  crashed_at: string | null;
}

export interface LiveOrder {
  order_id: number;
  run_id: string;
  intent_ts: string;
  submit_ts: string;
  side: "buy" | "sell";
  quantity: number;
  status: string;
  exchange_id: string | null;
  error_message: string | null;
}

export interface LiveFill {
  run_id: string;
  order_id: number;
  fill_ts: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  fee: number;
  fee_currency: string | null;
}

export interface LiveEquityPoint {
  timestamp: string;
  cash: number;
  position: number;
  price: number;
  equity: number;
}

export interface LiveEquityResponse {
  run_id: string;
  count: number;
  points: LiveEquityPoint[];
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
  runs: () => getJSON<RunSummary[]>("/api/runs"),
  run: (id: string) => getJSON<RunSummary>(`/api/runs/${id}`),
  runOrders: (id: string) => getJSON<LiveOrder[]>(`/api/runs/${id}/orders`),
  runFills: (id: string) => getJSON<LiveFill[]>(`/api/runs/${id}/fills`),
  runEquity: (id: string) => getJSON<LiveEquityResponse>(`/api/runs/${id}/equity`),
  stopRun: async (id: string): Promise<RunSummary> => {
    const res = await fetch(`/api/runs/${id}/stop`, { method: "POST" });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return (await res.json()) as RunSummary;
  },
};
