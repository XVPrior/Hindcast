// Tiny inline-SVG sparkline. Used on the overview page where loading
// lightweight-charts (165KB) for thumbnails would be wasteful.

interface Props {
  values: number[];
  width?: number;
  height?: number;
  /** If provided and within range, draws a dashed reference line at this y. */
  baseline?: number | null;
  /** Override stroke color. By default, derives from start vs end. */
  stroke?: string;
}

export function Sparkline({
  values,
  width = 120,
  height = 32,
  baseline = null,
  stroke,
}: Props) {
  if (values.length < 2) {
    return (
      <div
        style={{ width, height }}
        className="bg-slate-50 rounded text-[10px] text-slate-400 flex items-center justify-center"
      >
        —
      </div>
    );
  }

  const min = Math.min(...values, baseline ?? Infinity);
  const max = Math.max(...values, baseline ?? -Infinity);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);

  const path = values
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * height;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  const trendUp = values[values.length - 1] >= values[0];
  const lineColor = stroke ?? (trendUp ? "#10b981" : "#ef4444");

  let baselineY: number | null = null;
  if (baseline !== null && baseline >= min && baseline <= max) {
    baselineY = height - ((baseline - min) / range) * height;
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="block"
    >
      {baselineY !== null && (
        <line
          x1={0}
          y1={baselineY}
          x2={width}
          y2={baselineY}
          stroke="#cbd5e1"
          strokeDasharray="2 2"
          strokeWidth={1}
        />
      )}
      <path
        d={path}
        fill="none"
        stroke={lineColor}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
