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
}

export function NumberInput({ label, value, onChange, unit, step = 1, min, max, tooltip }: Props) {
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

  return (
    <div className="flex items-center gap-2 py-0.5 group" data-tooltip={tooltip}>
      <label className="text-[11px] flex-1 min-w-0 truncate" style={{ color: COL.textMid }}>
        {label}
      </label>
      <div
        className="flex items-center rounded-md overflow-hidden transition-all duration-150"
        style={{
          border: `1px solid ${isOutOfRange ? COL.danger : COL.border}`,
          background: COL.panel,
        }}
      >
        <button
          className="w-6 h-7 flex items-center justify-center text-sm select-none stepper-btn"
          style={{ color: COL.textDim, borderRight: `1px solid ${COL.border}` }}
          onMouseDown={() => startRepeat(-step)}
          onMouseUp={stopRepeat}
          onMouseLeave={stopRepeat}
          tabIndex={-1}
        >
          −
        </button>
        <input
          type="number"
          className="w-16 text-[11px] text-center py-1.5 outline-none tabular-nums"
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
          className="w-6 h-7 flex items-center justify-center text-sm select-none stepper-btn"
          style={{ color: COL.textDim, borderLeft: `1px solid ${COL.border}` }}
          onMouseDown={() => startRepeat(step)}
          onMouseUp={stopRepeat}
          onMouseLeave={stopRepeat}
          tabIndex={-1}
        >
          +
        </button>
      </div>
      {unit && <span className="text-[10px] w-9 text-right" style={{ color: COL.textDim }}>{unit}</span>}
    </div>
  );
}
