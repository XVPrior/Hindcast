import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

function MarketsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["markets"],
    queryFn: api.markets,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Markets</h1>
        <p className="mt-1 text-sm text-slate-600">
          What's configured and how much data is locally stored.
        </p>
      </div>

      {isLoading && <p className="text-slate-500">loading…</p>}
      {error && (
        <p className="text-red-600">load failed: {(error as Error).message}</p>
      )}

      {data && (
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Exchange</th>
                <th className="px-4 py-3 text-left font-medium">Symbol</th>
                <th className="px-4 py-3 text-left font-medium">
                  Fallback since
                </th>
                <th className="px-4 py-3 text-right font-medium">1d</th>
                <th className="px-4 py-3 text-right font-medium">4h</th>
                <th className="px-4 py-3 text-right font-medium">1h</th>
                <th className="px-4 py-3 text-right font-medium">5m</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((m) => (
                <tr key={`${m.exchange}-${m.symbol}`}>
                  <td className="px-4 py-3 text-slate-700">{m.exchange}</td>
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {m.symbol}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {m.fallback_since.slice(0, 10)}
                  </td>
                  {(["1d", "4h", "1h", "5m"] as const).map((tf) => (
                    <td
                      key={tf}
                      className="px-4 py-3 text-right tabular-nums text-slate-700"
                    >
                      {(m.bars_per_timeframe[tf] ?? 0).toLocaleString()}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export const Route = createFileRoute("/markets")({
  component: MarketsPage,
});
