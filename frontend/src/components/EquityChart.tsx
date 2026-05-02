import { useEffect, useRef } from "react";
import {
  ColorType,
  LineSeries,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";

import type { LiveEquityPoint } from "../lib/api";

interface Props {
  points: LiveEquityPoint[];
  height?: number;
}

export function EquityChart({ points, height = 320 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#475569",
      },
      grid: {
        vertLines: { color: "#f1f5f9" },
        horzLines: { color: "#f1f5f9" },
      },
      width: el.clientWidth,
      height,
      timeScale: { borderColor: "#e2e8f0", timeVisible: true },
      rightPriceScale: { borderColor: "#e2e8f0" },
    });
    chartRef.current = chart;

    const series = chart.addSeries(LineSeries, {
      color: "#3a6ea5",
      lineWidth: 2,
    });
    series.setData(
      points.map((p) => ({
        time: Math.floor(new Date(p.timestamp).getTime() / 1000) as Time,
        value: p.equity,
      })),
    );
    chart.timeScale().fitContent();

    const onResize = () => chart.applyOptions({ width: el.clientWidth });
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [points, height]);

  return <div ref={containerRef} className="w-full" />;
}
