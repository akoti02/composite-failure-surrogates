import { COL, DEFECT_COLORS, TOOLTIPS } from "../lib/constants";
import { VerdictCard } from "./VerdictCard";
import type { PredictionResults } from "../lib/types";

interface Props {
  results: PredictionResults | null;
  nDefects: number;
  onExpandModal?: () => void;
}

function SectionHeader({ text, tooltip }: { text: string; tooltip?: string }) {
  return (
    <div className="pt-4 pb-1.5 px-1">
      <div
        className="text-[10px] font-semibold tracking-[0.06em] uppercase"
        style={{ color: COL.textDim }}
        data-tooltip={tooltip}
      >
        {text}
      </div>
    </div>
  );
}

function ResultRow({ label, value, color, subtext, tooltip, delay = 0 }: {
  label: string; value: string; color: string; subtext?: string; tooltip?: string; delay?: number;
}) {
  return (
    <div
      className="selectable result-row flex items-center h-8 px-3 rounded-lg row-reveal"
      style={{
        background: COL.card,
        border: `1px solid ${COL.border}`,
        animationDelay: `${delay}ms`,
      }}
      data-tooltip={tooltip}
    >
      <span className="text-[11px] flex-1" style={{ color: COL.textMid }}>{label}</span>
      {subtext && <span className="text-[9px] mr-2" style={{ color: COL.textDim }}>{subtext}</span>}
      <span className="text-[11px] font-semibold tabular-nums" style={{ color }}>{value}</span>
    </div>
  );
}

function GaugeRow({ label, value, formattedValue, color, threshold = 1.0, tooltip, delay = 0 }: {
  label: string; value: number; formattedValue: string; color: string;
  threshold?: number; tooltip?: string; delay?: number;
}) {
  const ratio = Math.min(value / (threshold * 1.5), 1);
  const exceeded = value >= threshold;
  const pct = Math.round((value / threshold) * 100);
  const subtext = value > 0 ? (exceeded ? "Exceeded" : `${pct}%`) : "";

  return (
    <div
      className="selectable result-row flex items-center gap-2.5 h-9 px-3 rounded-lg row-reveal"
      style={{
        background: exceeded ? "rgba(248,113,113,0.03)" : COL.card,
        border: `1px solid ${exceeded ? "rgba(248,113,113,0.12)" : COL.border}`,
        animationDelay: `${delay}ms`,
      }}
      data-tooltip={tooltip}
    >
      <span className="text-[11px] w-28 shrink-0" style={{ color: COL.textMid }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full relative" style={{ background: "rgba(255,255,255,0.05)" }}>
        <div
          className="h-full rounded-full gauge-fill"
          style={{ width: `${ratio * 100}%`, background: color, animationDelay: `${delay + 100}ms` }}
        />
        <div
          className="absolute top-[-2px] bottom-[-2px] w-px"
          style={{ left: `${(threshold / (threshold * 1.5)) * 100}%`, background: "rgba(255,255,255,0.2)" }}
        />
      </div>
      <span className="text-[9px] w-16 text-right" style={{ color: COL.textDim }}>{subtext}</span>
      <span className="text-[11px] font-semibold tabular-nums w-14 text-right" style={{ color }}>
        {formattedValue}
      </span>
    </div>
  );
}

function DefectBar({ index, value, maxValue, active, delay }: {
  index: number; value?: number; maxValue: number; active: boolean; delay: number;
}) {
  const hasValue = value != null && isFinite(value) && active;
  const ratio = hasValue ? Math.min(value / Math.max(maxValue, 1), 1) : 0;
  const formatted = hasValue
    ? `${value.toLocaleString("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MPa`
    : "--";

  return (
    <div
      className="flex items-center gap-2.5 h-8 px-3 rounded-lg row-reveal result-row"
      style={{
        background: COL.card,
        border: `1px solid ${COL.border}`,
        animationDelay: `${delay}ms`,
        opacity: active ? 1 : 0.3,
      }}
    >
      <span className="text-[10px]" style={{ color: active ? DEFECT_COLORS[index] : COL.textDim }}>&#x25CF;</span>
      <span className="text-[11px] w-12 shrink-0" style={{ color: COL.textMid }}>#{index + 1}</span>
      <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.04)" }}>
        {hasValue && (
          <div
            className="h-full rounded-full gauge-fill"
            style={{
              width: `${ratio * 100}%`,
              background: DEFECT_COLORS[index],
              animationDelay: `${delay + 100}ms`,
            }}
          />
        )}
      </div>
      <span className="text-[11px] font-semibold tabular-nums w-20 text-right" style={{ color: active ? COL.text : COL.textDim }}>
        {formatted}
      </span>
    </div>
  );
}

function fmtStress(val?: number): { value: string; color: string; subtext?: string } {
  if (val == null || !isFinite(val)) return { value: "--", color: COL.textDim };
  return {
    value: `${val.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} MPa`,
    color: COL.text,
  };
}

function fmtIndex(val?: number, threshold = 1.0): { value: number; formatted: string; color: string } {
  if (val == null || !isFinite(val)) return { value: 0, formatted: "--", color: COL.textDim };
  const color = val >= threshold ? COL.danger : val >= threshold * 0.8 ? COL.warning : COL.success;
  return { value: val, formatted: val.toFixed(4), color };
}

function fmtBool(val?: number): { value: string; color: string } {
  if (val == null) return { value: "--", color: COL.textDim };
  return val === 0
    ? { value: "PASS", color: COL.success }
    : { value: "FAIL", color: COL.danger };
}

export function ResultsPanel({ results, nDefects, onExpandModal }: Props) {
  const r = results;

  let maxDefectStress = 0;
  for (let i = 1; i <= nDefects; i++) {
    const key = `max_mises_defect${i}` as keyof PredictionResults;
    const v = r?.[key] as number | undefined;
    if (v != null && isFinite(v) && v > maxDefectStress) maxDefectStress = v;
  }

  const hft = fmtIndex(r?.max_hashin_ft);
  const hfc = fmtIndex(r?.max_hashin_fc);
  const hmt = fmtIndex(r?.max_hashin_mt);
  const hmc = fmtIndex(r?.max_hashin_mc);

  // Use a key that changes when results arrive to re-trigger entrance animations
  const animKey = r ? `r-${r.max_mises}-${r.tsai_wu_index}` : "empty";

  return (
    <div className="overflow-y-auto px-4 py-3 flex flex-col gap-1">
      <div className="flex items-center justify-between mb-1">
        <VerdictCard results={results} />
        {onExpandModal && results && (
          <button
            className="w-6 h-6 flex items-center justify-center rounded-md btn-press shrink-0 ml-2"
            style={{ color: COL.textDim, border: `1px solid ${COL.border}` }}
            onClick={onExpandModal}
            data-tooltip="Expand results"
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            </svg>
          </button>
        )}
      </div>

      {!results && (
        <div className="flex-1 flex flex-col items-center justify-center py-16 opacity-40">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke={COL.textDim} strokeWidth="1" strokeLinecap="round">
            <path d="M3 3v18h18" />
            <path d="M7 16l4-6 4 4 5-8" />
          </svg>
          <span className="text-[11px] mt-3" style={{ color: COL.textDim }}>Run a prediction to see results</span>
        </div>
      )}

      {results && (
        <div key={animKey} className="flex flex-col gap-1">
          <SectionHeader text="Stress Analysis" tooltip={TOOLTIPS.mises} />
          <div className="flex flex-col gap-1">
            <ResultRow label="Peak Stress (von Mises)" {...fmtStress(r?.max_mises)} tooltip="Combined equivalent stress" delay={0} />
            <ResultRow label="Max Fibre Stress (S11)" {...fmtStress(r?.max_s11)} tooltip="Maximum stress in fibre direction" delay={40} />
            <ResultRow label="Min Fibre Stress (S11)" {...fmtStress(r?.min_s11)} tooltip="Minimum stress (compression)" delay={80} />
            <ResultRow label="Peak Shear (S12)" {...fmtStress(r?.max_s12)} tooltip="Maximum in-plane shear stress" delay={120} />
          </div>

          <SectionHeader text="Failure Assessment" tooltip={TOOLTIPS.tsai_wu} />
          <div className="flex flex-col gap-1">
            <ResultRow label="Tsai-Wu Verdict" {...fmtBool(r?.failed_tsai_wu)} delay={0} />
          </div>

          <SectionHeader text="Damage Modes (Hashin)" tooltip={TOOLTIPS.hashin} />
          <div className="flex flex-col gap-1">
            <GaugeRow label="Fibre Tension" value={hft.value} formattedValue={hft.formatted} color={hft.color} tooltip="Fibre tensile failure index" delay={0} />
            <GaugeRow label="Fibre Compression" value={hfc.value} formattedValue={hfc.formatted} color={hfc.color} tooltip="Fibre compressive failure index" delay={40} />
            <GaugeRow label="Matrix Tension" value={hmt.value} formattedValue={hmt.formatted} color={hmt.color} tooltip="Matrix tensile failure index" delay={80} />
            <GaugeRow label="Matrix Compression" value={hmc.value} formattedValue={hmc.formatted} color={hmc.color} tooltip="Matrix compressive failure index" delay={120} />
            <ResultRow label="Hashin Verdict" {...fmtBool(r?.failed_hashin)} delay={160} />
          </div>

          <SectionHeader text="Per-Defect Peak Stress" />
          <div className="flex flex-col gap-1">
            {Array.from({ length: nDefects }, (_, i) => {
              const key = `max_mises_defect${i + 1}` as keyof PredictionResults;
              return (
                <DefectBar
                  key={i}
                  index={i}
                  value={r?.[key] as number | undefined}
                  maxValue={maxDefectStress}
                  active={true}
                  delay={i * 40}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
