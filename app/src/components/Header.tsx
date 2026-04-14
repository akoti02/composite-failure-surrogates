import { PRESETS, PRESET_NAME_KEYS } from "../lib/presets";
import { COL } from "../lib/constants";
import { useLang } from "../lib/i18n";
import type { TKey } from "../lib/i18n";

interface Props {
  status: string;
  modelsReady: boolean;
  predicting: boolean;
  activePreset: string;
  onPreset: (name: string) => void;
  onExport: () => void;
  hasResults: boolean;
  onReset: () => void;
  onProjects: () => void;
  onLaminate: () => void;
}

/**
 * Language toggle pill — lives top-right in the header.
 * Users can switch EN ↔ RU any time while using the app.
 */
function LangToggle() {
  const { lang, setLang, t } = useLang();
  return (
    <div className="lang-pill" role="group" aria-label="Language">
      <button
        className={`lang-pill-btn ${lang === "en" ? "active" : ""}`}
        onClick={() => setLang("en")}
        aria-pressed={lang === "en"}
        aria-label={t("lang_switch_to_en")}
        title={t("lang_switch_to_en")}
      >
        EN
      </button>
      <button
        className={`lang-pill-btn ${lang === "ru" ? "active" : ""}`}
        onClick={() => setLang("ru")}
        aria-pressed={lang === "ru"}
        aria-label={t("lang_switch_to_ru")}
        title={t("lang_switch_to_ru")}
      >
        RU
      </button>
    </div>
  );
}

export function Header({ status, modelsReady, predicting, activePreset, onPreset, onExport, hasResults, onReset, onProjects, onLaminate }: Props) {
  const { t } = useLang();
  const dotColor = predicting ? COL.accent : modelsReady ? COL.success : COL.textDim;
  const dotClass = predicting ? "dot-pulse-fast" : modelsReady ? "" : "dot-pulse";
  const dotLabel = predicting ? t("computing") : modelsReady ? t("live") : t("loading");

  return (
    <header
      className="tooltip-below h-14 flex items-center px-5 gap-4 shrink-0"
      style={{
        background: COL.bgDark,
        borderBottom: `1px solid ${COL.border}`,
        boxShadow: "0 1px 8px rgba(0,0,0,0.35), 0 0 24px rgba(0, 234, 255, 0.04)",
      }}
    >
      <h1 className="text-[15px] font-semibold tracking-wide whitespace-nowrap" style={{ color: COL.text }}>
        <span className="text-glow-cyan" style={{ color: COL.accent }}>RP3</span>
        <span className="mx-2" style={{ color: COL.border }}>|</span>
        <span style={{ color: COL.textMid, fontWeight: 400 }}>{t("app_title")}</span>
      </h1>

      <div className="ml-auto flex items-center gap-2">
        <select
          aria-label={t("presets")}
          className="text-[13px] px-3 py-1.5 rounded-md cursor-pointer outline-none transition-colors"
          style={{
            background: COL.panel,
            border: `1px solid ${activePreset ? COL.borderBright : COL.border}`,
            color: activePreset ? COL.text : COL.textMid,
            boxShadow: activePreset ? COL.accentGlowSoft : "none",
          }}
          value={activePreset}
          onChange={(e) => onPreset(e.target.value)}
        >
          <option value="">{t("presets")}</option>
          {Object.keys(PRESETS).map((name) => {
            const key = PRESET_NAME_KEYS[name];
            return <option key={name} value={name}>{key ? t(key as TKey) : name}</option>;
          })}
        </select>

        {hasResults && (
          <button
            className="text-[13px] px-3 py-1.5 rounded-md cursor-pointer transition-colors flex items-center gap-1.5 export-enter btn-press"
            style={{
              background: COL.panel,
              border: `1px solid ${COL.border}`,
              color: COL.textMid,
            }}
            onClick={onExport}
            aria-label={t("export_tooltip")}
            data-tooltip={t("export_tooltip")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            {t("export")}
          </button>
        )}

        <button
          className="text-[13px] px-3 py-1.5 rounded-md cursor-pointer transition-colors flex items-center gap-1.5 btn-press"
          style={{
            background: COL.panel,
            border: `1px solid ${COL.border}`,
            color: COL.textMid,
          }}
          onClick={onProjects}
          aria-label={t("projects")}
          data-tooltip={t("projects_tooltip")}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
          </svg>
          {t("projects")}
        </button>

        <button
          className="text-[13px] px-3 py-1.5 rounded-md cursor-pointer transition-colors flex items-center gap-1.5 btn-press"
          style={{
            background: COL.panel,
            border: `1px solid ${COL.border}`,
            color: COL.textMid,
          }}
          onClick={onLaminate}
          aria-label={t("laminate")}
          data-tooltip={t("laminate_tooltip")}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="3" y1="15" x2="21" y2="15" />
          </svg>
          {t("laminate")}
        </button>

        {/* Check for updates — manual trigger (startup auto-check also runs) */}
        <button
          className="w-8 h-8 flex items-center justify-center rounded-md btn-press"
          style={{
            color: COL.textDim,
            border: `1px solid ${COL.border}`,
            background: "transparent",
          }}
          onClick={() => window.dispatchEvent(new CustomEvent("rp3-check-updates"))}
          aria-label={t("check_for_updates")}
          data-tooltip={t("check_for_updates")}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a9 9 0 11-3-6.7M21 3v6h-6" />
          </svg>
        </button>

        {/* Reset icon button */}
        <button
          className="w-8 h-8 flex items-center justify-center rounded-md btn-press"
          style={{
            color: COL.textDim,
            border: `1px solid ${COL.border}`,
            background: "transparent",
          }}
          onClick={onReset}
          aria-label={t("reset")}
          data-tooltip={t("reset")}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M1 4v6h6" />
            <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
          </svg>
        </button>

        {/* Language toggle — always visible, switches live. No Run button:
           predictions update live as inputs change (200ms debounce), and
           snapshot-saving lives in the Projects modal. */}
        <LangToggle />
      </div>

      <div className="flex items-center gap-2 text-[12px] max-w-[260px] overflow-hidden" style={{ color: COL.textDim }}>
        <span className={`text-[15px] shrink-0 ${dotClass}`} style={{ color: dotColor, textShadow: `0 0 8px ${dotColor}aa` }} data-tooltip={dotLabel}>&#x25CF;</span>
        <span className="truncate">
          {status.startsWith("Error:") ? status.slice(0, 50) + (status.length > 50 ? "…" : "") : status}
        </span>
      </div>

      <span
        className="text-[9px] tabular-nums select-all ml-1"
        style={{ color: COL.textDim, opacity: 0.5 }}
        title={`Build: ${__BUILD_TIMESTAMP__} (${__BUILD_HASH__})`}
      >
        {__BUILD_HASH__}
      </span>
    </header>
  );
}
