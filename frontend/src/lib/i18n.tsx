import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Lang = "zh" | "en";

// Flat keyed dictionary — no plurals, no ICU. Add a key in both languages
// when introducing user-facing copy. Missing keys fall back to the key
// itself, which makes any oversight obvious instead of silent.
type Dict = Record<string, { zh: string; en: string }>;

const D: Dict = {
  // ----- nav / app shell -----
  "app.brand": { zh: "Hindcast", en: "Hindcast" },
  "app.dashboard": { zh: "面板", en: "dashboard" },
  "nav.overview": { zh: "概览", en: "Overview" },
  "nav.markets": { zh: "市场", en: "Markets" },
  "nav.chart": { zh: "图表", en: "Chart" },
  "nav.live": { zh: "实盘", en: "Live" },

  // ----- common -----
  "common.loading": { zh: "加载中…", en: "loading…" },
  "common.load_failed": { zh: "加载失败", en: "load failed" },
  "common.no_data": { zh: "暂无数据", en: "no data" },
  "common.checking": { zh: "检查中…", en: "checking…" },
  "common.unreachable": { zh: "无法连接", en: "unreachable" },
  "common.dash": { zh: "—", en: "—" },

  // ----- overview page -----
  "overview.title": { zh: "概览", en: "Overview" },
  "overview.subtitle": {
    zh: "本地 Hindcast 数据库的只读视图。",
    en: "Read-only view of the local Hindcast store.",
  },
  "overview.health": { zh: "后端健康", en: "Backend health" },
  "overview.markets_count": { zh: "已配置市场", en: "Configured markets" },
  "overview.total_bars": { zh: "已存储 K 线总数", en: "Total bars in store" },
  "overview.live_active": { zh: "活跃实盘 session", en: "Active live sessions" },
  "overview.markets_section": { zh: "市场快照", en: "Market snapshot" },
  "overview.recent_runs": { zh: "最近实盘 sessions", en: "Recent live sessions" },
  "overview.no_runs": { zh: "还没有实盘 session", en: "No live sessions yet" },

  // ----- markets table -----
  "markets.title": { zh: "市场", en: "Markets" },
  "markets.subtitle": {
    zh: "已配置的现货市场——最近 1d 收盘、24 小时涨跌、永续资金费率，以及各 timeframe 的 K 线储量。",
    en: "Configured spot markets — latest 1d close, 24h change, perp funding, and stored bar counts per timeframe.",
  },
  "markets.col.symbol": { zh: "标的", en: "Symbol" },
  "markets.col.last_1d": { zh: "1d 最新价", en: "Last 1d" },
  "markets.col.24h": { zh: "24h", en: "24h" },
  "markets.col.funding": { zh: "永续资金费率（年化 · 7 日）", en: "Perp funding (APR · 7d)" },
  "markets.no_funding": { zh: "无数据", en: "no data" },
  "markets.footer.refresh": {
    zh: "{n} 个市场 · 每 30 秒刷新",
    en: "{n} markets · refresh every 30s",
  },
  "markets.bars.unit": { zh: "根", en: "" },
  "markets.bars_label": { zh: "K 线 · 1d / 4h / 1h / 5m", en: "Bars · 1d / 4h / 1h / 5m" },

  // ----- chart page -----
  "chart.title": { zh: "图表", en: "Chart" },
  "chart.subtitle": {
    zh: "缓冲：{n} 根 K 线（{range}）· 默认显示最近 80 根，左滑查看更早数据。",
    en: "Buffer: {n} bars ({range}) · default view shows the most recent ~80 — scroll back for the rest.",
  },
  "chart.symbol": { zh: "标的", en: "Symbol" },
  "chart.timeframe": { zh: "周期", en: "Timeframe" },
  "chart.bars_count": { zh: "{n} 根 · 首 {first} → 末 {last}", en: "{n} bars · first {first} → last {last}" },
  "chart.loading": { zh: "正在加载 K 线…", en: "loading bars…" },
  "chart.range.1d": { zh: "约 8 年（含全部库存）", en: "~8 years (all stored)" },
  "chart.range.4h": { zh: "约 16 个月", en: "~16 months" },
  "chart.range.1h": { zh: "约 4 个月", en: "~4 months" },
  "chart.range.5m": { zh: "约 10 天", en: "~10 days" },

  // ----- live runs list -----
  "live.title": { zh: "实盘 sessions", en: "Live runs" },
  "live.subtitle": {
    zh: "每次 hindcast live 的运行记录——dry-run 和真实下单都在内。每 10 秒刷新。",
    en: "Audit log of every hindcast live session — dry-run and real. Polls every 10 seconds.",
  },
  "live.empty.title": { zh: "还没有实盘 session", en: "No live sessions yet" },
  "live.empty.hint": {
    zh: "运行 uv run hindcast live --dry-run 创建一条。",
    en: "Run uv run hindcast live --dry-run to create one.",
  },
  "live.col.mode_status": { zh: "模式 / 状态", en: "Mode / Status" },
  "live.col.strategy": { zh: "策略", en: "Strategy" },
  "live.col.symbol": { zh: "标的", en: "Symbol" },
  "live.col.tf": { zh: "周期", en: "TF" },
  "live.col.started": { zh: "开始", en: "Started" },
  "live.col.bars": { zh: "K 线", en: "Bars" },
  "live.col.orders": { zh: "订单", en: "Orders" },
  "live.col.fills": { zh: "成交", en: "Fills" },

  // ----- live run detail -----
  "live_detail.back": { zh: "← 全部 sessions", en: "← All runs" },
  "live_detail.no_orders_dryrun": {
    zh: "未发送订单——仅运行策略逻辑",
    en: "no orders sent — strategy logic only",
  },
  "live_detail.fills_filled": {
    zh: "{n} 笔订单已在 testnet 成交",
    en: "{n} order(s) filled on testnet",
  },
  "live_detail.fills_none": { zh: "无订单成交", en: "no orders filled" },
  "live_detail.stat.bars": { zh: "K 线数", en: "Bars" },
  "live_detail.stat.intents": { zh: "意图（已跳过）", en: "Intents (skipped)" },
  "live_detail.stat.orders": { zh: "订单", en: "Orders" },
  "live_detail.stat.fills": { zh: "成交", en: "Fills" },
  "live_detail.stat.pnl": { zh: "Session PnL", en: "Session PnL" },
  "live_detail.equity_section": { zh: "权益曲线", en: "Equity over time" },
  "live_detail.equity_empty": { zh: "尚无 equity 点", en: "no equity points yet" },
  "live_detail.orders_section": { zh: "订单", en: "Orders" },
  "live_detail.fills_section": { zh: "成交", en: "Fills" },
  "live_detail.no_orders": { zh: "无订单", en: "no orders" },
  "live_detail.no_fills": { zh: "无成交", en: "no fills" },
  "live_detail.btn.stop": { zh: "停止 session", en: "Stop session" },
  "live_detail.btn.stopping": { zh: "请求中…", en: "requesting…" },
  "live_detail.confirm.dryrun": {
    zh: "停止此 dry-run session？",
    en: "Stop this dry-run session?",
  },
  "live_detail.confirm.live": {
    zh: "停止此 LIVE session？下一根 bar 上的 pending 意图将不会执行。",
    en: "Stop this LIVE session? Pending intents on the next bar will not execute.",
  },
  "live_detail.waiting_ack": {
    zh: "等待引擎响应（≤ 5 秒）",
    en: "waiting for engine to acknowledge (≤ 5s)",
  },

  // ----- status pills -----
  "status.running": { zh: "运行中", en: "running" },
  "status.stopping": { zh: "停止中…", en: "stopping…" },
  "status.ok": { zh: "成功", en: "ok" },
  "status.empty": { zh: "无成交", en: "no fills" },
  "status.crashed": { zh: "崩溃", en: "crashed" },

  // ----- mode pills -----
  "mode.live": { zh: "LIVE", en: "LIVE" },
  "mode.dry_run": { zh: "dry-run", en: "dry-run" },

  // ----- order status -----
  "order_status.filled": { zh: "已成交", en: "filled" },
  "order_status.simulated": { zh: "模拟（dry-run）", en: "simulated (dry-run)" },
  "order_status.skipped_dryrun": { zh: "跳过（旧版 dry-run）", en: "skipped (legacy dry-run)" },
  "order_status.error": { zh: "错误", en: "error" },

  // ----- order/fill table headers -----
  "table.col.id": { zh: "#", en: "#" },
  "table.col.side": { zh: "方向", en: "Side" },
  "table.col.qty": { zh: "数量", en: "Qty" },
  "table.col.status": { zh: "状态", en: "Status" },
  "table.col.submitted": { zh: "提交时间", en: "Submitted" },
  "table.col.exchange_id": { zh: "交易所 ID", en: "Exchange ID" },
  "table.col.order": { zh: "订单", en: "Order" },
  "table.col.price": { zh: "价格", en: "Price" },
  "table.col.fee": { zh: "手续费", en: "Fee" },
  "table.col.filled_at": { zh: "成交时间", en: "Filled at" },
  "side.buy": { zh: "买", en: "buy" },
  "side.sell": { zh: "卖", en: "sell" },
};

const STORAGE_KEY = "hindcast.lang";

function detectInitial(): Lang {
  if (typeof window === "undefined") return "zh";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "zh" || stored === "en") return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const Ctx = createContext<LangCtx | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectInitial);
  useEffect(() => {
    document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // localStorage may be blocked in some browsers — silently ignore.
    }
  }, []);
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLang(): LangCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useLang must be used inside <LangProvider>");
  return ctx;
}

/** Translation function: t("key", { name: "Foo" }) → "Hello Foo". */
export function useT() {
  const { lang } = useLang();
  return useCallback(
    (key: string, params?: Record<string, string | number>) => {
      const entry = D[key];
      let s = entry ? entry[lang] : key;
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          s = s.replace(`{${k}}`, String(v));
        }
      }
      return s;
    },
    [lang],
  );
}
