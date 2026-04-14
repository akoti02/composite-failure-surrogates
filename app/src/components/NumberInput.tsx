import { useRef, useCallback, useState, useEffect } from "react";
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

/**
 * NumberInput with a local text buffer.
 *
 * The classic pitfall with `type="number"` controlled inputs is that
 * `parseFloat("") || 0` coerces every empty state to 0 — so clearing the
 * field and typing "5" visibly briefly shows "0" and then "5", or worse,
 * "05". We fix that by keeping the displayed string in local state, only
 * committing the numeric value to the parent when the string parses to a
 * finite number. Empty / intermediate strings like "-" or "." leave the
 * parent value untouched. On blur, we snap the display back to the last
 * committed value so we never leave the field in a broken half-typed state.
 *
 * `type="text" inputMode="decimal"` mirrors a numeric keypad on touch
 * devices without invoking the browser's own (buggy) input coercion.
 */
export function NumberInput({ label, value, onChange, unit, step = 1, min, max, tooltip, compact }: Props) {
  const intervalRef = useRef<number>(0);
  const valueRef = useRef(value);
  valueRef.current = value;

  // Local display string. Starts matching the initial value; user edits
  // here; we sync from `value` when the parent changes it via a source
  // we don't own (preset restore, +/- buttons).
  const [text, setText] = useState<string>(() => String(value));

  // Keep display text in sync with parent value ONLY if the current text
  // doesn't already parse to it (so we don't clobber in-progress typing).
  useEffect(() => {
    const parsed = parseFloat(text);
    if (isNaN(parsed) || Math.abs(parsed - value) > 1e-9) {
      setText(String(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const clamp = useCallback((v: number) => {
    if (min !== undefined && v < min) v = min;
    if (max !== undefined && v > max) v = max;
    return Math.round(v * 10000) / 10000;
  }, [min, max]);

  const commit = useCallback((n: number) => {
    if (!isFinite(n)) return;
    onChange(clamp(n));
  }, [onChange, clamp]);

  const startRepeat = useCallback((delta: number) => {
    commit(valueRef.current + delta);
    let speed = 180;
    const tick = () => {
      commit(valueRef.current + delta);
      speed = Math.max(speed - 15, 40);
      intervalRef.current = window.setTimeout(tick, speed);
    };
    intervalRef.current = window.setTimeout(tick, 350);
  }, [commit]);

  const stopRepeat = useCallback(() => {
    if (intervalRef.current) clearTimeout(intervalRef.current);
  }, []);

  const isOutOfRange = (min !== undefined && value < min) || (max !== undefined && value > max);
  const h = compact ? "h-10" : "h-11";
  const btnW = compact ? "w-10" : "w-11";
  const inputW = compact ? "w-[78px]" : "w-[96px]";
  const fontSize = compact ? "text-[15px]" : "text-[17px]";
  const labelSize = compact ? "text-[14px]" : "text-[15px]";

  return (
    <div
      className="flex items-center gap-4 px-3 py-1.5 -mx-3 rounded-lg transition-colors duration-100 hover:bg-cyan-500/5"
      data-tooltip={tooltip}
    >
      <label className={`${labelSize} flex-1 min-w-0 truncate`} style={{ color: COL.textMid }}>
        {label}
      </label>
      <div
        className="flex items-center rounded-lg overflow-hidden transition-all duration-150"
        style={{
          border: `1px solid ${isOutOfRange ? COL.danger : COL.border}`,
          background: "rgba(0,0,0,0.25)",
        }}
      >
        <button
          type="button"
          className={`${btnW} ${h} flex items-center justify-center text-xl select-none stepper-btn`}
          style={{ color: COL.textMid, borderRight: `1px solid ${COL.border}` }}
          onMouseDown={() => startRepeat(-step)}
          onMouseUp={stopRepeat}
          onMouseLeave={stopRepeat}
          tabIndex={-1}
          aria-label="Decrement"
        >
          −
        </button>
        <input
          type="text"
          inputMode="decimal"
          className={`${inputW} ${fontSize} text-center py-2 outline-none tabular-nums font-semibold`}
          style={{
            background: "transparent",
            color: isOutOfRange ? COL.danger : COL.text,
            border: "none",
          }}
          value={text}
          onChange={(e) => {
            const t = e.target.value;
            // Accept what the user typed as-is. Only block characters that
            // are clearly nonsense in a numeric field (letters other than
            // leading sign/dot/digits).
            setText(t);
            const parsed = parseFloat(t);
            if (isFinite(parsed)) commit(parsed);
            // If not finite (empty, "-", ".", etc.), leave parent value
            // alone — the user is mid-type.
          }}
          onBlur={() => {
            // Normalise display on blur: always show the committed value.
            // This handles empty / invalid residue left by the user.
            setText(String(valueRef.current));
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur();
          }}
        />
        <button
          type="button"
          className={`${btnW} ${h} flex items-center justify-center text-xl select-none stepper-btn`}
          style={{ color: COL.textMid, borderLeft: `1px solid ${COL.border}` }}
          onMouseDown={() => startRepeat(step)}
          onMouseUp={stopRepeat}
          onMouseLeave={stopRepeat}
          tabIndex={-1}
          aria-label="Increment"
        >
          +
        </button>
      </div>
      {unit && (
        <span className="text-[13px] w-11 text-right tabular-nums" style={{ color: COL.textDim, opacity: 0.75 }}>
          {unit}
        </span>
      )}
    </div>
  );
}
