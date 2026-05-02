import type { RunSummary } from "../lib/api";
import {
  STATUS_LABEL,
  STATUS_STYLE,
  getMode,
  getStatus,
  isPulsing,
  MODE_STYLE,
} from "../lib/runStatus";

const SIZE_CLS = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2.5 py-1 text-sm",
} as const;

const DOT_CLS = "w-1.5 h-1.5 rounded-full animate-pulse shrink-0";

function dotColor(status: string): string {
  if (status === "running") return "bg-blue-600";
  if (status === "stopping") return "bg-orange-600";
  return "";
}

/** Standalone Mode pill (LIVE / dry-run). */
export function ModePill({
  run,
  size = "sm",
}: {
  run: RunSummary;
  size?: "sm" | "md";
}) {
  const mode = getMode(run);
  return (
    <span
      className={`inline-flex items-center rounded font-medium ${MODE_STYLE[mode]} ${SIZE_CLS[size]}`}
    >
      {mode === "live" ? "LIVE" : "dry-run"}
    </span>
  );
}

/** Standalone Status pill (running / stopping / ok / no fills / crashed). */
export function StatusPill({
  run,
  size = "sm",
}: {
  run: RunSummary;
  size?: "sm" | "md";
}) {
  const status = getStatus(run);
  const pulse = isPulsing(status);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded font-medium ${STATUS_STYLE[status]} ${SIZE_CLS[size]}`}
    >
      {pulse && <span className={`${DOT_CLS} ${dotColor(status)}`} />}
      {STATUS_LABEL[status]}
    </span>
  );
}

/** Combined two-segment pill: [Mode | Status]. Used in list rows. */
export function RunBadges({
  run,
  size = "sm",
}: {
  run: RunSummary;
  size?: "sm" | "md";
}) {
  const mode = getMode(run);
  const status = getStatus(run);
  const pulse = isPulsing(status);
  return (
    <span className="inline-flex items-stretch rounded overflow-hidden font-medium leading-none">
      <span
        className={`inline-flex items-center ${MODE_STYLE[mode]} ${SIZE_CLS[size]}`}
      >
        {mode === "live" ? "LIVE" : "dry-run"}
      </span>
      <span
        className={`inline-flex items-center gap-1 ${STATUS_STYLE[status]} ${SIZE_CLS[size]}`}
      >
        {pulse && <span className={`${DOT_CLS} ${dotColor(status)}`} />}
        {STATUS_LABEL[status]}
      </span>
    </span>
  );
}
