import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-medium text-slate-700 mb-2">{title}</h2>
      {children}
    </div>
  );
}

function HomePage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 5_000,
  });
  const markets = useQuery({ queryKey: ["markets"], queryFn: api.markets });

  const totalBars = markets.data?.reduce(
    (acc, m) =>
      acc + Object.values(m.bars_per_timeframe).reduce((a, b) => a + b, 0),
    0,
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Overview</h1>
        <p className="mt-1 text-sm text-slate-600">
          Read-only view of the local Hindcast store.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="Backend health">
          {health.isLoading && (
            <p className="text-sm text-slate-500">checking…</p>
          )}
          {health.error && (
            <p className="text-sm text-red-600">
              unreachable: {(health.error as Error).message}
            </p>
          )}
          {health.data && (
            <p className="text-sm text-emerald-600">
              {health.data.status} · v{health.data.version}
            </p>
          )}
        </Card>

        <Card title="Configured markets">
          {markets.isLoading && (
            <p className="text-sm text-slate-500">loading…</p>
          )}
          {markets.data && (
            <p className="text-2xl font-semibold text-slate-900">
              {markets.data.length}
            </p>
          )}
        </Card>

        <Card title="Total bars in store">
          {markets.isLoading && (
            <p className="text-sm text-slate-500">loading…</p>
          )}
          {totalBars !== undefined && (
            <p className="text-2xl font-semibold text-slate-900">
              {totalBars.toLocaleString()}
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

export const Route = createFileRoute("/")({
  component: HomePage,
});
