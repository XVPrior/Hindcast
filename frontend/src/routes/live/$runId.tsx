import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type LiveOrder } from "../../lib/api";
import { EquityChart } from "../../components/EquityChart";
import { RunBadges } from "../../components/RunBadges";

// Same sizing as RunBadges sm so all pills on the page share dimensions.
const PILL_SM = "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium leading-none";

function OrderStatusPill({ status }: { status: string }) {
  // Old data may have "skipped_dryrun" — pre-virtual-portfolio dry-run
  // sessions where no fill was recorded. New data uses "simulated".
  const cls =
    status === "filled"
      ? "bg-emerald-100 text-emerald-800"
      : status === "simulated"
        ? "bg-yellow-100 text-yellow-800"
        : status === "skipped_dryrun"
          ? "bg-slate-100 text-slate-600"
          : status === "error"
            ? "bg-red-100 text-red-800"
            : "bg-slate-100 text-slate-700";
  const label =
    status === "skipped_dryrun"
      ? "skipped (legacy dry-run)"
      : status === "simulated"
        ? "simulated (dry-run)"
        : status;
  return <span className={`${PILL_SM} ${cls}`}>{label}</span>;
}

function SidePill({ side }: { side: "buy" | "sell" }) {
  const cls =
    side === "buy"
      ? "bg-emerald-100 text-emerald-800"
      : "bg-red-100 text-red-800";
  return <span className={`${PILL_SM} ${cls}`}>{side}</span>;
}

function fmt(iso: string): string {
  return new Date(iso).toLocaleString();
}

function RunDetail() {
  const { runId } = Route.useParams();
  const queryClient = useQueryClient();

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: 5_000,
  });

  const stopMutation = useMutation({
    mutationFn: () => api.stopRun(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });
  const equity = useQuery({
    queryKey: ["run-equity", runId],
    queryFn: () => api.runEquity(runId),
    refetchInterval: 5_000,
  });
  const orders = useQuery({
    queryKey: ["run-orders", runId],
    queryFn: () => api.runOrders(runId),
    refetchInterval: 5_000,
  });
  const fills = useQuery({
    queryKey: ["run-fills", runId],
    queryFn: () => api.runFills(runId),
    refetchInterval: 5_000,
  });

  if (run.isLoading) return <p className="text-slate-500">loading…</p>;
  if (run.error) {
    return (
      <p className="text-red-600">load failed: {(run.error as Error).message}</p>
    );
  }
  if (!run.data) return null;

  const r = run.data;
  const points = equity.data?.points ?? [];
  const startEquity = points[0]?.equity;
  const lastEquity = points[points.length - 1]?.equity;
  const pnl =
    startEquity !== undefined && lastEquity !== undefined
      ? lastEquity - startEquity
      : undefined;

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/live"
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          ← All runs
        </Link>
        <div className="mt-2 flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold text-slate-900">{r.strategy}</h1>
          <RunBadges run={r} size="md" />
          {r.active && !r.stop_requested && (
            <button
              type="button"
              onClick={() => {
                if (
                  window.confirm(
                    r.dry_run
                      ? "Stop this dry-run session?"
                      : "Stop this LIVE session? Pending intents on the next bar will not execute.",
                  )
                ) {
                  stopMutation.mutate();
                }
              }}
              disabled={stopMutation.isPending}
              className="ml-auto rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-red-700 disabled:opacity-50"
            >
              {stopMutation.isPending ? "requesting…" : "Stop session"}
            </button>
          )}
          {r.active && r.stop_requested && (
            <span className="ml-auto text-sm text-orange-700">
              waiting for engine to acknowledge (≤ 5s)
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-slate-600">
          {r.symbol} · {r.timeframe} · started {fmt(r.started_at)}
          {r.ended_at && <> · ended {fmt(r.ended_at)}</>}
          {r.dry_run && (
            <>
              {" · "}
              <span className="text-yellow-700">no orders sent — strategy logic only</span>
            </>
          )}
          {!r.dry_run && (
            <>
              {" · "}
              <span className="text-red-700 font-medium">
                {r.n_fills > 0 ? `${r.n_fills} order(s) filled on testnet` : "no orders filled"}
              </span>
            </>
          )}
        </p>
        <p className="mt-1 text-xs text-slate-400 font-mono">{r.run_id}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label="Bars" value={r.n_equity_points.toString()} />
        <Stat
          label={r.dry_run ? "Intents (skipped)" : "Orders"}
          value={r.n_orders.toString()}
          tone={r.dry_run ? "muted" : "neutral"}
        />
        <Stat
          label="Fills"
          value={r.n_fills.toString()}
          tone={
            r.dry_run ? "muted" : r.n_fills > 0 ? "good" : "neutral"
          }
        />
        <Stat
          label="Session PnL"
          value={
            pnl === undefined
              ? "—"
              : `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)}`
          }
          tone={
            pnl === undefined ? "neutral" : pnl >= 0 ? "good" : "bad"
          }
        />
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-medium text-slate-700 mb-3">
          Equity over time
        </h2>
        {points.length === 0 && (
          <p className="text-slate-500 text-sm">no equity points yet</p>
        )}
        {points.length > 0 && <EquityChart points={points} />}
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-700 mb-3">Orders</h2>
        <OrdersTable orders={orders.data ?? []} />
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-700 mb-3">Fills</h2>
        <FillsTable fills={fills.data ?? []} />
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "bad" | "muted";
}) {
  const color =
    tone === "good"
      ? "text-emerald-600"
      : tone === "bad"
        ? "text-red-600"
        : tone === "muted"
          ? "text-slate-400"
          : "text-slate-900";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function OrdersTable({ orders }: { orders: LiveOrder[] }) {
  if (orders.length === 0) {
    return <p className="text-slate-500 text-sm">no orders</p>;
  }
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
          <tr>
            <th className="px-4 py-2 text-right font-medium">#</th>
            <th className="px-4 py-2 text-left font-medium">Side</th>
            <th className="px-4 py-2 text-right font-medium">Qty</th>
            <th className="px-4 py-2 text-left font-medium">Status</th>
            <th className="px-4 py-2 text-left font-medium">Submitted</th>
            <th className="px-4 py-2 text-left font-medium">Exchange ID</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {orders.map((o) => (
            <tr key={o.order_id}>
              <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                {o.order_id}
              </td>
              <td className="px-4 py-2">
                <SidePill side={o.side} />
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {o.quantity.toFixed(8).replace(/0+$/, "").replace(/\.$/, "")}
              </td>
              <td className="px-4 py-2">
                <OrderStatusPill status={o.status} />
              </td>
              <td className="px-4 py-2 text-slate-500 text-xs">
                {fmt(o.submit_ts)}
              </td>
              <td className="px-4 py-2 text-slate-500 text-xs font-mono">
                {o.exchange_id ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FillsTable({ fills }: { fills: { fill_ts: string; side: "buy" | "sell"; quantity: number; price: number; fee: number; fee_currency: string | null; order_id: number }[] }) {
  if (fills.length === 0) {
    return <p className="text-slate-500 text-sm">no fills</p>;
  }
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
          <tr>
            <th className="px-4 py-2 text-right font-medium">Order</th>
            <th className="px-4 py-2 text-left font-medium">Side</th>
            <th className="px-4 py-2 text-right font-medium">Qty</th>
            <th className="px-4 py-2 text-right font-medium">Price</th>
            <th className="px-4 py-2 text-right font-medium">Fee</th>
            <th className="px-4 py-2 text-left font-medium">Filled at</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {fills.map((f, i) => (
            <tr key={`${f.order_id}-${i}`}>
              <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                {f.order_id}
              </td>
              <td className="px-4 py-2">
                <SidePill side={f.side} />
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                {f.quantity.toFixed(8).replace(/0+$/, "").replace(/\.$/, "")}
              </td>
              <td className="px-4 py-2 text-right tabular-nums">
                ${f.price.toFixed(2)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                {f.fee} {f.fee_currency ?? ""}
              </td>
              <td className="px-4 py-2 text-slate-500 text-xs">
                {fmt(f.fill_ts)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const Route = createFileRoute("/live/$runId")({
  component: RunDetail,
});
