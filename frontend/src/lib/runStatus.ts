// Derive presentational state from a RunSummary so the list and detail
// pages stay consistent.

import type { RunSummary } from "./api";

export type RunStatus =
  | "running" // active, no stop requested
  | "stopping" // active, stop requested
  | "ok" // ended cleanly, has fills (live mode)
  | "empty" // ended cleanly, no fills (live or dry-run)
  | "crashed"; // ended without a clean shutdown

export function getStatus(run: RunSummary): RunStatus {
  if (run.active && run.stop_requested) return "stopping";
  if (run.active) return "running";
  if (run.crashed_at) return "crashed";
  if (run.n_fills > 0) return "ok";
  return "empty";
}

// Display labels live in i18n.tsx (status.running / status.stopping / etc).
// className modifiers for status pills — kept ring-free so the segmented
// pill in RunBadges renders flush across both halves.
export const STATUS_STYLE: Record<RunStatus, string> = {
  running: "bg-blue-100 text-blue-800",
  stopping: "bg-orange-100 text-orange-800",
  ok: "bg-emerald-100 text-emerald-800",
  empty: "bg-slate-100 text-slate-600",
  crashed: "bg-red-200 text-red-900",
};

export function isPulsing(status: RunStatus): boolean {
  return status === "running" || status === "stopping";
}

export const MODE_STYLE: Record<"live" | "dry-run", string> = {
  live: "bg-red-100 text-red-800",
  "dry-run": "bg-yellow-100 text-yellow-800",
};

export function getMode(run: RunSummary): "live" | "dry-run" {
  return run.dry_run ? "dry-run" : "live";
}
