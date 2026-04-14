import { useEffect, useRef, useState } from "react";
import { COL } from "../lib/constants";
import type { PredictionResults, VerdictLevel } from "../lib/types";
import { useT } from "../lib/i18n";

function useVerdict(results: PredictionResults | null): { level: VerdictLevel; title: string; desc: string } {
  const t = useT();
  if (!results) return { level: "awaiting", title: t("verdict_initialising"), desc: t("verdict_initialising_desc") };

  const tw = results.tsai_wu_index ?? 0;
  const ftw = results.failed_tsai_wu ?? 0;
  const fh = results.failed_hashin ?? 0;
  const fp = results.failed_puck ?? 0;
  const fl = results.failed_larc ?? 0;
  const isFailed = ftw === 1 || fh === 1 || fp === 1 || fl === 1 || tw >= 1.0;
  const isWarning = !isFailed && tw >= 0.8;

  if (isFailed) {
    const modes: string[] = [];
    if (ftw === 1) modes.push("Tsai-Wu");
    if (fh === 1) modes.push("Hashin");
    if (fp === 1) modes.push("Puck");
    if (fl === 1) modes.push("LaRC");
    return {
      level: "failure",
      title: t("verdict_failure"),
      desc: modes.length ? `${t("verdict_failed")}: ${modes.join(" & ")}` : t("verdict_tsai_exceeds", { v: tw.toFixed(2) }),
    };
  }
  if (isWarning) {
    const pct = Math.round(tw * 100);
    return {
      level: "caution",
      title: t("verdict_caution"),
      desc: t("verdict_caution_desc", { pct, m: Math.round((1 - tw) * 100) }),
    };
  }
  const pct = Math.round(tw * 100);
  return {
    level: "safe",
    title: t("verdict_safe"),
    desc: t("verdict_safe_desc", { m: 100 - pct }),
  };
}

const VERDICT_CFG: Record<VerdictLevel, {
  bg: string; border: string; glow: string;
  color: string; descColor: string; pulseClass: string;
}> = {
  awaiting: {
    bg: COL.card, border: COL.border, glow: "none",
    color: COL.textDim, descColor: COL.textDim, pulseClass: "",
  },
  safe: {
    bg: COL.safeBg, border: "rgba(94, 255, 176, 0.28)",
    glow: "0 0 26px -5px rgba(94, 255, 176, 0.45)",
    color: COL.success, descColor: "#b7ffd7", pulseClass: "",
  },
  caution: {
    bg: COL.warnBg, border: "rgba(255, 216, 77, 0.32)",
    glow: "none",
    color: COL.warning, descColor: "#ffebb0", pulseClass: "verdict-warn-pulse",
  },
  failure: {
    bg: COL.critBg, border: "rgba(255, 94, 135, 0.32)",
    glow: "none",
    color: COL.danger, descColor: "#ffc2d2", pulseClass: "verdict-fail-pulse",
  },
};

function AnimatedIcon({ level, color }: { level: VerdictLevel; color: string }) {
  const [drawn, setDrawn] = useState(false);
  const prevLevel = useRef(level);

  useEffect(() => {
    if (level !== prevLevel.current) {
      setDrawn(false);
      prevLevel.current = level;
      requestAnimationFrame(() => setDrawn(true));
    } else {
      setDrawn(true);
    }
  }, [level]);

  const circleLen = 2 * Math.PI * 11;

  const glowFilter = `drop-shadow(0 0 4px ${color}88)`;

  if (level === "awaiting") {
    return (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" opacity="0.35">
        <circle cx="12" cy="12" r="11" stroke={color} strokeWidth="1.5" strokeDasharray="4 3" />
        <line x1="12" y1="8" x2="12" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
        <line x1="12" y1="12" x2="15" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }

  if (level === "safe") {
    return (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" style={{ filter: glowFilter }}>
        <circle cx="12" cy="12" r="11" stroke={color} strokeWidth="1.5"
          style={{
            strokeDasharray: circleLen,
            strokeDashoffset: drawn ? 0 : circleLen,
            transition: "stroke-dashoffset 0.4s cubic-bezier(0.65, 0, 0.45, 1)",
          }}
        />
        <polyline points="8,12 11,15 16,9" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          style={{
            strokeDasharray: 20,
            strokeDashoffset: drawn ? 0 : 20,
            transition: "stroke-dashoffset 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.35s",
          }}
        />
      </svg>
    );
  }

  if (level === "caution") {
    return (
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" style={{ filter: glowFilter }}>
        <path d="M12 2L22 20H2L12 2Z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"
          fill={color} fillOpacity="0.12"
          style={{
            strokeDasharray: 60,
            strokeDashoffset: drawn ? 0 : 60,
            transition: "stroke-dashoffset 0.4s cubic-bezier(0.65, 0, 0.45, 1)",
          }}
        />
        <line x1="12" y1="9" x2="12" y2="14" stroke={color} strokeWidth="2" strokeLinecap="round"
          style={{ opacity: drawn ? 1 : 0, transition: "opacity 0.2s ease 0.35s" }}
        />
        <circle cx="12" cy="17" r="1" fill={color}
          style={{ opacity: drawn ? 1 : 0, transition: "opacity 0.2s ease 0.4s" }}
        />
      </svg>
    );
  }

  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" className={drawn ? "shake" : ""} style={{ filter: glowFilter }}>
      <circle cx="12" cy="12" r="11" stroke={color} strokeWidth="1.5"
        fill={color} fillOpacity="0.08"
        style={{
          strokeDasharray: circleLen,
          strokeDashoffset: drawn ? 0 : circleLen,
          transition: "stroke-dashoffset 0.4s cubic-bezier(0.65, 0, 0.45, 1)",
        }}
      />
      <line x1="9" y1="9" x2="15" y2="15" stroke={color} strokeWidth="2" strokeLinecap="round"
        style={{
          strokeDasharray: 10,
          strokeDashoffset: drawn ? 0 : 10,
          transition: "stroke-dashoffset 0.25s cubic-bezier(0.65, 0, 0.45, 1) 0.3s",
        }}
      />
      <line x1="15" y1="9" x2="9" y2="15" stroke={color} strokeWidth="2" strokeLinecap="round"
        style={{
          strokeDasharray: 10,
          strokeDashoffset: drawn ? 0 : 10,
          transition: "stroke-dashoffset 0.25s cubic-bezier(0.65, 0, 0.45, 1) 0.4s",
        }}
      />
    </svg>
  );
}

function TsaiWuGauge({ value }: { value: number }) {
  const t = useT();
  const maxDisplay = 1.5;
  const ratio = Math.min(value / maxDisplay, 1);
  const thresholdPos = (1.0 / maxDisplay) * 100;
  const color = value >= 1.0 ? COL.danger : value >= 0.8 ? COL.warning : COL.success;
  const label = value >= 1.0 ? t("exceeded") : t("pct_of_limit", { pct: Math.round(value * 100) });

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[12px]" style={{ color: COL.textMid }}>{t("tsai_wu_index")}</span>
        <div className="flex items-center gap-2">
          <span className="text-[11px]" style={{ color: COL.textDim }}>{label}</span>
          <span className="text-[14px] font-bold tabular-nums" style={{ color, textShadow: `0 0 6px ${color}88` }}>{value.toFixed(3)}</span>
        </div>
      </div>
      <div className="relative h-2.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-full rounded-full gauge-fill"
          style={{ width: `${ratio * 100}%`, background: color, boxShadow: `0 0 8px ${color}aa` }}
        />
        <div
          className="absolute top-[-3px] bottom-[-3px] w-[2px] rounded-full"
          style={{ left: `${thresholdPos}%`, background: "rgba(255,255,255,0.55)" }}
        />
        <span
          className="absolute text-[9px]"
          style={{ left: `${thresholdPos}%`, top: -14, transform: "translateX(-50%)", color: COL.textDim }}
        >
          {t("limit")}
        </span>
      </div>
    </div>
  );
}

export function VerdictCard({ results }: { results: PredictionResults | null }) {
  const { level, title, desc } = useVerdict(results);
  const c = VERDICT_CFG[level];
  const tw = results?.tsai_wu_index ?? 0;

  return (
    <div
      className={`rounded-xl p-4 verdict-animate ${c.pulseClass} ${level === "safe" ? "verdict-safe-glow" : ""}`}
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        boxShadow: c.pulseClass || level === "safe" ? undefined : c.glow,
      }}
    >
      <div className="flex items-center gap-3">
        <AnimatedIcon level={level} color={c.color} />
        <div className="flex-1 min-w-0">
          <div className="text-[15px] font-bold tracking-wide" style={{ color: c.color, textShadow: level !== "awaiting" ? `0 0 8px ${c.color}77` : undefined }}>{title}</div>
          <div className="text-[12px] mt-0.5" style={{ color: c.descColor }}>{desc}</div>
        </div>
      </div>
      {results && <TsaiWuGauge value={tw} />}
    </div>
  );
}
