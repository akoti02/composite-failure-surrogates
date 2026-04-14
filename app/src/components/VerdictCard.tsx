import { useEffect, useRef, useState } from "react";
import { COL } from "../lib/constants";
import type { PredictionResults, VerdictLevel } from "../lib/types";

function getVerdict(results: PredictionResults | null): { level: VerdictLevel; title: string; desc: string } {
  if (!results) return { level: "awaiting", title: "Initialising...", desc: "Predictions update live as you change inputs" };

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
      title: "FAILURE PREDICTED",
      desc: modes.length ? `Failed: ${modes.join(" & ")}` : `Tsai-Wu index ${tw.toFixed(2)} exceeds limit`,
    };
  }
  if (isWarning) {
    const pct = Math.round(tw * 100);
    return {
      level: "caution",
      title: "CAUTION",
      desc: `At ${pct}% of failure threshold — ${Math.round((1 - tw) * 100)}% margin remaining`,
    };
  }
  const pct = Math.round(tw * 100);
  return {
    level: "safe",
    title: "SAFE",
    desc: `${100 - pct}% margin of safety remaining`,
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
    bg: "rgba(52, 211, 153, 0.05)", border: "rgba(52, 211, 153, 0.15)",
    glow: "0 0 30px -8px rgba(52, 211, 153, 0.2)",
    color: COL.success, descColor: "#86efac", pulseClass: "",
  },
  caution: {
    bg: "rgba(251, 191, 36, 0.05)", border: "rgba(251, 191, 36, 0.15)",
    glow: "none",
    color: COL.warning, descColor: "#fde68a", pulseClass: "verdict-warn-pulse",
  },
  failure: {
    bg: "rgba(248, 113, 113, 0.05)", border: "rgba(248, 113, 113, 0.15)",
    glow: "none",
    color: COL.danger, descColor: "#fca5a5", pulseClass: "verdict-fail-pulse",
  },
};

// Animated SVG icons that draw themselves
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

  const circleLen = 2 * Math.PI * 11; // r=11

  if (level === "awaiting") {
    return (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" opacity="0.3">
        <circle cx="12" cy="12" r="11" stroke={color} strokeWidth="1.5" strokeDasharray="4 3" />
        <line x1="12" y1="8" x2="12" y2="12" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
        <line x1="12" y1="12" x2="15" y2="14" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }

  if (level === "safe") {
    return (
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
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
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L22 20H2L12 2Z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"
          fill={color} fillOpacity="0.08"
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

  // failure
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" className={drawn ? "shake" : ""}>
      <circle cx="12" cy="12" r="11" stroke={color} strokeWidth="1.5"
        fill={color} fillOpacity="0.06"
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
  const maxDisplay = 1.5;
  const ratio = Math.min(value / maxDisplay, 1);
  const thresholdPos = (1.0 / maxDisplay) * 100;
  const color = value >= 1.0 ? COL.danger : value >= 0.8 ? COL.warning : COL.success;
  const pct = Math.round(value * 100);
  const label = value >= 1.0 ? "Exceeded" : `${pct}% of limit`;

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px]" style={{ color: COL.textMid }}>Tsai-Wu Index</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px]" style={{ color: COL.textDim }}>{label}</span>
          <span className="text-xs font-bold tabular-nums" style={{ color }}>{value.toFixed(3)}</span>
        </div>
      </div>
      <div className="relative h-2 rounded-full" style={{ background: "rgba(255,255,255,0.05)" }}>
        <div
          className="h-full rounded-full gauge-fill"
          style={{ width: `${ratio * 100}%`, background: color }}
        />
        <div
          className="absolute top-[-3px] bottom-[-3px] w-[2px] rounded-full"
          style={{ left: `${thresholdPos}%`, background: "rgba(255,255,255,0.4)" }}
        />
        <span
          className="absolute text-[8px]"
          style={{ left: `${thresholdPos}%`, top: -14, transform: "translateX(-50%)", color: COL.textDim }}
        >
          limit
        </span>
      </div>
    </div>
  );
}

export function VerdictCard({ results }: { results: PredictionResults | null }) {
  const { level, title, desc } = getVerdict(results);
  const c = VERDICT_CFG[level];
  const tw = results?.tsai_wu_index ?? 0;

  return (
    <div
      className={`rounded-xl p-4 verdict-animate ${c.pulseClass}`}
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        boxShadow: c.pulseClass ? undefined : c.glow,
      }}
    >
      <div className="flex items-center gap-3">
        <AnimatedIcon level={level} color={c.color} />
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-bold tracking-wide" style={{ color: c.color }}>{title}</div>
          <div className="text-[11px] mt-0.5" style={{ color: c.descColor }}>{desc}</div>
        </div>
      </div>
      {results && <TsaiWuGauge value={tw} />}
    </div>
  );
}
