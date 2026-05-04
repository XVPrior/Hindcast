// Typed fetch helpers — all backend calls go through this module so
// changes to the API surface only touch one place.

export interface Health {
  status: string;
  version: string;
}

// /api/markets used to return a slim shape; it now returns the same
// MarketOverview as the overview endpoint. Kept this alias for any
// older imports that still reference `Market`.
export type Market = MarketOverview;

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

// In dev, paths like "/api/health" are proxied by Vite to localhost:8000.
// In prod (Cloudflare Pages → Fly), the frontend and backend live on
// different origins, so we prefix with the absolute base URL when
// VITE_API_BASE is set at build time.
const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
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

export interface MarketOverview {
  exchange: string;
  symbol: string;
  latest_close: number | null;
  latest_close_ts: string | null;
  change_24h_pct: number | null;
  total_bars: Record<string, number>;
  funding_rate: number | null;
  funding_annualized_pct: number | null;
  funding_ts: string | null;
  funding_history: number[];
}

export interface Overview {
  health: Health;
  markets: MarketOverview[];
  live_total: number;
  live_active: number;
  live_recent: RunSummary[];
  live_recent_equity: Record<string, number[]>;
}

export const api = {
  health: () => getJSON<Health>("/api/health"),
  overview: () => getJSON<Overview>("/api/overview"),
  markets: () => getJSON<MarketOverview[]>("/api/markets"),
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
    const res = await fetch(`${API_BASE}/api/runs/${id}/stop`, {
      method: "POST",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return (await res.json()) as RunSummary;
  },
};
