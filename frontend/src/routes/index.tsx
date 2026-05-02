import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

interface Health {
  status: string;
  version: string;
}

async function fetchHealth(): Promise<Health> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as Health;
}

function HomePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5_000,
  });

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <h1 className="text-3xl font-bold text-slate-900">Hindcast</h1>
      <p className="mt-2 text-slate-600">M4 dashboard scaffolding.</p>

      <div className="mt-8 max-w-md rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-medium text-slate-700">Backend health</h2>
        {isLoading && (
          <p className="mt-1 text-sm text-slate-500">checking…</p>
        )}
        {error && (
          <p className="mt-1 text-sm text-red-600">
            unreachable: {(error as Error).message}
          </p>
        )}
        {data && (
          <p className="mt-1 text-sm text-emerald-600">
            {data.status} · v{data.version}
          </p>
        )}
      </div>
    </div>
  );
}

export const Route = createFileRoute("/")({
  component: HomePage,
});
