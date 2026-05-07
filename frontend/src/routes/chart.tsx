import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { PriceChart } from "../components/PriceChart";
import { useT } from "../lib/i18n";

const TIMEFRAMES = ["1d", "4h", "1h", "5m"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

interface ChartSearch {
  symbol: string;
  timeframe: Timeframe;
}

// Generous fixed buffer per timeframe — gives plenty of room to scroll
// back. The chart only renders ~80 bars at default zoom; the rest sit
// waiting for the user to pan/zoom out.
//   1d × 3000 = ~8 years (we only have ~3.3y, so this returns everything)
//   4h × 3000 = ~16 months
//   1h × 3000 = ~4 months
//   5m × 3000 = ~10 days
const BUFFER_BARS = 3000;

function ChartPage() {
  const t = useT();
  const markets = useQuery({ queryKey: ["markets"], queryFn: api.markets });
  const { symbol, timeframe } = Route.useSearch();
  const navigate = Route.useNavigate();
  const setSymbol = (s: string) =>
    navigate({ search: { symbol: s, timeframe } });
  const setTimeframe = (tf: Timeframe) =>
    navigate({ search: { symbol, timeframe: tf } });

  const bars = useQuery({
    queryKey: ["bars", symbol, timeframe, BUFFER_BARS],
    queryFn: () => api.bars({ symbol, timeframe, limit: BUFFER_BARS }),
    enabled: !!symbol && !!timeframe,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{t("chart.title")}</h1>
        <p className="mt-1 text-sm text-slate-600">
          {t("chart.subtitle", {
            n: BUFFER_BARS.toLocaleString(),
            range: t(`chart.range.${timeframe}`),
          })}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs uppercase tracking-wider text-slate-500">
          {t("chart.symbol")}
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
          {t("chart.timeframe")}
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
            {t("chart.bars_count", {
              n: bars.data.count.toLocaleString(),
              first: new Date(bars.data.bars[0]?.timestamp ?? "").toLocaleDateString(),
              last: new Date(bars.data.bars[bars.data.bars.length - 1]?.timestamp ?? "").toLocaleDateString(),
            })}
          </span>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        {bars.isLoading && <p className="text-slate-500">{t("chart.loading")}</p>}
        {bars.error && (
          <p className="text-red-600">
            {t("common.load_failed")}: {(bars.error as Error).message}
          </p>
        )}
        {bars.data && <PriceChart bars={bars.data.bars} height={520} />}
      </div>
    </div>
  );
}

export const Route = createFileRoute("/chart")({
  component: ChartPage,
  validateSearch: (search: Record<string, unknown>): ChartSearch => {
    const symbol =
      typeof search.symbol === "string" && search.symbol
        ? search.symbol
        : "BTC/USDT";
    const tfRaw = search.timeframe;
    const timeframe = TIMEFRAMES.includes(tfRaw as Timeframe)
      ? (tfRaw as Timeframe)
      : "1d";
    return { symbol, timeframe };
  },
});
