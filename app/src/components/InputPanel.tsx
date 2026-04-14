import { useState, useEffect } from "react";
import { COL, DEFECT_COLORS, MAX_DEFECTS, PLATE_LENGTH, PLATE_WIDTH } from "../lib/constants";
import { NumberInput } from "./NumberInput";
import { MATERIAL_DB, LAYUP_DB, BC_MODES } from "../lib/materials";
import type { DefectParams } from "../lib/types";
import { useT } from "../lib/i18n";
import type { TKey } from "../lib/i18n";

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
/*  SURFACE TOKENS                                             */
/* ─────────────────────────────────────────────────────────── */
const S = {
  base:    "rgba(255,255,255,0.00)",
  raised:  "rgba(255,255,255,0.03)",
  card:    "rgba(255,255,255,0.05)",
  inset:   "rgba(0,0,0,0.25)",
  border:  "rgba(255,255,255,0.10)",
  borderH: "rgba(0, 234, 255, 0.28)",
  hoverBg: "rgba(0, 234, 255, 0.05)",
};

/* ─────────────────────────────────────────────────────────── */
/*  CONFIG CARD                                                */
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
        <span className="text-[13px] font-semibold uppercase tracking-wider" style={{ color: COL.accent, textShadow: "0 0 8px rgba(0,234,255,0.35)" }}>
          {label}
        </span>
      </div>
      <select
        className="w-full text-[16px] font-medium px-3.5 py-2.5 rounded-lg outline-none cursor-pointer transition-all duration-150"
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
        <p className="text-[12px] mt-2 leading-relaxed" style={{ color: COL.textMid, opacity: 0.85 }}>
          {current?.desc ?? description}
        </p>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  SECTION LABEL                                              */
/* ─────────────────────────────────────────────────────────── */
function SectionLabel({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 pt-5 pb-2">
      <span className="text-[12px] font-bold uppercase tracking-[0.12em] text-glow-cyan" style={{ color: COL.accent, opacity: 0.9 }}>
        {text}
      </span>
      <div className="flex-1 h-px" style={{ background: `linear-gradient(to right, rgba(0,234,255,0.35), transparent)` }} />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────── */
/*  DEFECT COUNT                                               */
/* ─────────────────────────────────────────────────────────── */
function DefectCount({ value, max, onChange, label }: { value: number; max: number; onChange: (n: number) => void; label: string }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="text-[14px] font-medium mr-1" style={{ color: COL.textMid }}>{label}</span>
      {Array.from({ length: max }, (_, i) => {
        const active = i < value;
        const isEdge = i === value - 1;
        return (
          <button
            key={i}
            className="flex-1 flex items-center justify-center rounded-lg cursor-pointer transition-all duration-200"
            style={{
              height: 40,
              background: active ? `${DEFECT_COLORS[i]}22` : S.raised,
              border: `1.5px solid ${active ? `${DEFECT_COLORS[i]}77` : S.border}`,
              color: active ? DEFECT_COLORS[i] : COL.textDim,
              fontWeight: isEdge ? 800 : active ? 700 : 400,
              fontSize: 15,
              boxShadow: isEdge ? `0 0 18px ${DEFECT_COLORS[i]}44, 0 0 4px ${DEFECT_COLORS[i]}66` : active ? `0 0 8px ${DEFECT_COLORS[i]}22` : "none",
              textShadow: isEdge ? `0 0 6px ${DEFECT_COLORS[i]}aa` : undefined,
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
/*  DEFECT TABS                                                */
/* ─────────────────────────────────────────────────────────── */
function DefectTabs({ nDefects, active, onSelect, label }: {
  nDefects: number; active: number; onSelect: (i: number) => void; label: string;
}) {
  if (nDefects <= 1) return null;
  return (
    <div className="flex items-center gap-1.5 py-1.5">
      {Array.from({ length: nDefects }, (_, i) => {
        const isActive = i === active;
        return (
          <button
            key={i}
            className="flex-1 py-2 rounded-lg text-[14px] font-semibold cursor-pointer transition-all duration-200"
            style={{
              background: isActive ? `${DEFECT_COLORS[i]}22` : "transparent",
              borderBottom: isActive ? `2px solid ${DEFECT_COLORS[i]}` : "2px solid transparent",
              color: isActive ? DEFECT_COLORS[i] : COL.textDim,
              opacity: isActive ? 1 : 0.55,
              textShadow: isActive ? `0 0 8px ${DEFECT_COLORS[i]}88` : undefined,
            }}
            onClick={() => onSelect(i)}
          >
            {label} {i + 1}
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
  const t = useT();
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

      {/* ═══ CONFIGURATION ═══ */}
      <SectionLabel text={t("section_configuration")} />
      <div className="flex flex-col gap-2.5">
        <ConfigCard
          label={t("material")}
          value={materialKey}
          onChange={setMaterialKey}
          options={Object.entries(MATERIAL_DB).map(([k, m]) => ({
            value: k, label: m.name, desc: t(m.descKey as TKey),
          }))}
        />
        <ConfigCard
          label={t("layup")}
          value={layupKey}
          onChange={setLayupKey}
          options={Object.entries(LAYUP_DB).map(([k, l]) => ({
            value: k, label: l.name, desc: t(l.descKey as TKey),
          }))}
        />
        <ConfigCard
          label={t("boundary_condition")}
          value={bcMode}
          onChange={setBcMode}
          options={BC_MODES.map(b => ({
            value: b.id, label: t(b.nameKey as TKey), desc: t(b.descKey as TKey),
          }))}
        />
      </div>

      {/* ═══ LOADING ═══ */}
      <SectionLabel text={t("section_loading")} />
      <div
        className="rounded-xl p-4"
        style={{ background: S.raised, border: `1px solid ${S.border}` }}
      >
        <NumberInput label={t("pressure_x")} value={pressureX} onChange={setPressureX} unit={t("unit_mpa")} step={10} min={-500} max={500} tooltip={t("tip_pressure_x")} />
        <NumberInput label={t("pressure_y")} value={pressureY} onChange={setPressureY} unit={t("unit_mpa")} step={10} min={-500} max={500} tooltip={t("tip_pressure_y")} />
      </div>

      {/* ═══ DEFECTS ═══ */}
      <SectionLabel text={t("section_defects")} />
      <div
        className="rounded-xl p-4"
        style={{ background: S.raised, border: `1px solid ${S.border}` }}
      >
        <DefectCount value={nDefects} max={MAX_DEFECTS} onChange={setNDefects} label={t("count")} />
        <DefectTabs nDefects={nDefects} active={clampedActive} onSelect={setActiveDefect} label={t("defect")} />

        {d && (
          <div
            key={clampedActive}
            className="rounded-xl p-4 mt-3 tab-fade-in"
            style={{
              background: `${DEFECT_COLORS[clampedActive]}08`,
              border: `1px solid ${DEFECT_COLORS[clampedActive]}33`,
              boxShadow: `0 0 12px ${DEFECT_COLORS[clampedActive]}18`,
            }}
          >
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: DEFECT_COLORS[clampedActive], boxShadow: `0 0 8px ${DEFECT_COLORS[clampedActive]}` }} />
              <span className="text-[15px] font-semibold" style={{ color: COL.text }}>
                {t("defect")} {clampedActive + 1}
              </span>
              <span className="text-[12px] ml-auto" style={{ color: COL.textDim }}>
                {mat?.name} · {layup?.name}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0">
              <NumberInput label={t("defect_x")} value={d.x} onChange={(v) => updateDefect(clampedActive, "x", v)} unit={t("unit_mm")} step={1} min={0} max={PLATE_LENGTH} tooltip={t("tip_x_position")} compact />
              <NumberInput label={t("defect_y")} value={d.y} onChange={(v) => updateDefect(clampedActive, "y", v)} unit={t("unit_mm")} step={1} min={0} max={PLATE_WIDTH} tooltip={t("tip_y_position")} compact />
              <NumberInput label={t("defect_length")} value={d.half_length} onChange={(v) => updateDefect(clampedActive, "half_length", v)} unit={t("unit_mm")} step={0.5} min={0.1} max={50} tooltip={t("tip_half_length")} compact />
              <NumberInput label={t("defect_width")} value={d.width} onChange={(v) => updateDefect(clampedActive, "width", v)} unit={t("unit_mm")} step={0.1} min={0.01} max={10} tooltip={t("tip_width")} compact />
              <NumberInput label={t("defect_angle")} value={d.angle} onChange={(v) => updateDefect(clampedActive, "angle", v)} unit={t("unit_deg")} step={5} min={-90} max={90} tooltip={t("tip_angle")} compact />
              <NumberInput label={t("defect_roughness")} value={d.roughness} onChange={(v) => updateDefect(clampedActive, "roughness", v)} unit="0-1" step={0.1} min={0} max={1} tooltip={t("tip_roughness")} compact />
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
