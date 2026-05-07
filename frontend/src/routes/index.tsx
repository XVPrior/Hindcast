import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api, type MarketOverview, type RunSummary } from "../lib/api";
import { RunBadges } from "../components/RunBadges";
import { Sparkline } from "../components/Sparkline";
import { useT } from "../lib/i18n";

function fmtCash(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmtPct(n: number | null | undefined, signed = true): string {
  if (n == null) return "—";
  const sign = signed && n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function StatCard({
  label,
  value,
  sublabel,
  href,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sublabel?: string;
  href?: string;
  tone?: "neutral" | "good" | "bad" | "muted";
}) {
  const valueColor =
    tone === "good"
      ? "text-emerald-600"
      : tone === "bad"
        ? "text-red-600"
        : tone === "muted"
          ? "text-slate-400"
          : "text-slate-900";
  const inner = (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm h-full">
      <div className="text-xs uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${valueColor}`}>{value}</div>
      {sublabel && (
        <div className="mt-1 text-xs text-slate-500">{sublabel}</div>
      )}
    </div>
  );
  if (href) {
    return (
      <Link to={href} className="block hover:[&>div]:bg-slate-50">
        {inner}
      </Link>
    );
  }
  return inner;
}

function MarketCard({ m }: { m: MarketOverview }) {
  const t = useT();
  const changeColor =
    m.change_24h_pct == null
      ? "text-slate-500"
      : m.change_24h_pct >= 0
        ? "text-emerald-600"
        : "text-red-600";
  const fundingColor =
    m.funding_rate == null
      ? "text-slate-500"
      : m.funding_rate > 0
        ? "text-emerald-600"
        : m.funding_rate < 0
          ? "text-red-600"
          : "text-slate-600";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-baseline justify-between">
        <h3 className="text-lg font-semibold text-slate-900">{m.symbol}</h3>
        <span className="text-xs text-slate-400 uppercase tracking-wider">
          {m.exchange}
        </span>
      </div>

      <div className="mt-3 flex items-baseline gap-3">
        <span className="text-3xl font-bold tabular-nums text-slate-900">
          {fmtCash(m.latest_close)}
        </span>
        <span className={`text-sm font-medium ${changeColor}`}>
          {fmtPct(m.change_24h_pct)} <span className="text-slate-400">/ 24h</span>
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{fmtTime(m.latest_close_ts)}</p>

      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded bg-slate-50 px-3 py-2">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-wider text-slate-500">
              {t("markets.col.funding")}
            </div>
            {m.funding_history.length > 1 && (
              <Sparkline
                values={m.funding_history.map((r) => r * 100)}
                baseline={0}
                width={80}
                height={26}
              />
            )}
          </div>
          <div className={`mt-1 font-semibold ${fundingColor}`}>
            {m.funding_annualized_pct == null
              ? "—"
              : `${fmtPct(m.funding_annualized_pct)} APR`}
          </div>
          <div className="text-[10px] text-slate-400">
            per 8h: {m.funding_rate == null ? "—" : (m.funding_rate * 100).toFixed(4) + "%"}
          </div>
        </div>
        <div className="rounded bg-slate-50 px-3 py-2">
          <div className="text-xs uppercase tracking-wider text-slate-500">
            {t("markets.bars_label")}
          </div>
          <div className="mt-0.5 text-xs text-slate-700 leading-relaxed">
            {Object.entries(m.total_bars).map(([tf, n]) => (
              <div key={tf} className="flex justify-between">
                <span className="text-slate-500">{tf}</span>
                <span className="tabular-nums font-medium">
                  {n.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function RecentRunRow({
  r,
  equity,
}: {
  r: RunSummary;
  equity: number[] | undefined;
}) {
  const t = useT();
  const baseline = equity && equity.length > 0 ? equity[0] : null;
  return (
    <Link
      to="/live/$runId"
      params={{ runId: r.run_id }}
      className="flex items-center gap-4 px-4 py-2.5 hover:bg-slate-50 border-b border-slate-100 last:border-b-0"
    >
      <div className="shrink-0">
        <RunBadges run={r} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-slate-900 truncate">{r.strategy}</div>
        <div className="text-xs text-slate-500">
          {r.symbol} {r.timeframe} · {fmtTime(r.started_at)}
        </div>
      </div>
      <div className="shrink-0">
        {equity && equity.length > 1 ? (
          <Sparkline values={equity} baseline={baseline} width={100} height={28} />
        ) : (
          <div className="w-[100px] h-[28px]" />
        )}
      </div>
      <div className="shrink-0 text-right text-xs text-slate-500 tabular-nums w-32">
        <div>
          <span className="text-slate-700 font-medium">{r.n_equity_points}</span>{" "}
          {t("live.col.bars").toLowerCase()}
        </div>
        <div>
          <span className={r.n_fills > 0 ? "text-emerald-700 font-medium" : "text-slate-400"}>
            {r.n_fills}
          </span>{" "}
          {t("live.col.fills").toLowerCase()} · {r.n_orders}{" "}
          {t("live.col.orders").toLowerCase()}
        </div>
      </div>
    </Link>
  );
}

function HomePage() {
  const t = useT();
  const { data, isLoading, error } = useQuery({
    queryKey: ["overview"],
    queryFn: api.overview,
    refetchInterval: 5_000,
  });

  if (isLoading) return <p className="text-slate-500">{t("common.loading")}</p>;
  if (error)
    return (
      <p className="text-red-600">
        {t("common.load_failed")}: {(error as Error).message}
      </p>
    );
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{t("overview.title")}</h1>
        <p className="mt-1 text-sm text-slate-600">{t("overview.subtitle")}</p>
      </div>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label={t("overview.health")}
          value={data.health.status === "ok" ? "OK" : data.health.status}
          sublabel={`v${data.health.version}`}
          tone={data.health.status === "ok" ? "good" : "bad"}
        />
        <StatCard
          label={t("overview.live_active")}
          value={data.live_active.toString()}
          sublabel={`${data.live_total} total`}
          href="/live"
          tone={data.live_active > 0 ? "good" : "muted"}
        />
        <StatCard
          label={t("overview.markets_count")}
          value={data.markets.length.toString()}
          href="/markets"
        />
        <StatCard
          label={t("overview.total_bars")}
          value={data.markets
            .reduce(
              (acc, m) =>
                acc + Object.values(m.total_bars).reduce((a, b) => a + b, 0),
              0,
            )
            .toLocaleString()}
        />
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wider text-slate-500 mb-3">
          {t("overview.markets_section")}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.markets.map((m) => (
            <MarketCard key={`${m.exchange}-${m.symbol}`} m={m} />
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-sm uppercase tracking-wider text-slate-500">
            {t("overview.recent_runs")}
          </h2>
          <Link
            to="/live"
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            {t("nav.live")} →
          </Link>
        </div>
        {data.live_recent.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-slate-500 text-sm">
            {t("overview.no_runs")}
          </div>
        ) : (
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
            {data.live_recent.map((r) => (
              <RecentRunRow
                key={r.run_id}
                r={r}
                equity={data.live_recent_equity[r.run_id]}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export const Route = createFileRoute("/")({
  component: HomePage,
});
