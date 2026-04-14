import { COL } from "../lib/constants";
import { VerdictCard } from "./VerdictCard";
import type { PredictionResults } from "../lib/types";
import { useT, useLang } from "../lib/i18n";

interface Props {
  results: PredictionResults | null;
  nDefects: number;
  onExpandModal?: () => void;
}

function SectionHeader({ text, tooltip }: { text: string; tooltip?: string }) {
  return (
    <div className="pt-4 pb-1.5 px-1">
      <div
        className="text-[11px] font-bold tracking-[0.1em] uppercase text-glow-cyan"
        style={{ color: COL.accent, opacity: 0.95 }}
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
      className="selectable result-row flex items-center h-9 px-3 rounded-lg row-reveal"
      style={{
        background: COL.card,
        border: `1px solid ${COL.border}`,
        animationDelay: `${delay}ms`,
      }}
      data-tooltip={tooltip}
    >
      <span className="text-[13px] flex-1" style={{ color: COL.textMid }}>{label}</span>
      {subtext && <span className="text-[10px] mr-2" style={{ color: COL.textDim }}>{subtext}</span>}
      <span className="text-[14px] font-semibold tabular-nums" style={{ color, textShadow: color !== COL.text ? `0 0 6px ${color}88` : undefined }}>{value}</span>
    </div>
  );
}

function GaugeRow({ label, value, formattedValue, color, threshold = 1.0, tooltip, delay = 0 }: {
  label: string; value: number; formattedValue: string; color: string;
  threshold?: number; tooltip?: string; delay?: number;
}) {
  const t = useT();
  const ratio = Math.min(value / (threshold * 1.5), 1);
  const exceeded = value >= threshold;
  const pct = Math.round((value / threshold) * 100);
  const subtext = value > 0 ? (exceeded ? t("exceeded") : `${pct}%`) : "";

  return (
    <div
      className="selectable result-row flex items-center gap-2.5 h-10 px-3 rounded-lg row-reveal"
      style={{
        background: exceeded ? COL.dangerMuted : COL.card,
        border: `1px solid ${exceeded ? "rgba(255,94,135,0.25)" : COL.border}`,
        animationDelay: `${delay}ms`,
        boxShadow: exceeded ? "0 0 10px rgba(255,94,135,0.15)" : undefined,
      }}
      data-tooltip={tooltip}
    >
      <span className="text-[13px] w-32 shrink-0" style={{ color: COL.textMid }}>{label}</span>
      <div className="flex-1 h-2 rounded-full relative" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-full rounded-full gauge-fill"
          style={{ width: `${ratio * 100}%`, background: color, animationDelay: `${delay + 100}ms`, boxShadow: `0 0 8px ${color}88` }}
        />
        <div
          className="absolute top-[-2px] bottom-[-2px] w-px"
          style={{ left: `${(threshold / (threshold * 1.5)) * 100}%`, background: "rgba(255,255,255,0.4)" }}
        />
      </div>
      <span className="text-[10px] w-16 text-right" style={{ color: COL.textDim }}>{subtext}</span>
      <span className="text-[14px] font-semibold tabular-nums w-14 text-right" style={{ color, textShadow: `0 0 6px ${color}66` }}>
        {formattedValue}
      </span>
    </div>
  );
}

function useFmt() {
  const { lang } = useLang();
  const t = useT();
  const localeTag = lang === "ru" ? "ru-RU" : "en-GB";

  return {
    fmtStress: (val?: number) => {
      if (val == null || !isFinite(val)) return { value: "--", color: COL.textDim };
      return {
        value: `${val.toLocaleString(localeTag, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${t("unit_mpa")}`,
        color: COL.text,
      };
    },
    fmtIndex: (val?: number, threshold = 1.0) => {
      if (val == null || !isFinite(val)) return { value: 0, formatted: "--", color: COL.textDim };
      const color = val >= threshold ? COL.danger : val >= threshold * 0.8 ? COL.warning : COL.success;
      return { value: val, formatted: val.toFixed(4), color };
    },
    fmtBool: (val?: number) => {
      if (val == null) return { value: "--", color: COL.textDim };
      return val === 0
        ? { value: t("pass"), color: COL.success }
        : { value: t("fail"), color: COL.danger };
    },
  };
}

export function ResultsPanel({ results, nDefects: _nDefects, onExpandModal }: Props) {
  const t = useT();
  const { fmtStress, fmtIndex, fmtBool } = useFmt();
  const r = results;

  const hft = fmtIndex(r?.max_hashin_ft);
  const hmt = fmtIndex(r?.max_hashin_mt);
  const hmc = fmtIndex(r?.max_hashin_mc);

  const animKey = r ? `r-${r.tsai_wu_index}-${r.max_s11}` : "empty";

  return (
    <div className="overflow-y-auto px-4 py-3 flex flex-col gap-1">
      <div className="flex items-center justify-between mb-1">
        <VerdictCard results={results} />
        {onExpandModal && results && (
          <button
            className="w-7 h-7 flex items-center justify-center rounded-md btn-press shrink-0 ml-2"
            style={{ color: COL.textDim, border: `1px solid ${COL.border}` }}
            onClick={onExpandModal}
            data-tooltip={t("expand_results")}
            aria-label={t("expand_results")}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
            </svg>
          </button>
        )}
      </div>

      {!results && (
        <div className="flex-1 flex flex-col items-center justify-center py-16 opacity-50">
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke={COL.accent} strokeWidth="1" strokeLinecap="round" style={{ filter: "drop-shadow(0 0 8px rgba(0,234,255,0.35))" }}>
            <path d="M3 3v18h18" />
            <path d="M7 16l4-6 4 4 5-8" />
          </svg>
          <span className="text-[13px] mt-3" style={{ color: COL.textMid }}>{t("awaiting_results")}</span>
        </div>
      )}

      {results && (
        <div key={animKey} className="flex flex-col gap-1">
          <SectionHeader text={t("section_stress")} tooltip={t("tip_s11")} />
          <div className="flex flex-col gap-1">
            <ResultRow label={t("max_fibre_stress")} {...fmtStress(r?.max_s11)} tooltip={t("tip_max_s11_row")} delay={0} />
            <ResultRow label={t("min_fibre_stress")} {...fmtStress(r?.min_s11)} tooltip={t("tip_min_s11_row")} delay={40} />
            <ResultRow label={t("peak_shear")} {...fmtStress(r?.max_s12)} tooltip={t("tip_max_s12_row")} delay={80} />
          </div>

          <SectionHeader text={t("section_failure")} tooltip={t("tip_tsai_wu")} />
          <div className="flex flex-col gap-1">
            <ResultRow label={t("tsai_wu_verdict")} {...fmtBool(r?.failed_tsai_wu)} delay={0} />
            <ResultRow label={t("hashin_verdict")} {...fmtBool(r?.failed_hashin)} delay={40} />
            <ResultRow label={t("puck_verdict")} {...fmtBool(r?.failed_puck)} tooltip={t("tip_puck_verdict")} delay={80} />
            <ResultRow label={t("larc_verdict")} {...fmtBool(r?.failed_larc)} tooltip={t("tip_larc_verdict")} delay={120} />
          </div>

          <SectionHeader text={t("section_damage")} tooltip={t("tip_hashin")} />
          <div className="flex flex-col gap-1">
            <GaugeRow label={t("fibre_tension")} value={hft.value} formattedValue={hft.formatted} color={hft.color} tooltip={t("tip_hashin_ft_idx")} delay={0} />
            <GaugeRow label={t("matrix_tension")} value={hmt.value} formattedValue={hmt.formatted} color={hmt.color} tooltip={t("tip_hashin_mt_idx")} delay={40} />
            <GaugeRow label={t("matrix_compression")} value={hmc.value} formattedValue={hmc.formatted} color={hmc.color} tooltip={t("tip_hashin_mc_idx")} delay={80} />
          </div>
        </div>
      )}
    </div>
  );
}
