import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { PriceChart } from "../components/PriceChart";

const TIMEFRAMES = ["1d", "4h", "1h", "5m"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

function ChartPage() {
  const markets = useQuery({ queryKey: ["markets"], queryFn: api.markets });
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("1d");

  const bars = useQuery({
    queryKey: ["bars", symbol, timeframe],
    queryFn: () => api.bars({ symbol, timeframe, limit: 2000 }),
    enabled: !!symbol && !!timeframe,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Chart</h1>
        <p className="mt-1 text-sm text-slate-600">
          Local OHLCV — last 2,000 bars.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs uppercase tracking-wider text-slate-500">
          Symbol
        </label>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
        >
          {(markets.data ?? []).map((m) => (
            <option key={`${m.exchange}-${m.symbol}`} value={m.symbol}>
              {m.symbol}
            </option>
          ))}
        </select>

        <label className="text-xs uppercase tracking-wider text-slate-500 ml-2">
          Timeframe
        </label>
        <select
          value={timeframe}
          onChange={(e) => setTimeframe(e.target.value as Timeframe)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
        >
          {TIMEFRAMES.map((tf) => (
            <option key={tf} value={tf}>
              {tf}
            </option>
          ))}
        </select>

        {bars.data && (
          <span className="ml-auto text-xs text-slate-500">
            {bars.data.count.toLocaleString()} bars
          </span>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        {bars.isLoading && (
          <p className="text-slate-500">loading bars…</p>
        )}
        {bars.error && (
          <p className="text-red-600">
            load failed: {(bars.error as Error).message}
          </p>
        )}
        {bars.data && <PriceChart bars={bars.data.bars} />}
      </div>
    </div>
  );
}

export const Route = createFileRoute("/chart")({
  component: ChartPage,
});
