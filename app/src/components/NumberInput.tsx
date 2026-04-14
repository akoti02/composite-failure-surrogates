import { useRef, useCallback } from "react";
import { COL } from "../lib/constants";

interface Props {
  label: string;
  value: number;
  onChange: (v: number) => void;
  unit?: string;
  step?: number;
  min?: number;
  max?: number;
  tooltip?: string;
  compact?: boolean;
}

export function NumberInput({ label, value, onChange, unit, step = 1, min, max, tooltip, compact }: Props) {
  const intervalRef = useRef<number>(0);
  const valueRef = useRef(value);
  valueRef.current = value;

  const clamp = useCallback((v: number) => {
    if (min !== undefined && v < min) v = min;
    if (max !== undefined && v > max) v = max;
    return Math.round(v * 10000) / 10000;
  }, [min, max]);

  const handleChange = (v: number) => onChange(clamp(v));

  const startRepeat = useCallback((delta: number) => {
    onChange(clamp(valueRef.current + delta));
    let speed = 180;
    const tick = () => {
      onChange(clamp(valueRef.current + delta));
      speed = Math.max(speed - 15, 40);
      intervalRef.current = window.setTimeout(tick, speed);
    };
    intervalRef.current = window.setTimeout(tick, 350);
  }, [onChange, clamp]);

  const stopRepeat = useCallback(() => {
    if (intervalRef.current) clearTimeout(intervalRef.current);
  }, []);

  const isOutOfRange = (min !== undefined && value < min) || (max !== undefined && value > max);
  const h = compact ? "h-9" : "h-10";
  const btnW = compact ? "w-9" : "w-10";
  const inputW = compact ? "w-[72px]" : "w-[88px]";
  const fontSize = compact ? "text-[13px]" : "text-[15px]";
  const labelSize = compact ? "text-[13px]" : "text-[14px]";

  return (
    <div
      className="flex items-center gap-4 px-3 py-1.5 -mx-3 rounded-lg transition-colors duration-100 hover:bg-white/[0.03]"
      data-tooltip={tooltip}
    >
      <label className={`${labelSize} flex-1 min-w-0 truncate`} style={{ color: COL.textMid }}>
        {label}
      </label>
      <div
        className="flex items-center rounded-lg overflow-hidden transition-all duration-150"
        style={{
          border: `1px solid ${isOutOfRange ? COL.danger : COL.border}`,
          background: "rgba(0,0,0,0.2)",
        }}
      >
        <button
          className={`${btnW} ${h} flex items-center justify-center text-lg select-none transition-colors duration-100 hover:bg-white/[0.06] active:bg-white/[0.1]`}
          style={{ color: COL.textMid, borderRight: `1px solid ${COL.border}` }}
          onMouseDown={() => startRepeat(-step)}
          onMouseUp={stopRepeat}
          onMouseLeave={stopRepeat}
          tabIndex={-1}
        >
          −
        </button>
        <input
          type="number"
          className={`${inputW} ${fontSize} text-center py-2 outline-none tabular-nums font-medium`}
          style={{
            background: "transparent",
            color: isOutOfRange ? COL.danger : COL.text,
            border: "none",
          }}
          value={value}
          step={step}
          min={min}
          max={max}
          onChange={(e) => handleChange(parseFloat(e.target.value) || 0)}
          onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
        />
        <button
          className={`${btnW} ${h} flex items-center justify-center text-lg select-none transition-colors duration-100 hover:bg-white/[0.06] active:bg-white/[0.1]`}
          style={{ color: COL.textMid, borderLeft: `1px solid ${COL.border}` }}
          onMouseDown={() => startRepeat(step)}
          onMouseUp={stopRepeat}
          onMouseLeave={stopRepeat}
          tabIndex={-1}
        >
          +
        </button>
      </div>
      {unit && (
        <span className="text-[12px] w-9 text-right tabular-nums" style={{ color: COL.textDim, opacity: 0.6 }}>
          {unit}
        </span>
      )}
    </div>
  );
}
