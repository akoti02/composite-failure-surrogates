import { useState, useEffect } from "react";
import { COL, DEFECT_COLORS, MAX_DEFECTS, PLATE_LENGTH, PLATE_WIDTH, TOOLTIPS } from "../lib/constants";
import { NumberInput } from "./NumberInput";
import { CollapsibleSection } from "./CollapsibleSection";
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

function DefectSlider({ value, max, onChange }: { value: number; max: number; onChange: (n: number) => void }) {
  return (
    <div className="flex items-center gap-3 py-1.5 px-1">
      <label className="text-[11px]" style={{ color: COL.textMid }}>Defects</label>
      <div className="flex-1 flex items-center gap-1">
        {Array.from({ length: max }, (_, i) => {
          const active = i < value;
          return (
            <button
              key={i}
              className="flex-1 h-2 rounded-full transition-all duration-200 cursor-pointer"
              style={{
                background: active ? DEFECT_COLORS[i] : "rgba(255,255,255,0.06)",
                opacity: active ? 1 : 0.5,
              }}
              onClick={() => onChange(i + 1)}
            />
          );
        })}
      </div>
      <span className="text-[11px] font-bold w-8 text-center tabular-nums" style={{ color: COL.accent }}>
        {value}
      </span>
    </div>
  );
}

function MiniEllipse({ defect, color }: { defect: DefectParams; color: string }) {
  const w = 28;
  const h = 14;
  const rx = Math.min(defect.half_length * 0.5, w / 2 - 1);
  const ry = Math.max(defect.width * 1.5, 1.5);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <ellipse
        cx={w / 2} cy={h / 2} rx={Math.max(rx, 2)} ry={Math.min(ry, h / 2 - 1)}
        transform={`rotate(${defect.angle} ${w / 2} ${h / 2})`}
        fill={color} fillOpacity={0.2}
        stroke={color} strokeWidth={1.5}
      />
    </svg>
  );
}

function DefectTabBar({ nDefects, activeTab, onSelect, defects }: {
  nDefects: number; activeTab: number; onSelect: (i: number) => void; defects: DefectParams[];
}) {
  return (
    <div className="flex items-center gap-1.5 py-1 px-1">
      {Array.from({ length: nDefects }, (_, i) => {
        const active = i === activeTab;
        return (
          <button
            key={i}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg transition-all duration-150 cursor-pointer"
            style={{
              background: active ? `${DEFECT_COLORS[i]}15` : "transparent",
              border: `1px solid ${active ? `${DEFECT_COLORS[i]}40` : COL.border}`,
              opacity: active ? 1 : 0.6,
            }}
            onClick={() => onSelect(i)}
          >
            <MiniEllipse defect={defects[i]} color={DEFECT_COLORS[i]} />
            <span className="text-[10px] font-semibold" style={{ color: active ? DEFECT_COLORS[i] : COL.textDim }}>
              {i + 1}
            </span>
          </button>
        );
      })}
    </div>
  );
}

const selectStyle = {
  background: COL.panel,
  border: `1px solid ${COL.border}`,
  color: COL.text,
};

export function InputPanel({
  nDefects, setNDefects, pressureX, setPressureX, pressureY, setPressureY,
  materialKey, setMaterialKey, layupKey, setLayupKey, bcMode, setBcMode,
  defects, updateDefect,
}: Props) {
  const [activeDefect, setActiveDefect] = useState(0);

  // Clamp active tab if defects reduced (useEffect to avoid setState during render)
  const clampedActive = Math.min(activeDefect, nDefects - 1);
  useEffect(() => {
    if (clampedActive !== activeDefect) setActiveDefect(clampedActive);
  }, [clampedActive, activeDefect]);

  const d = defects[clampedActive];
  const mat = MATERIAL_DB[materialKey];
  const layup = LAYUP_DB[layupKey];
  const bc = BC_MODES.find(b => b.id === bcMode);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-2 flex flex-col gap-0.5 min-h-0">

        <CollapsibleSection
          title="Loading Conditions"
          icon="⊕"
          summary={`Px=${pressureX}, Py=${pressureY} MPa`}
          defaultOpen={true}
        >
          <NumberInput label="Pressure X" value={pressureX} onChange={setPressureX} unit="MPa" step={10} min={-500} max={500} tooltip={TOOLTIPS.pressure_x} />
          <NumberInput label="Pressure Y" value={pressureY} onChange={setPressureY} unit="MPa" step={10} min={-500} max={500} tooltip={TOOLTIPS.pressure_y} />
        </CollapsibleSection>

        <CollapsibleSection
          title="Material & Layup"
          icon="◈"
          summary={`${mat?.name ?? materialKey} / ${layup?.name ?? layupKey}`}
          defaultOpen={false}
        >
          <div className="flex flex-col gap-2 py-1">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold" style={{ color: COL.textDim }} data-tooltip={TOOLTIPS.material}>Material</label>
              <select
                className="text-[11px] px-2.5 py-1.5 rounded-md outline-none w-full"
                style={selectStyle}
                value={materialKey}
                onChange={(e) => setMaterialKey(e.target.value)}
              >
                {Object.entries(MATERIAL_DB).map(([key, m]) => (
                  <option key={key} value={key}>{m.name}</option>
                ))}
              </select>
              {mat && (
                <span className="text-[9px] px-1" style={{ color: COL.textDim }}>{mat.description}</span>
              )}
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold" style={{ color: COL.textDim }} data-tooltip={TOOLTIPS.layup}>Layup</label>
              <select
                className="text-[11px] px-2.5 py-1.5 rounded-md outline-none w-full"
                style={selectStyle}
                value={layupKey}
                onChange={(e) => setLayupKey(e.target.value)}
              >
                {Object.entries(LAYUP_DB).map(([key, l]) => (
                  <option key={key} value={key}>{l.name}</option>
                ))}
              </select>
              {layup && (
                <span className="text-[9px] px-1" style={{ color: COL.textDim }}>{layup.description}</span>
              )}
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] font-semibold" style={{ color: COL.textDim }} data-tooltip={TOOLTIPS.bc_mode}>BC Mode</label>
              <select
                className="text-[11px] px-2.5 py-1.5 rounded-md outline-none w-full"
                style={selectStyle}
                value={bcMode}
                onChange={(e) => setBcMode(e.target.value)}
              >
                {BC_MODES.map(b => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
              {bc && (
                <span className="text-[9px] px-1" style={{ color: COL.textDim }}>{bc.description}</span>
              )}
            </div>
          </div>
        </CollapsibleSection>

        <CollapsibleSection
          title="Damage Configuration"
          icon="⚠"
          summary={`${nDefects} defect${nDefects !== 1 ? "s" : ""}`}
          defaultOpen={true}
        >
          <DefectSlider value={nDefects} max={MAX_DEFECTS} onChange={setNDefects} />

          <DefectTabBar
            nDefects={nDefects}
            activeTab={clampedActive}
            onSelect={setActiveDefect}
            defects={defects}
          />

          {/* Single defect editor */}
          {d && (
            <div
              key={clampedActive}
              className="surface-card p-3 mt-1 tab-fade-in"
              style={{ borderLeft: `3px solid ${DEFECT_COLORS[clampedActive]}` }}
            >
              <div className="flex items-center gap-2 mb-2">
                <MiniEllipse defect={d} color={DEFECT_COLORS[clampedActive]} />
                <span className="text-[11px] font-semibold" style={{ color: COL.text }}>Defect {clampedActive + 1}</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <NumberInput label="X position" value={d.x} onChange={(v) => updateDefect(clampedActive, "x", v)} unit="mm" step={1} min={0} max={PLATE_LENGTH} />
                <NumberInput label="Y position" value={d.y} onChange={(v) => updateDefect(clampedActive, "y", v)} unit="mm" step={1} min={0} max={PLATE_WIDTH} />
                <NumberInput label="Half-Length" value={d.half_length} onChange={(v) => updateDefect(clampedActive, "half_length", v)} unit="mm" step={0.5} min={0.1} max={50} tooltip={TOOLTIPS.half_length} />
                <NumberInput label="Width" value={d.width} onChange={(v) => updateDefect(clampedActive, "width", v)} unit="mm" step={0.1} min={0.01} max={10} tooltip={TOOLTIPS.width} />
                <NumberInput label="Angle" value={d.angle} onChange={(v) => updateDefect(clampedActive, "angle", v)} unit="deg" step={5} min={-90} max={90} tooltip={TOOLTIPS.angle} />
                <NumberInput label="Roughness" value={d.roughness} onChange={(v) => updateDefect(clampedActive, "roughness", v)} unit="0-1" step={0.1} min={0} max={1} tooltip={TOOLTIPS.roughness} />
              </div>
            </div>
          )}
        </CollapsibleSection>

    </div>
  );
}
