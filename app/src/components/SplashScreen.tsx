import { useState, useEffect } from "react";
import { COL } from "../lib/constants";

const STAGES = [
  "Initializing engine...",
  "Loading neural networks...",
  "Preparing XGBoost models...",
  "Calibrating inference...",
];

export function SplashScreen({ onReady }: { onReady?: boolean }) {
  const [stageIdx, setStageIdx] = useState(0);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setStageIdx((prev) => (prev + 1) % STAGES.length);
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
      {/* Subtle radial glow */}
      <div
        className="absolute inset-0"
        style={{
          background: "radial-gradient(circle at 50% 40%, rgba(99,102,241,0.06) 0%, transparent 60%)",
        }}
      />

      <div className="relative z-10 flex flex-col items-center">
        <div className="text-4xl font-bold tracking-tight mb-1" style={{ color: COL.accent }}>
          RP3
        </div>
        <div className="text-sm mb-1" style={{ color: COL.textMid }}>
          Composite Failure Surrogate
        </div>
        <div className="text-[10px] mb-8" style={{ color: COL.textDim }}>
          University of Bristol
        </div>

        {/* Loading bar */}
        <div
          className="w-52 h-1 rounded-full overflow-hidden"
          style={{ background: "rgba(255,255,255,0.06)" }}
        >
          <div
            className="h-full w-full rounded-full splash-bar"
            style={{
              background: `linear-gradient(90deg, transparent, ${COL.accent}, transparent)`,
            }}
          />
        </div>

        <div className="text-[11px] mt-4 transition-opacity duration-300" style={{ color: COL.textDim }}>
          {STAGES[stageIdx]}
        </div>
      </div>
    </div>
  );
}
