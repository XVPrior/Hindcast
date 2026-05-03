import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api, type MarketOverview } from "../lib/api";
import { Sparkline } from "../components/Sparkline";

const ALL_TFS = ["1d", "4h", "1h", "5m"] as const;

function fmtCash(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1000) return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function ChangePill({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-slate-400">—</span>;
  const cls = pct >= 0 ? "text-emerald-700" : "text-red-700";
  return <span className={`tabular-nums font-medium ${cls}`}>{fmtPct(pct)}</span>;
}

function FundingCell({ m }: { m: MarketOverview }) {
  if (m.funding_annualized_pct == null) {
    return <span className="text-slate-400 text-xs">no data</span>;
  }
  const cls =
    m.funding_annualized_pct > 0
      ? "text-emerald-700"
      : m.funding_annualized_pct < 0
        ? "text-red-700"
        : "text-slate-700";
  return (
    <div className="flex items-center gap-2">
      <span className={`tabular-nums font-medium ${cls}`}>
        {fmtPct(m.funding_annualized_pct)}
      </span>
      {m.funding_history.length > 1 && (
        <Sparkline
          values={m.funding_history.map((r) => r * 100)}
          baseline={0}
          width={56}
          height={20}
        />
      )}
    </div>
  );
}

function BarsCell({ count }: { count: number }) {
  if (count === 0) return <span className="text-slate-300">—</span>;
  return (
    <span className="tabular-nums text-slate-700">
      {count.toLocaleString()}
    </span>
  );
}

function MarketsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["markets-rich"],
    queryFn: api.markets,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Markets</h1>
        <p className="mt-1 text-sm text-slate-600">
          Configured spot markets — latest 1d close, 24h change, perp funding,
          and stored bar counts per timeframe.
        </p>
      </div>

      {isLoading && <p className="text-slate-500">loading…</p>}
      {error && (
        <p className="text-red-600">load failed: {(error as Error).message}</p>
      )}

      {data && (
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Symbol</th>
                <th className="px-4 py-3 text-right font-medium">Last 1d</th>
                <th className="px-4 py-3 text-right font-medium">24h</th>
                <th className="px-4 py-3 text-left font-medium">
                  Perp funding (APR · 7d)
                </th>
                {ALL_TFS.map((tf) => (
                  <th
                    key={tf}
                    className="px-4 py-3 text-right font-medium tabular-nums"
                  >
                    {tf}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((m) => (
                <tr key={`${m.exchange}-${m.symbol}`}>
                  <td className="px-4 py-3">
                    <Link
                      to="/chart"
                      search={{ symbol: m.symbol, timeframe: "1d" }}
                      className="font-semibold text-slate-900 hover:text-slate-700 hover:underline"
                    >
                      {m.symbol}
                    </Link>
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider">
                      {m.exchange}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-900 font-medium">
                    {fmtCash(m.latest_close)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ChangePill pct={m.change_24h_pct} />
                  </td>
                  <td className="px-4 py-3">
                    <FundingCell m={m} />
                  </td>
                  {ALL_TFS.map((tf) => (
                    <td key={tf} className="px-4 py-3 text-right">
                      <BarsCell count={m.total_bars[tf] ?? 0} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <td colSpan={4} className="px-4 py-2">
                  {data.length} markets · refresh every 30s
                </td>
                {ALL_TFS.map((tf) => {
                  const total = data.reduce(
                    (acc, m) => acc + (m.total_bars[tf] ?? 0),
                    0,
                  );
                  return (
                    <td
                      key={tf}
                      className="px-4 py-2 text-right tabular-nums font-medium text-slate-700"
                    >
                      {total.toLocaleString()}
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

export const Route = createFileRoute("/markets")({
  component: MarketsPage,
});
