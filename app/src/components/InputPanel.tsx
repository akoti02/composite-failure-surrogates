import { useState, useEffect } from "react";
import { COL, DEFECT_COLORS, MAX_DEFECTS, PLATE_LENGTH, PLATE_WIDTH, TOOLTIPS } from "../lib/constants";
import { NumberInput } from "./NumberInput";
import { MATERIAL_DB, LAYUP_DB, BC_MODES } from "../lib/materials";
import type { DefectParams } from "../lib/types";

interface Props {
  nDefects: number; setNDefects: (n: number) => void;
  pressureX: number; setPressureX: (v: number) => void;
  pressureY: number; setPressureY: (v: number) => void;
  materialKey: string; setMaterialKey: (v: string) => void;
  layupKey: string; setLayupKey: (v: string) => void;
  bcMode: string; setBcMode: (v: string) => void;
  defects: DefectParams[];
  updateDefect: (i: number, field: keyof DefectParams, value: number) => void;
}

/* ─────────────────────────────────────────────────────────── */
/*  SURFACE TOKENS  — 4-level dark elevation (5-8% luminance  */
/*  step per level, matching shadcn/muzli guidance)            */
/* ─────────────────────────────────────────────────────────── */
const S = {
  base:    "rgba(255,255,255,0.00)",   // level 0 — inherits panel bg
  raised:  "rgba(255,255,255,0.025)",  // level 1 — sections
  card:    "rgba(255,255,255,0.045)",  // level 2 — cards/inputs
  inset:   "rgba(0,0,0,0.20)",        // sunken — input fields
  border:  "rgba(255,255,255,0.08)",   // default border
  borderH: "rgba(255,255,255,0.14)",   // hover border
  hoverBg: "rgba(255,255,255,0.03)",   // row hover
};

/* ─────────────────────────────────────────────────────────── */
/*  CONFIG CARD  — large selection card for Material/Layup/BC  */
/* ─────────────────────────────────────────────────────────── */
function ConfigCard({ label, value, description, onChange, options }: {
  label: string;
  value: string;
  description?: string;
  onChange: (v: string) => void;
  options: { value: string; label: string; desc?: string }[];
}) {
  const current = options.find(o => o.value === value);
  return (
    <div
      className="rounded-xl p-3.5 transition-all duration-200"
      style={{ background: S.raised, border: `1px solid ${S.border}` }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[12px] font-semibold uppercase tracking-wider" style={{ color: COL.textDim }}>
          {label}
        </span>
      </div>
      <select
        className="w-full text-[15px] font-medium px-3.5 py-2.5 rounded-lg outline-none cursor-pointer transition-all duration-150 focus:ring-2"
        style={{
          background: S.inset,
          border: `1px solid ${S.border}`,
          color: COL.text,
          boxShadow: "inset 0 1px 3px rgba(0,0,0,0.2)",
        }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {(description || current?.desc) && (
        <p className="text-[11px] mt-2 leading-relaxed" style={{ color: COL.textDim, opacity: 0.7 }}>
          {current?.desc ?? description}
        </p>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  SECTION LABEL  — subtle divider with accent tint           */
/* ─────────────────────────────────────────────────────────── */
function SectionLabel({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 pt-5 pb-2">
      <span className="text-[11px] font-bold uppercase tracking-[0.1em]" style={{ color: COL.accent, opacity: 0.5 }}>
        {text}
      </span>
      <div className="flex-1 h-px" style={{ background: `linear-gradient(to right, ${COL.accent}20, transparent)` }} />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  DEFECT COUNT  — numbered buttons, active one glows         */
/* ─────────────────────────────────────────────────────────── */
function DefectCount({ value, max, onChange }: { value: number; max: number; onChange: (n: number) => void }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="text-[13px] font-medium mr-1" style={{ color: COL.textDim }}>Count</span>
      {Array.from({ length: max }, (_, i) => {
        const active = i < value;
        const isEdge = i === value - 1;
        return (
          <button
            key={i}
            className="flex-1 flex items-center justify-center rounded-lg cursor-pointer transition-all duration-200"
            style={{
              height: 38,
              background: active ? `${DEFECT_COLORS[i]}15` : S.raised,
              border: `1.5px solid ${active ? `${DEFECT_COLORS[i]}40` : S.border}`,
              color: active ? DEFECT_COLORS[i] : COL.textDim,
              fontWeight: isEdge ? 800 : active ? 600 : 400,
              fontSize: 14,
              boxShadow: isEdge ? `0 0 16px ${DEFECT_COLORS[i]}12` : "none",
            }}
            onClick={() => onChange(i + 1)}
          >
            {i + 1}
          </button>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  DEFECT TABS  — which defect is being edited                */
/* ─────────────────────────────────────────────────────────── */
function DefectTabs({ nDefects, active, onSelect }: {
  nDefects: number; active: number; onSelect: (i: number) => void;
}) {
  if (nDefects <= 1) return null;
  return (
    <div className="flex items-center gap-1.5 py-1.5">
      {Array.from({ length: nDefects }, (_, i) => {
        const isActive = i === active;
        return (
          <button
            key={i}
            className="flex-1 py-2 rounded-lg text-[13px] font-semibold cursor-pointer transition-all duration-200"
            style={{
              background: isActive ? `${DEFECT_COLORS[i]}18` : "transparent",
              borderBottom: isActive ? `2px solid ${DEFECT_COLORS[i]}` : "2px solid transparent",
              color: isActive ? DEFECT_COLORS[i] : COL.textDim,
              opacity: isActive ? 1 : 0.45,
            }}
            onClick={() => onSelect(i)}
          >
            Defect {i + 1}
          </button>
        );
      })}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  MAIN PANEL                                                 */
/* ─────────────────────────────────────────────────────────── */
export function InputPanel({
  nDefects, setNDefects, pressureX, setPressureX, pressureY, setPressureY,
  materialKey, setMaterialKey, layupKey, setLayupKey, bcMode, setBcMode,
  defects, updateDefect,
}: Props) {
  const [activeDefect, setActiveDefect] = useState(0);
  const clampedActive = Math.min(activeDefect, nDefects - 1);
  useEffect(() => {
    if (clampedActive !== activeDefect) setActiveDefect(clampedActive);
  }, [clampedActive, activeDefect]);

  const d = defects[clampedActive];
  const mat = MATERIAL_DB[materialKey];
  const layup = LAYUP_DB[layupKey];

  return (
    <div className="flex-1 overflow-y-auto px-5 py-3 flex flex-col min-h-0">

      {/* ═══ CONFIGURATION ═══ — 3 large selection cards ═══ */}
      <SectionLabel text="Configuration" />
      <div className="flex flex-col gap-2.5">
        <ConfigCard
          label="Material"
          value={materialKey}
          onChange={setMaterialKey}
          options={Object.entries(MATERIAL_DB).map(([k, m]) => ({
            value: k, label: m.name, desc: m.description,
          }))}
        />
        <ConfigCard
          label="Layup"
          value={layupKey}
          onChange={setLayupKey}
          options={Object.entries(LAYUP_DB).map(([k, l]) => ({
            value: k, label: l.name, desc: l.description,
          }))}
        />
        <ConfigCard
          label="Boundary Condition"
          value={bcMode}
          onChange={setBcMode}
          options={BC_MODES.map(b => ({
            value: b.id, label: b.name, desc: b.description,
          }))}
        />
      </div>

      {/* ═══ LOADING ═══ — pressure X and Y ═══ */}
      <SectionLabel text="Applied Loading" />
      <div
        className="rounded-xl p-4"
        style={{ background: S.raised, border: `1px solid ${S.border}` }}
      >
        <NumberInput label="Pressure X" value={pressureX} onChange={setPressureX} unit="MPa" step={10} min={-500} max={500} tooltip={TOOLTIPS.pressure_x} />
        <NumberInput label="Pressure Y" value={pressureY} onChange={setPressureY} unit="MPa" step={10} min={-500} max={500} tooltip={TOOLTIPS.pressure_y} />
      </div>

      {/* ═══ DEFECTS ═══ — count + active defect editor ═══ */}
      <SectionLabel text="Defects" />
      <div
        className="rounded-xl p-4"
        style={{ background: S.raised, border: `1px solid ${S.border}` }}
      >
        <DefectCount value={nDefects} max={MAX_DEFECTS} onChange={setNDefects} />
        <DefectTabs nDefects={nDefects} active={clampedActive} onSelect={setActiveDefect} />

        {/* Active defect parameters — 2-column grid */}
        {d && (
          <div
            key={clampedActive}
            className="rounded-xl p-4 mt-3 tab-fade-in"
            style={{
              background: `${DEFECT_COLORS[clampedActive]}05`,
              border: `1px solid ${DEFECT_COLORS[clampedActive]}18`,
            }}
          >
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: DEFECT_COLORS[clampedActive] }} />
              <span className="text-[14px] font-semibold" style={{ color: COL.text }}>
                Defect {clampedActive + 1}
              </span>
              <span className="text-[11px] ml-auto" style={{ color: COL.textDim }}>
                {mat?.name} · {layup?.name}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0">
              <NumberInput label="X" value={d.x} onChange={(v) => updateDefect(clampedActive, "x", v)} unit="mm" step={1} min={0} max={PLATE_LENGTH} compact />
              <NumberInput label="Y" value={d.y} onChange={(v) => updateDefect(clampedActive, "y", v)} unit="mm" step={1} min={0} max={PLATE_WIDTH} compact />
              <NumberInput label="Length" value={d.half_length} onChange={(v) => updateDefect(clampedActive, "half_length", v)} unit="mm" step={0.5} min={0.1} max={50} tooltip={TOOLTIPS.half_length} compact />
              <NumberInput label="Width" value={d.width} onChange={(v) => updateDefect(clampedActive, "width", v)} unit="mm" step={0.1} min={0.01} max={10} tooltip={TOOLTIPS.width} compact />
              <NumberInput label="Angle" value={d.angle} onChange={(v) => updateDefect(clampedActive, "angle", v)} unit="deg" step={5} min={-90} max={90} tooltip={TOOLTIPS.angle} compact />
              <NumberInput label="Rough." value={d.roughness} onChange={(v) => updateDefect(clampedActive, "roughness", v)} unit="0-1" step={0.1} min={0} max={1} tooltip={TOOLTIPS.roughness} compact />
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
