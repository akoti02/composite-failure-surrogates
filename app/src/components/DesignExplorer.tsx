import { useState, useCallback, useRef } from "react";
import { COL, MAX_DEFECTS } from "../lib/constants";
import { mapColor } from "../lib/stress-field";
import { invoke } from "@tauri-apps/api/core";
import type { RawInputs, PredictionResults } from "../lib/types";
import { DEFAULT_DEFECT } from "../lib/presets";

/** Parameter definition for sweeps */
interface SweepParam {
  id: string;
  label: string;
  min: number;
  max: number;
  default: number;
  unit: string;
}

const SWEEP_PARAMS: SweepParam[] = [
  { id: "pressure_x", label: "Pressure X", min: -500, max: 500, default: 100, unit: "MPa" },
  { id: "pressure_y", label: "Pressure Y", min: -500, max: 500, default: 0, unit: "MPa" },
  { id: "ply_thickness", label: "Ply Thickness", min: 0.05, max: 1.0, default: 0.125, unit: "mm" },
  { id: "layup_rotation", label: "Layup Rotation", min: -90, max: 90, default: 0, unit: "deg" },
  { id: "defect1_half_length", label: "Defect 1 Half-Length", min: 0.1, max: 50, default: 10, unit: "mm" },
  { id: "defect1_width", label: "Defect 1 Width", min: 0.01, max: 10, default: 1, unit: "mm" },
  { id: "defect1_angle", label: "Defect 1 Angle", min: -90, max: 90, default: 0, unit: "deg" },
  { id: "defect1_roughness", label: "Defect 1 Roughness", min: 0, max: 1, default: 0.5, unit: "" },
];

const OUTPUT_FIELDS: { id: keyof PredictionResults; label: string; unit: string }[] = [
  { id: "max_mises", label: "Peak von Mises", unit: "MPa" },
  { id: "tsai_wu_index", label: "Tsai-Wu Index", unit: "" },
  { id: "max_s11", label: "Max S11", unit: "MPa" },
  { id: "min_s11", label: "Min S11", unit: "MPa" },
  { id: "max_s12", label: "Max S12", unit: "MPa" },
  { id: "max_hashin_ft", label: "Hashin FT", unit: "" },
  { id: "max_hashin_fc", label: "Hashin FC", unit: "" },
  { id: "max_hashin_mt", label: "Hashin MT", unit: "" },
  { id: "max_hashin_mc", label: "Hashin MC", unit: "" },
];

type ExplorerMode = "sweep1d" | "sweep2d" | "montecarlo" | "sensitivity";

interface SweepResult1D {
  paramValues: number[];
  outputs: Record<string, number[]>;
}

interface SweepResult2D {
  xValues: number[];
  yValues: number[];
  outputs: Record<string, number[][]>;
}

interface MonteCarloResult {
  samples: Record<string, number[]>;
  outputs: Record<string, number[]>;
  stats: Record<string, { mean: number; std: number; min: number; max: number; p5: number; p95: number }>;
}

interface SensitivityResult {
  params: string[];
  indices: Record<string, number[]>; // output → sensitivity per param
}

interface ExplorerProps {
  nDefects: number;
  pressureX: number;
  pressureY: number;
  plyThickness: number;
  layupRotation: number;
  defects: import("../lib/types").DefectParams[];
  modelsReady: boolean;
}

function buildBaseInputs(props: ExplorerProps, overrides: Record<string, number>): RawInputs {
  const raw: RawInputs = {
    n_defects: overrides.n_defects ?? props.nDefects,
    pressure_x: overrides.pressure_x ?? props.pressureX,
    pressure_y: overrides.pressure_y ?? props.pressureY,
    ply_thickness: overrides.ply_thickness ?? props.plyThickness,
    layup_rotation: overrides.layup_rotation ?? props.layupRotation,
  };
  const defects = props.defects;
  for (let i = 0; i < MAX_DEFECTS; i++) {
    const d = defects[i] || DEFAULT_DEFECT;
    const idx = i + 1;
    raw[`defect${idx}_x`] = overrides[`defect${idx}_x`] ?? d.x;
    raw[`defect${idx}_y`] = overrides[`defect${idx}_y`] ?? d.y;
    raw[`defect${idx}_half_length`] = overrides[`defect${idx}_half_length`] ?? d.half_length;
    raw[`defect${idx}_width`] = overrides[`defect${idx}_width`] ?? d.width;
    raw[`defect${idx}_angle`] = overrides[`defect${idx}_angle`] ?? d.angle;
    raw[`defect${idx}_roughness`] = overrides[`defect${idx}_roughness`] ?? d.roughness;
  }
  return raw;
}

/** Simple SVG line chart */
function LineChart({ data, title, xLabel, yLabel, width = 400, height = 200 }: {
  data: { x: number[]; y: number[]; color: string; label: string }[];
  title: string;
  xLabel: string;
  yLabel: string;
  width?: number;
  height?: number;
}) {
  const mx = 50, my = 24, mb = 30, mr = 20;
  const pw = width - mx - mr;
  const ph = height - my - mb;

  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (const d of data) {
    for (const v of d.x) { if (v < xMin) xMin = v; if (v > xMax) xMax = v; }
    for (const v of d.y) { if (isFinite(v)) { if (v < yMin) yMin = v; if (v > yMax) yMax = v; } }
  }
  if (yMin === yMax) { yMin -= 1; yMax += 1; }
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <text x={width / 2} y={14} fill={COL.textMid} fontSize={10} textAnchor="middle" fontWeight={600}>{title}</text>
      <rect x={mx} y={my} width={pw} height={ph} fill="none" stroke="rgba(255,255,255,0.06)" />

      {/* Grid lines */}
      {[0.25, 0.5, 0.75].map(f => (
        <line key={f} x1={mx} y1={my + ph * (1 - f)} x2={mx + pw} y2={my + ph * (1 - f)} stroke="rgba(255,255,255,0.04)" />
      ))}

      {data.map((series, si) => {
        const points = series.x.map((xv, i) => {
          const px = mx + ((xv - xMin) / xRange) * pw;
          const py = my + ph - ((isFinite(series.y[i]) ? series.y[i] : yMin) - yMin) / yRange * ph;
          return `${px.toFixed(1)},${py.toFixed(1)}`;
        }).join(" ");
        return <polyline key={si} points={points} fill="none" stroke={series.color} strokeWidth={1.5} />;
      })}

      {/* Axes */}
      <text x={width / 2} y={height - 4} fill={COL.textDim} fontSize={9} textAnchor="middle">{xLabel}</text>
      <text x={10} y={my + ph / 2} fill={COL.textDim} fontSize={9} textAnchor="middle" transform={`rotate(-90, 10, ${my + ph / 2})`}>{yLabel}</text>

      {/* Tick labels */}
      {[0, 0.5, 1].map(f => (
        <text key={`x${f}`} x={mx + pw * f} y={my + ph + 14} fill={COL.textDim} fontSize={8} textAnchor="middle">
          {(xMin + xRange * f).toFixed(1)}
        </text>
      ))}
      {[0, 0.5, 1].map(f => (
        <text key={`y${f}`} x={mx - 4} y={my + ph * (1 - f) + 3} fill={COL.textDim} fontSize={8} textAnchor="end">
          {(yMin + yRange * f).toFixed(1)}
        </text>
      ))}

      {/* Legend */}
      {data.length > 1 && data.map((s, i) => (
        <g key={i} transform={`translate(${mx + 8}, ${my + 12 + i * 14})`}>
          <line x1={0} y1={0} x2={12} y2={0} stroke={s.color} strokeWidth={2} />
          <text x={16} y={3} fill={COL.textDim} fontSize={8}>{s.label}</text>
        </g>
      ))}
    </svg>
  );
}

/** 2D heatmap chart */
function HeatmapChart({ xValues, yValues, data, title, xLabel, yLabel, width = 360, height = 280 }: {
  xValues: number[]; yValues: number[]; data: number[][];
  title: string; xLabel: string; yLabel: string;
  width?: number; height?: number;
}) {
  const mx = 50, my = 24, mb = 30, mr = 60;
  const pw = width - mx - mr;
  const ph = height - my - mb;

  let vMin = Infinity, vMax = -Infinity;
  for (const row of data) for (const v of row) {
    if (isFinite(v)) { if (v < vMin) vMin = v; if (v > vMax) vMax = v; }
  }
  if (vMin === vMax) { vMin -= 1; vMax += 1; }

  const nx = xValues.length;
  const ny = yValues.length;
  const cellW = pw / nx;
  const cellH = ph / ny;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <text x={width / 2} y={14} fill={COL.textMid} fontSize={10} textAnchor="middle" fontWeight={600}>{title}</text>

      {data.map((row, j) => row.map((val, i) => {
        const [r, g, b] = isFinite(val)
          ? mapColor(val, vMin, vMax, "turbo")
          : [30, 30, 30];
        return (
          <rect
            key={`${j}-${i}`}
            x={mx + i * cellW} y={my + j * cellH}
            width={cellW + 0.5} height={cellH + 0.5}
            fill={`rgb(${r},${g},${b})`}
          />
        );
      }))}

      <text x={(mx + mx + pw) / 2} y={height - 4} fill={COL.textDim} fontSize={9} textAnchor="middle">{xLabel}</text>
      <text x={10} y={my + ph / 2} fill={COL.textDim} fontSize={9} textAnchor="middle" transform={`rotate(-90, 10, ${my + ph / 2})`}>{yLabel}</text>

      {/* Colorbar */}
      {Array.from({ length: 20 }, (_, i) => {
        const t = i / 19;
        const val = vMin + t * (vMax - vMin);
        const [r, g, b] = mapColor(val, vMin, vMax, "turbo");
        return (
          <rect key={i} x={mx + pw + 8} y={my + ph * (1 - t) - ph / 20} width={10} height={ph / 19 + 1}
            fill={`rgb(${r},${g},${b})`} />
        );
      })}
      <text x={mx + pw + 22} y={my + 6} fill={COL.textDim} fontSize={8}>{vMax.toFixed(1)}</text>
      <text x={mx + pw + 22} y={my + ph + 4} fill={COL.textDim} fontSize={8}>{vMin.toFixed(1)}</text>
    </svg>
  );
}

/** Histogram for Monte Carlo */
function Histogram({ values, title, bins = 30, width = 300, height = 160 }: {
  values: number[]; title: string; bins?: number; width?: number; height?: number;
}) {
  if (values.length === 0) return null;

  const mx = 40, my = 20, mb = 24, mr = 10;
  const pw = width - mx - mr;
  const ph = height - my - mb;

  const sorted = [...values].filter(isFinite).sort((a, b) => a - b);
  const vMin = sorted[0], vMax = sorted[sorted.length - 1];
  const range = vMax - vMin || 1;
  const binW = range / bins;

  const counts = new Array(bins).fill(0);
  for (const v of sorted) {
    const idx = Math.min(Math.floor((v - vMin) / binW), bins - 1);
    counts[idx]++;
  }
  const maxCount = Math.max(...counts);

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <text x={width / 2} y={14} fill={COL.textMid} fontSize={10} textAnchor="middle" fontWeight={600}>{title}</text>
      {counts.map((c, i) => {
        const x = mx + (i / bins) * pw;
        const h = (c / maxCount) * ph;
        return (
          <rect key={i} x={x} y={my + ph - h} width={pw / bins - 0.5} height={h}
            fill={COL.accent} fillOpacity={0.7} />
        );
      })}
      <rect x={mx} y={my} width={pw} height={ph} fill="none" stroke="rgba(255,255,255,0.06)" />
      <text x={mx} y={height - 4} fill={COL.textDim} fontSize={8}>{vMin.toFixed(1)}</text>
      <text x={mx + pw} y={height - 4} fill={COL.textDim} fontSize={8} textAnchor="end">{vMax.toFixed(1)}</text>
    </svg>
  );
}

/** Sobol sensitivity bar chart */
function SensitivityBars({ params, indices, title, width = 360, height = 200 }: {
  params: string[]; indices: number[]; title: string; width?: number; height?: number;
}) {
  const mx = 120, my = 20, mb = 10, mr = 40;
  const pw = width - mx - mr;
  const ph = height - my - mb;
  const barH = Math.min(ph / params.length, 20);
  const maxIdx = Math.max(...indices, 0.01);

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <text x={width / 2} y={14} fill={COL.textMid} fontSize={10} textAnchor="middle" fontWeight={600}>{title}</text>
      {params.map((p, i) => {
        const y = my + i * barH;
        const w = (indices[i] / maxIdx) * pw;
        return (
          <g key={i}>
            <text x={mx - 4} y={y + barH / 2 + 3} fill={COL.textDim} fontSize={9} textAnchor="end">{p}</text>
            <rect x={mx} y={y + 2} width={Math.max(w, 1)} height={barH - 4} fill={COL.accent} rx={2} />
            <text x={mx + w + 4} y={y + barH / 2 + 3} fill={COL.textMid} fontSize={9}>{indices[i].toFixed(3)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function DesignExplorer(props: ExplorerProps) {
  const [mode, setMode] = useState<ExplorerMode>("sweep1d");
  const [paramX, setParamX] = useState("pressure_x");
  const [paramY, setParamY] = useState("ply_thickness");
  const [outputField, setOutputField] = useState<keyof PredictionResults>("max_mises");
  const [nSteps, setNSteps] = useState(20);
  const [nSamples, setNSamples] = useState(200);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);

  const [result1D, setResult1D] = useState<SweepResult1D | null>(null);
  const [result2D, setResult2D] = useState<SweepResult2D | null>(null);
  const [resultMC, setResultMC] = useState<MonteCarloResult | null>(null);
  const [resultSens, setResultSens] = useState<SensitivityResult | null>(null);

  const abortRef = useRef(false);

  const getParamDef = (id: string) => SWEEP_PARAMS.find(p => p.id === id) ?? SWEEP_PARAMS[0];

  const runSweep1D = useCallback(async () => {
    const param = getParamDef(paramX);
    if (!param) return;

    setRunning(true);
    setProgress(0);
    abortRef.current = false;

    const values: number[] = [];
    const outputs: Record<string, number[]> = {};
    OUTPUT_FIELDS.forEach(f => { outputs[f.id] = []; });

    const safeSteps = Math.max(nSteps, 1);
    for (let i = 0; i <= safeSteps; i++) {
      if (abortRef.current) break;
      const t = i / safeSteps;
      const val = param.min + t * (param.max - param.min);
      values.push(val);

      const raw = buildBaseInputs(props,{ [param.id]: val });
      raw[param.id] = val;

      try {
        const resp = await invoke<{ ok: boolean; results: PredictionResults }>("predict", { params: raw });
        if (resp.ok) {
          OUTPUT_FIELDS.forEach(f => {
            outputs[f.id].push(resp.results[f.id] as number ?? 0);
          });
        }
      } catch (err) {
        console.warn(`Sweep1D sample ${i} failed:`, err);
        OUTPUT_FIELDS.forEach(f => { outputs[f.id].push(NaN); });
      }

      setProgress((i + 1) / (nSteps + 1));
    }

    setResult1D({ paramValues: values, outputs });
    setRunning(false);
  }, [paramX, nSteps, props]);

  const runSweep2D = useCallback(async () => {
    const px = getParamDef(paramX);
    const py = getParamDef(paramY);
    if (!px || !py) return;

    const steps = Math.min(nSteps, 15); // keep 2D manageable
    setRunning(true);
    setProgress(0);
    abortRef.current = false;

    const xValues: number[] = [];
    const yValues: number[] = [];
    for (let i = 0; i <= steps; i++) {
      xValues.push(px.min + (i / steps) * (px.max - px.min));
      yValues.push(py.min + (i / steps) * (py.max - py.min));
    }

    const outputs: Record<string, number[][]> = {};
    OUTPUT_FIELDS.forEach(f => {
      outputs[f.id] = yValues.map(() => new Array(xValues.length).fill(0));
    });

    const total = xValues.length * yValues.length;
    let count = 0;

    for (let j = 0; j < yValues.length; j++) {
      for (let i = 0; i < xValues.length; i++) {
        if (abortRef.current) break;

        const raw = buildBaseInputs(props,{ [px.id]: xValues[i], [py.id]: yValues[j] });
        raw[px.id] = xValues[i];
        raw[py.id] = yValues[j];

        try {
          const resp = await invoke<{ ok: boolean; results: PredictionResults }>("predict", { params: raw });
          if (resp.ok) {
            OUTPUT_FIELDS.forEach(f => {
              outputs[f.id][j][i] = resp.results[f.id] as number ?? 0;
            });
          }
        } catch (err) {
          console.warn(`Sweep2D [${i},${j}] failed:`, err);
        }

        count++;
        setProgress(count / total);
      }
    }

    setResult2D({ xValues, yValues, outputs });
    setRunning(false);
  }, [paramX, paramY, nSteps, props]);

  const runMonteCarlo = useCallback(async () => {
    setRunning(true);
    setProgress(0);
    abortRef.current = false;

    const samples: Record<string, number[]> = {};
    const outputs: Record<string, number[]> = {};
    SWEEP_PARAMS.forEach(p => { samples[p.id] = []; });
    OUTPUT_FIELDS.forEach(f => { outputs[f.id] = []; });

    for (let i = 0; i < nSamples; i++) {
      if (abortRef.current) break;

      // Random sample from uniform distribution
      const vals: Record<string, number> = {};
      SWEEP_PARAMS.forEach(p => {
        const v = p.min + Math.random() * (p.max - p.min);
        vals[p.id] = v;
        samples[p.id].push(v);
      });

      const raw = buildBaseInputs(props,vals);
      SWEEP_PARAMS.forEach(p => { raw[p.id] = vals[p.id]; });

      try {
        const resp = await invoke<{ ok: boolean; results: PredictionResults }>("predict", { params: raw });
        if (resp.ok) {
          OUTPUT_FIELDS.forEach(f => {
            outputs[f.id].push(resp.results[f.id] as number ?? 0);
          });
        }
      } catch (err) {
        console.warn(`Monte Carlo sample ${i} failed:`, err);
        OUTPUT_FIELDS.forEach(f => { outputs[f.id].push(NaN); });
      }

      setProgress((i + 1) / nSamples);
    }

    // Compute statistics
    const stats: MonteCarloResult["stats"] = {};
    OUTPUT_FIELDS.forEach(f => {
      const vals = outputs[f.id].filter(isFinite).sort((a, b) => a - b);
      if (vals.length === 0) return;
      const mean = vals.reduce((s, v) => s + v, 0) / vals.length;
      const variance = vals.reduce((s, v) => s + (v - mean) ** 2, 0) / vals.length;
      stats[f.id] = {
        mean,
        std: Math.sqrt(variance),
        min: vals[0],
        max: vals[vals.length - 1],
        p5: vals[Math.floor(vals.length * 0.05)],
        p95: vals[Math.floor(vals.length * 0.95)],
      };
    });

    setResultMC({ samples, outputs, stats });
    setRunning(false);
  }, [nSamples, props]);

  const runSensitivity = useCallback(async () => {
    // Sobol-like sensitivity via Morris screening (one-at-a-time)
    setRunning(true);
    setProgress(0);
    abortRef.current = false;

    const nReps = 10;
    const params = SWEEP_PARAMS.map(p => p.id);
    const indices: Record<string, number[]> = {};
    OUTPUT_FIELDS.forEach(f => { indices[f.id] = new Array(params.length).fill(0); });

    const total = nReps * params.length;
    let count = 0;

    for (let rep = 0; rep < nReps; rep++) {
      // Random base point
      const base: Record<string, number> = {};
      SWEEP_PARAMS.forEach(p => {
        base[p.id] = p.min + Math.random() * (p.max - p.min);
      });

      // Get base prediction
      const rawBase = buildBaseInputs(props,base);
      SWEEP_PARAMS.forEach(p => { rawBase[p.id] = base[p.id]; });

      let baseResults: PredictionResults | null = null;
      try {
        const resp = await invoke<{ ok: boolean; results: PredictionResults }>("predict", { params: rawBase });
        if (resp.ok) baseResults = resp.results;
      } catch (err) {
        console.warn(`Sensitivity base prediction failed:`, err);
      }

      if (!baseResults) continue;

      // Perturb each parameter
      for (let pi = 0; pi < params.length; pi++) {
        if (abortRef.current) break;

        const p = getParamDef(params[pi]);
        const delta = (p.max - p.min) * 0.1;
        const perturbed = { ...base };
        perturbed[p.id] = Math.min(p.max, base[p.id] + delta);

        const rawPert = buildBaseInputs(props,perturbed);
        SWEEP_PARAMS.forEach(pp => { rawPert[pp.id] = perturbed[pp.id]; });

        try {
          const resp = await invoke<{ ok: boolean; results: PredictionResults }>("predict", { params: rawPert });
          if (resp.ok) {
            OUTPUT_FIELDS.forEach(f => {
              const baseVal = baseResults![f.id] as number ?? 0;
              const pertVal = resp.results[f.id] as number ?? 0;
              // Elementary effect
              const ee = Math.abs(pertVal - baseVal) / delta;
              indices[f.id][pi] += ee / nReps;
            });
          }
        } catch (err) {
          console.warn(`Sensitivity perturbation [${pi}] failed:`, err);
        }

        count++;
        setProgress(count / total);
      }
    }

    // Normalize
    OUTPUT_FIELDS.forEach(f => {
      const total = indices[f.id].reduce((s, v) => s + v, 0);
      if (total > 0) {
        indices[f.id] = indices[f.id].map(v => v / total);
      }
    });

    setResultSens({ params, indices });
    setRunning(false);
  }, [props]);

  const handleRun = useCallback(() => {
    switch (mode) {
      case "sweep1d": return runSweep1D();
      case "sweep2d": return runSweep2D();
      case "montecarlo": return runMonteCarlo();
      case "sensitivity": return runSensitivity();
    }
  }, [mode, runSweep1D, runSweep2D, runMonteCarlo, runSensitivity]);

  const modes: { id: ExplorerMode; label: string; desc: string }[] = [
    { id: "sweep1d", label: "1D Sweep", desc: "Vary one parameter, plot response" },
    { id: "sweep2d", label: "2D Sweep", desc: "Vary two parameters, contour map" },
    { id: "montecarlo", label: "Monte Carlo", desc: "Random sampling, statistics" },
    { id: "sensitivity", label: "Sensitivity", desc: "Morris screening, parameter ranking" },
  ];

  const colors = [COL.accent, "#f472b6", "#38bdf8", "#4ade80", "#fb923c", "#a78bfa"];

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Mode selector */}
      <div className="flex gap-1">
        {modes.map(m => (
          <button
            key={m.id}
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all"
            style={{
              background: mode === m.id ? COL.accentMuted : "transparent",
              color: mode === m.id ? COL.accent : COL.textDim,
              border: `1px solid ${mode === m.id ? `${COL.accent}40` : COL.border}`,
            }}
            onClick={() => setMode(m.id)}
            title={m.desc}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="flex items-end gap-3 flex-wrap">
        {(mode === "sweep1d" || mode === "sweep2d") && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px]" style={{ color: COL.textDim }}>
              {mode === "sweep2d" ? "X Parameter" : "Parameter"}
            </label>
            <select
              className="text-[11px] px-2 py-1.5 rounded-md outline-none"
              style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
              value={paramX}
              onChange={(e) => setParamX(e.target.value)}
            >
              {SWEEP_PARAMS.map(p => (
                <option key={p.id} value={p.id}>{p.label} ({p.unit})</option>
              ))}
            </select>
          </div>
        )}

        {mode === "sweep2d" && (
          <div className="flex flex-col gap-1">
            <label className="text-[10px]" style={{ color: COL.textDim }}>Y Parameter</label>
            <select
              className="text-[11px] px-2 py-1.5 rounded-md outline-none"
              style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
              value={paramY}
              onChange={(e) => setParamY(e.target.value)}
            >
              {SWEEP_PARAMS.map(p => (
                <option key={p.id} value={p.id}>{p.label} ({p.unit})</option>
              ))}
            </select>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-[10px]" style={{ color: COL.textDim }}>Output</label>
          <select
            className="text-[11px] px-2 py-1.5 rounded-md outline-none"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            value={outputField}
            onChange={(e) => setOutputField(e.target.value as keyof PredictionResults)}
          >
            {OUTPUT_FIELDS.map(f => (
              <option key={f.id} value={f.id}>{f.label}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[10px]" style={{ color: COL.textDim }}>
            {mode === "montecarlo" ? "Samples" : "Steps"}
          </label>
          <input
            className="text-[11px] px-2 py-1.5 rounded-md outline-none w-16 tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number"
            value={mode === "montecarlo" ? nSamples : nSteps}
            onChange={(e) => mode === "montecarlo" ? setNSamples(Number(e.target.value)) : setNSteps(Number(e.target.value))}
            min={5} max={mode === "montecarlo" ? 1000 : 50}
          />
        </div>

        <button
          className="px-4 py-1.5 rounded-lg text-[11px] font-semibold btn-press"
          style={{
            background: running ? "rgba(255,255,255,0.06)" : COL.accent,
            color: running ? COL.textDim : "#fff",
            border: `1px solid ${running ? COL.border : "rgba(99,102,241,0.3)"}`,
          }}
          onClick={() => {
            if (running) { abortRef.current = true; } else { handleRun(); }
          }}
          disabled={!props.modelsReady && !running}
        >
          {running ? `${Math.round(progress * 100)}% — Stop` : !props.modelsReady ? "Models loading..." : "Run"}
        </button>

        {/* CSV Export */}
        {(result1D || resultMC || resultSens) && !running && (
          <button
            className="px-3 py-1.5 rounded-lg text-[11px] font-semibold btn-press"
            style={{ background: COL.panel, color: COL.textMid, border: `1px solid ${COL.border}` }}
            aria-label="Export results as CSV"
            onClick={() => {
              let csv = "";
              if (result1D && mode === "sweep1d") {
                const cols = ["Parameter Value", ...OUTPUT_FIELDS.map(f => f.label)];
                csv = cols.join(",") + "\n";
                for (let i = 0; i < result1D.paramValues.length; i++) {
                  csv += [result1D.paramValues[i], ...OUTPUT_FIELDS.map(f => result1D.outputs[f.id]?.[i] ?? "")].join(",") + "\n";
                }
              } else if (resultMC && mode === "montecarlo") {
                const cols = OUTPUT_FIELDS.map(f => f.label);
                csv = cols.join(",") + "\n";
                const n = resultMC.outputs[OUTPUT_FIELDS[0].id]?.length ?? 0;
                for (let i = 0; i < n; i++) {
                  csv += OUTPUT_FIELDS.map(f => resultMC.outputs[f.id]?.[i] ?? "").join(",") + "\n";
                }
              }
              if (csv) {
                navigator.clipboard.writeText(csv);
              }
            }}
          >
            📋 Copy CSV
          </button>
        )}
      </div>

      {/* Progress bar */}
      {running && (
        <div className="h-1 rounded-full" style={{ background: "rgba(255,255,255,0.04)" }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${progress * 100}%`, background: COL.accent }} />
        </div>
      )}

      {/* Results */}
      <div className="flex-1 overflow-y-auto">
        {mode === "sweep1d" && result1D && (
          <div className="flex flex-col gap-3">
            <LineChart
              data={[{
                x: result1D.paramValues,
                y: result1D.outputs[outputField] ?? [],
                color: COL.accent,
                label: OUTPUT_FIELDS.find(f => f.id === outputField)?.label ?? "",
              }]}
              title={`${OUTPUT_FIELDS.find(f => f.id === outputField)?.label} vs ${getParamDef(paramX)?.label}`}
              xLabel={`${getParamDef(paramX)?.label} (${getParamDef(paramX)?.unit})`}
              yLabel={OUTPUT_FIELDS.find(f => f.id === outputField)?.label ?? ""}
              width={600} height={280}
            />

            {/* Multi-output overlay */}
            <LineChart
              data={OUTPUT_FIELDS.slice(0, 5).map((f, i) => ({
                x: result1D.paramValues,
                y: result1D.outputs[f.id] ?? [],
                color: colors[i % colors.length],
                label: f.label,
              }))}
              title="All Outputs"
              xLabel={`${getParamDef(paramX)?.label} (${getParamDef(paramX)?.unit})`}
              yLabel="Value"
              width={600} height={280}
            />
          </div>
        )}

        {mode === "sweep2d" && result2D && (
          <HeatmapChart
            xValues={result2D.xValues}
            yValues={result2D.yValues}
            data={result2D.outputs[outputField] ?? []}
            title={`${OUTPUT_FIELDS.find(f => f.id === outputField)?.label}`}
            xLabel={`${getParamDef(paramX)?.label} (${getParamDef(paramX)?.unit})`}
            yLabel={`${getParamDef(paramY)?.label} (${getParamDef(paramY)?.unit})`}
            width={500} height={400}
          />
        )}

        {mode === "montecarlo" && resultMC && (
          <div className="flex flex-col gap-4">
            <Histogram
              values={resultMC.outputs[outputField] ?? []}
              title={`${OUTPUT_FIELDS.find(f => f.id === outputField)?.label} Distribution (n=${nSamples})`}
              width={500} height={200}
            />

            <div className="grid grid-cols-3 gap-3">
              {Object.entries(resultMC.stats).slice(0, 6).map(([key, st]) => (
                <div key={key} className="p-2 rounded-lg" style={{ background: COL.card, border: `1px solid ${COL.border}` }}>
                  <div className="text-[9px] font-semibold" style={{ color: COL.textDim }}>
                    {OUTPUT_FIELDS.find(f => f.id === key)?.label}
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-1 text-[9px]">
                    <span style={{ color: COL.textDim }}>Mean:</span>
                    <span className="tabular-nums text-right" style={{ color: COL.text }}>{st.mean.toFixed(2)}</span>
                    <span style={{ color: COL.textDim }}>Std:</span>
                    <span className="tabular-nums text-right" style={{ color: COL.text }}>{st.std.toFixed(2)}</span>
                    <span style={{ color: COL.textDim }}>P5–P95:</span>
                    <span className="tabular-nums text-right" style={{ color: COL.text }}>{st.p5.toFixed(1)}–{st.p95.toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {mode === "sensitivity" && resultSens && (
          <div className="flex flex-col gap-4">
            <SensitivityBars
              params={resultSens.params.map(p => getParamDef(p)?.label ?? p)}
              indices={resultSens.indices[outputField] ?? []}
              title={`Sensitivity: ${OUTPUT_FIELDS.find(f => f.id === outputField)?.label}`}
              width={500} height={SWEEP_PARAMS.length * 28 + 40}
            />

            <div className="text-[9px]" style={{ color: COL.textDim }}>
              Morris screening method · Normalized elementary effects · {10} repetitions
            </div>
          </div>
        )}

        {/* Empty state */}
        {!running && !result1D && !result2D && !resultMC && !resultSens && (
          <div className="flex items-center justify-center h-48">
            <span className="text-[11px]" style={{ color: COL.textDim }}>
              Configure parameters and click Run to explore the design space
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
