import { useLang } from "../lib/i18n";

export function LangSwitcher() {
  const { lang, setLang } = useLang();
  const baseCls =
    "px-2 py-0.5 text-xs font-medium rounded transition-colors leading-none";
  const activeCls = "bg-slate-900 text-white";
  const inactiveCls = "text-slate-500 hover:text-slate-900";

  return (
    <div className="inline-flex items-center gap-1 ml-3 rounded border border-slate-200 px-1 py-0.5">
      <button
        type="button"
        onClick={() => setLang("zh")}
        className={`${baseCls} ${lang === "zh" ? activeCls : inactiveCls}`}
      >
        中
      </button>
      <button
        type="button"
        onClick={() => setLang("en")}
        className={`${baseCls} ${lang === "en" ? activeCls : inactiveCls}`}
      >
        EN
      </button>
    </div>
  );
}
