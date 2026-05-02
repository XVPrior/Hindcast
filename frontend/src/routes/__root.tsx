import { Link, Outlet, createRootRoute } from "@tanstack/react-router";

function NavLink({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-md text-sm font-medium"
      activeProps={{ className: "text-slate-900 bg-slate-100" }}
    >
      {label}
    </Link>
  );
}

function RootLayout() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold text-slate-900">
              Hindcast
            </span>
            <span className="text-xs text-slate-400 uppercase tracking-wider">
              dashboard
            </span>
          </div>
          <nav className="flex items-center gap-1">
            <NavLink to="/" label="Overview" />
            <NavLink to="/markets" label="Markets" />
            <NavLink to="/chart" label="Chart" />
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}

export const Route = createRootRoute({
  component: RootLayout,
});
