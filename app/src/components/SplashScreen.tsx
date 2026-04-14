import { useState, useEffect } from "react";
import { COL } from "../lib/constants";
import { useT } from "../lib/i18n";
import type { TKey } from "../lib/i18n";

const STAGE_KEYS: TKey[] = [
  "splash_stage_init",
  "splash_stage_nn",
  "splash_stage_xgb",
  "splash_stage_cal",
];

export function SplashScreen({ onReady }: { onReady?: boolean }) {
  const t = useT();
  const [stageIdx, setStageIdx] = useState(0);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setStageIdx((prev) => (prev + 1) % STAGE_KEYS.length);
    }, 900);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (onReady) {
      setExiting(true);
    }
  }, [onReady]);

  const [hidden, setHidden] = useState(false);
  if (hidden) return null;

  return (
    <div
      className={`fixed inset-0 flex flex-col items-center justify-center z-50 ${exiting ? "splash-exit" : ""}`}
      style={{ background: COL.bgDark }}
      onAnimationEnd={(e) => {
        if (e.animationName === "splashFadeOut") setHidden(true);
      }}
    >
      {/* Luminescent radial glow */}
      <div
        className="absolute inset-0"
        style={{
          background: "radial-gradient(circle at 50% 40%, rgba(0,234,255,0.12) 0%, transparent 60%), radial-gradient(circle at 50% 70%, rgba(183,148,255,0.08) 0%, transparent 60%)",
        }}
      />

      <div className="relative z-10 flex flex-col items-center">
        <div className="text-5xl font-bold tracking-tight mb-1 text-glow-cyan" style={{ color: COL.accent }}>
          RP3
        </div>
        <div className="text-base mb-1" style={{ color: COL.textMid }}>
          {t("app_title")}
        </div>
        <div className="text-[12px] mb-8" style={{ color: COL.textDim }}>
          {t("app_subtitle")}
        </div>

        {/* Loading bar */}
        <div
          className="w-56 h-1.5 rounded-full overflow-hidden"
          style={{ background: "rgba(255,255,255,0.08)" }}
        >
          <div
            className="h-full w-full rounded-full splash-bar"
            style={{
              background: `linear-gradient(90deg, transparent, ${COL.accent}, transparent)`,
              boxShadow: "0 0 10px rgba(0, 234, 255, 0.7)",
            }}
          />
        </div>

        <div className="text-[13px] mt-4 transition-opacity duration-300" style={{ color: COL.textMid }}>
          {t(STAGE_KEYS[stageIdx])}
        </div>
      </div>
    </div>
  );
}
