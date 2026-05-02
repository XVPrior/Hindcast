import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { RunBadges } from "../../components/RunBadges";

function fmtTs(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function LivePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Live runs</h1>
        <p className="mt-1 text-sm text-slate-600">
          Audit log of every <code>hindcast live</code> session — dry-run and
          real. Polls every 10 seconds.
        </p>
      </div>

      {isLoading && <p className="text-slate-500">loading…</p>}
      {error && (
        <p className="text-red-600">
          load failed: {(error as Error).message}
        </p>
      )}

      {data && data.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">
          No live sessions yet. Run{" "}
          <code className="bg-slate-100 px-2 py-0.5 rounded text-sm">
            uv run hindcast live --dry-run
          </code>{" "}
          to create one.
        </div>
      )}

      {data && data.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Mode / Status</th>
                <th className="px-4 py-3 text-left font-medium">Strategy</th>
                <th className="px-4 py-3 text-left font-medium">Symbol</th>
                <th className="px-4 py-3 text-left font-medium">TF</th>
                <th className="px-4 py-3 text-left font-medium">Started</th>
                <th className="px-4 py-3 text-right font-medium">Bars</th>
                <th className="px-4 py-3 text-right font-medium">Orders</th>
                <th className="px-4 py-3 text-right font-medium">Fills</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((r) => (
                <tr
                  key={r.run_id}
                  className="hover:bg-slate-50 cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <Link
                      to="/live/$runId"
                      params={{ runId: r.run_id }}
                      className="block"
                    >
                      <RunBadges run={r} />
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-900">
                    <Link
                      to="/live/$runId"
                      params={{ runId: r.run_id }}
                      className="block hover:underline"
                    >
                      {r.strategy}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{r.symbol}</td>
                  <td className="px-4 py-3 text-slate-700">{r.timeframe}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {fmtTs(r.started_at)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                    {r.n_equity_points}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                    {r.n_orders}
                  </td>
                  <td
                    className={`px-4 py-3 text-right tabular-nums font-medium ${
                      r.n_fills > 0 ? "text-emerald-700" : "text-slate-400"
                    }`}
                  >
                    {r.n_fills}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export const Route = createFileRoute("/live/")({
  component: LivePage,
});
