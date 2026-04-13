import { PRESETS } from "../lib/presets";
import { COL } from "../lib/constants";

interface Props {
  status: string;
  modelsReady: boolean;
  predicting: boolean;
  onPreset: (name: string) => void;
  onExport: () => void;
  hasResults: boolean;
  onPredict: () => void;
  onReset: () => void;
}

export function Header({ status, modelsReady, predicting, onPreset, onExport, hasResults, onPredict, onReset }: Props) {
  const dotColor = predicting ? COL.accent : modelsReady ? COL.success : COL.textDim;
  const dotClass = predicting ? "dot-pulse-fast" : modelsReady ? "" : "dot-pulse";
  const dotLabel = predicting ? "Computing" : modelsReady ? "Live" : "Loading";

  return (
    <header
      className="h-12 flex items-center px-5 gap-4 shrink-0"
      style={{
        background: COL.bgDark,
        borderBottom: `1px solid ${COL.border}`,
        boxShadow: "0 1px 8px rgba(0,0,0,0.3)",
      }}
    >
      <h1 className="text-[13px] font-semibold tracking-wide whitespace-nowrap" style={{ color: COL.text }}>
        <span style={{ color: COL.accent }}>RP3</span>
        <span className="mx-2" style={{ color: COL.border }}>|</span>
        <span style={{ color: COL.textMid, fontWeight: 400 }}>Composite Failure Surrogate</span>
      </h1>

      <div className="ml-auto flex items-center gap-2">
        <select
          aria-label="Load a preset scenario"
          className="text-[11px] px-2.5 py-1 rounded-md cursor-pointer outline-none transition-colors focus-visible:ring-2 focus-visible:ring-indigo-500"
          style={{
            background: COL.panel,
            border: `1px solid ${COL.border}`,
            color: COL.textMid,
          }}
          defaultValue=""
          onChange={(e) => { onPreset(e.target.value); e.target.value = ""; }}
        >
          <option value="" disabled>Presets</option>
          {Object.keys(PRESETS).map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>

        {hasResults && (
          <button
            className="text-[11px] px-2.5 py-1 rounded-md cursor-pointer transition-colors flex items-center gap-1.5 export-enter"
            style={{
              background: COL.panel,
              border: `1px solid ${COL.border}`,
              color: COL.textMid,
            }}
            onClick={onExport}
            aria-label="Copy results to clipboard"
            data-tooltip="Copy results to clipboard"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            Export
          </button>
        )}

        {/* Reset icon button */}
        <button
          className="w-7 h-7 flex items-center justify-center rounded-md btn-press"
          style={{
            color: COL.textDim,
            border: `1px solid ${COL.border}`,
            background: "transparent",
          }}
          onClick={onReset}
          aria-label="Reset all inputs"
          data-tooltip="Reset all inputs"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M1 4v6h6" />
            <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
          </svg>
        </button>

        {/* Run Prediction button */}
        <button
          className={`px-4 py-1.5 rounded-lg text-[11px] font-semibold ${predicting ? "btn-shimmer" : "btn-press"}`}
          style={{
            background: modelsReady && !predicting ? COL.accent : "rgba(255,255,255,0.06)",
            color: modelsReady && !predicting ? "#fff" : COL.textDim,
            cursor: modelsReady && !predicting ? "pointer" : "not-allowed",
            border: `1px solid ${modelsReady && !predicting ? "rgba(99,102,241,0.3)" : COL.border}`,
            boxShadow: modelsReady && !predicting ? "0 0 20px -5px rgba(99,102,241,0.3)" : "none",
          }}
          onClick={onPredict}
          disabled={!modelsReady || predicting}
        >
          {predicting ? "•••" : <>Save <span className="text-[9px] opacity-50 ml-1">Enter</span></>}
        </button>
      </div>

      <div className="flex items-center gap-2 text-[11px] max-w-[260px] overflow-hidden" style={{ color: COL.textDim }}>
        <span className={`text-sm shrink-0 ${dotClass}`} style={{ color: dotColor }} data-tooltip={dotLabel}>&#x25CF;</span>
        <span className="truncate">
          {status.startsWith("Error:") ? status.slice(0, 50) + (status.length > 50 ? "…" : "") : status}
        </span>
      </div>

      <span
        className="text-[8px] tabular-nums select-all ml-1"
        style={{ color: COL.textDim, opacity: 0.4 }}
        title={`Build: ${__BUILD_TIMESTAMP__} (${__BUILD_HASH__})`}
      >
        {__BUILD_HASH__}
      </span>
    </header>
  );
}
