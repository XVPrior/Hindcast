import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { RunBadges } from "../../components/RunBadges";
import { useT } from "../../lib/i18n";

function fmtTs(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function LivePage() {
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{t("live.title")}</h1>
        <p className="mt-1 text-sm text-slate-600">{t("live.subtitle")}</p>
      </div>

      {isLoading && <p className="text-slate-500">{t("common.loading")}</p>}
      {error && (
        <p className="text-red-600">
          {t("common.load_failed")}: {(error as Error).message}
        </p>
      )}

      {data && data.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500">
          <p className="font-medium">{t("live.empty.title")}</p>
          <p className="mt-2 text-sm">{t("live.empty.hint")}</p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left font-medium">
                  {t("live.col.mode_status")}
                </th>
                <th className="px-4 py-3 text-left font-medium">
                  {t("live.col.strategy")}
                </th>
                <th className="px-4 py-3 text-left font-medium">
                  {t("live.col.symbol")}
                </th>
                <th className="px-4 py-3 text-left font-medium">
                  {t("live.col.tf")}
                </th>
                <th className="px-4 py-3 text-left font-medium">
                  {t("live.col.started")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("live.col.bars")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("live.col.orders")}
                </th>
                <th className="px-4 py-3 text-right font-medium">
                  {t("live.col.fills")}
                </th>
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
