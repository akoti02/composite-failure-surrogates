import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { COL, PLATE_LENGTH, PLATE_WIDTH, DEFECT_COLORS } from "../lib/constants";
import {
  computeStressField,
  renderToImageData,
  extractField,
  mapColor,
  type StressFieldResult,
  type FieldComponent,
  type ColorMap,
} from "../lib/stress-field";
import { MATERIAL_DB, DEFAULT_MATERIAL_ID } from "../lib/materials";
import { parseLaminateCode, expandPlies } from "../lib/clt";
import {
  computeAllPlyFields,
  computeWorstPlyField,
  applyMLScaling,
  extractContours,
  type PlyFieldResult,
  type WorstPlyPoint,
  type ContourLine,
} from "../lib/ply-stress-field";
import type { DefectParams } from "../lib/types";
import type { PredictionResults } from "../lib/types";

type ViewMode = "global" | "ply" | "failure" | "worstPly";

interface Props {
  defects: DefectParams[];
  nDefects: number;
  pressureX: number;
  pressureY: number;
  predictions?: PredictionResults | null;
  laminateCode?: string;
  laminateMaterialId?: string;
}

// Field options per view mode
const GLOBAL_FIELDS: { value: FieldComponent; label: string }[] = [
  { value: "vonMises", label: "von Mises" },
  { value: "sigX", label: "σx (Fibre)" },
  { value: "sigY", label: "σy (Transverse)" },
  { value: "tauXY", label: "τxy (Shear)" },
  { value: "sig1", label: "σ₁ (Principal)" },
  { value: "sig2", label: "σ₂ (Principal)" },
  { value: "maxShear", label: "Max Shear" },
  { value: "tsaiWu", label: "Tsai-Wu Index" },
];

type PlyFieldKey = "sigma1" | "sigma2" | "tau12" | "tsaiWu" | "maxStress" | "hashinFT" | "hashinFC" | "hashinMT" | "hashinMC" | "maxFI";
const PLY_FIELDS: { value: PlyFieldKey; label: string }[] = [
  { value: "sigma1", label: "σ₁ (Material)" },
  { value: "sigma2", label: "σ₂ (Material)" },
  { value: "tau12", label: "τ₁₂ (Material)" },
];

const FAILURE_FIELDS: { value: PlyFieldKey; label: string }[] = [
  { value: "tsaiWu", label: "Tsai-Wu" },
  { value: "maxStress", label: "Max Stress" },
  { value: "hashinFT", label: "Hashin FT" },
  { value: "hashinFC", label: "Hashin FC" },
  { value: "hashinMT", label: "Hashin MT" },
  { value: "hashinMC", label: "Hashin MC" },
  { value: "maxFI", label: "Max FI" },
];

const COLORMAP_OPTIONS: ColorMap[] = ["turbo", "viridis", "plasma", "inferno", "coolwarm", "jet"];

/** Segmented button — defined outside component to avoid remount on every render */
function SegBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      className="px-2.5 py-1 text-[10px] font-semibold transition-all"
      style={{
        background: active ? COL.accent : "transparent",
        color: active ? "#fff" : COL.textDim,
        borderRadius: 4,
      }}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function ColorBar({ min, max, colormap, unit }: { min: number; max: number; colormap: ColorMap; unit: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    for (let x = 0; x < w; x++) {
      const t = x / (w - 1);
      const val = min + t * (max - min);
      const [r, g, b] = mapColor(val, min, max, colormap);
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(x, 0, 1, h);
    }
  }, [min, max, colormap]);

  const fmt = (v: number) => {
    if (Math.abs(v) >= 1000) return v.toFixed(0);
    if (Math.abs(v) >= 100) return v.toFixed(1);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(4);
  };

  return (
    <div className="flex flex-col gap-0.5">
      <canvas ref={canvasRef} width={200} height={12} className="rounded-sm w-full" style={{ height: 10 }} />
      <div className="flex justify-between text-[9px]" style={{ color: COL.textDim }}>
        <span>{fmt(min)} {unit}</span>
        <span>{fmt((min + max) / 2)} {unit}</span>
        <span>{fmt(max)} {unit}</span>
      </div>
    </div>
  );
}

/** Render a 2D array of values to ImageData */
function renderFieldToImageData(
  values: Float64Array,
  nx: number, ny: number,
  width: number, height: number,
  colormap: ColorMap,
  min: number, max: number,
): ImageData {
  const imgData = new ImageData(width, height);
  const pixels = imgData.data;

  for (let py = 0; py < height; py++) {
    for (let px = 0; px < width; px++) {
      const gx = (px / (width - 1)) * (nx - 1);
      const gy = (py / (height - 1)) * (ny - 1);
      const ix = Math.min(Math.floor(gx), nx - 2);
      const iy = Math.min(Math.floor(gy), ny - 2);
      const fx = gx - ix;
      const fy = gy - iy;

      const v00 = values[iy * nx + ix];
      const v10 = values[iy * nx + ix + 1];
      const v01 = values[(iy + 1) * nx + ix];
      const v11 = values[(iy + 1) * nx + ix + 1];
      const val = v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) +
                  v01 * (1 - fx) * fy + v11 * fx * fy;

      const [r, g, b, a] = mapColor(val, min, max, colormap);
      const idx = (py * width + px) * 4;
      pixels[idx] = r;
      pixels[idx + 1] = g;
      pixels[idx + 2] = b;
      pixels[idx + 3] = a;
    }
  }
  return imgData;
}

/** Extract flat array from ply field grid */
function extractPlyFieldData(
  grid: PlyFieldResult["grid"] | WorstPlyPoint[][],
  nx: number, ny: number,
  key: string,
): { data: Float64Array; min: number; max: number } {
  const data = new Float64Array(nx * ny);
  let min = Infinity, max = -Infinity;
  for (let j = 0; j < ny; j++) {
    for (let i = 0; i < nx; i++) {
      const val = (grid[j][i] as unknown as Record<string, number>)[key] ?? 0;
      data[j * nx + i] = val;
      if (val < min) min = val;
      if (val > max) max = val;
    }
  }
  return { data, min, max };
}

export function StressHeatmap({ defects, nDefects, pressureX, pressureY, predictions, laminateCode, laminateMaterialId }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // View state
  const [viewMode, setViewMode] = useState<ViewMode>("global");
  const [field, setField] = useState<FieldComponent>("vonMises");
  const [plyField, setPlyField] = useState<PlyFieldKey>("sigma1");
  const [selectedPly, setSelectedPly] = useState(0);
  const [colormap, setColormap] = useState<ColorMap>("turbo");
  const [resolution, setResolution] = useState(100);
  const [materialId, setMaterialId] = useState(DEFAULT_MATERIAL_ID);

  // Toggles
  const [mlCalibrated, setMlCalibrated] = useState(false);
  const [showContours, setShowContours] = useState(false);

  // Computed state
  const [computing, setComputing] = useState(false);
  const [baseResult, setBaseResult] = useState<StressFieldResult | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number; val: number } | null>(null);

  const material = MATERIAL_DB[materialId];
  const lamMaterial = MATERIAL_DB[laminateMaterialId ?? DEFAULT_MATERIAL_ID];

  // Parse plies from laminate code
  const plyAngles = useMemo(() => {
    const fallback = [0, 45, -45, 90, 90, -45, 45, 0];
    try {
      const def = parseLaminateCode(laminateCode ?? "[0/±45/90]s", laminateMaterialId ?? DEFAULT_MATERIAL_ID);
      const plies = expandPlies(def);
      const angles = plies.map(p => p.angle);
      return angles.length > 0 ? angles : fallback;
    } catch {
      return fallback;
    }
  }, [laminateCode, laminateMaterialId]);

  // Clamp selectedPly when ply count changes
  useEffect(() => {
    if (selectedPly >= plyAngles.length) {
      setSelectedPly(Math.max(0, plyAngles.length - 1));
    }
  }, [plyAngles.length, selectedPly]);

  // ML scaling — uses max_s11 as the calibration target (V11 no longer predicts max_mises)
  const mlScaleResult = useMemo(() => {
    if (!baseResult || !mlCalibrated || !predictions?.max_s11) return null;
    return applyMLScaling(baseResult, predictions.max_s11, material);
  }, [baseResult, mlCalibrated, predictions, material]);

  const effectiveResult = mlScaleResult?.scaled ?? baseResult;

  // Ply fields
  const allPlyFields = useMemo(() => {
    if (!effectiveResult || (viewMode !== "ply" && viewMode !== "failure" && viewMode !== "worstPly")) return null;
    return computeAllPlyFields(effectiveResult, plyAngles, lamMaterial);
  }, [effectiveResult, plyAngles, lamMaterial, viewMode]);

  // Worst ply
  const worstPlyField = useMemo(() => {
    if (!allPlyFields || viewMode !== "worstPly" || !effectiveResult) return null;
    return computeWorstPlyField(allPlyFields, effectiveResult.nx, effectiveResult.ny);
  }, [allPlyFields, viewMode, effectiveResult]);

  // Contour lines
  const contours = useMemo((): ContourLine[] | null => {
    if (!effectiveResult || !showContours) return null;
    const { nx, ny, xMin, xMax, yMin, yMax } = effectiveResult;
    let data: Float64Array;
    if (viewMode === "global") {
      data = extractField(effectiveResult, field).data;
    } else if (viewMode === "worstPly" && worstPlyField) {
      data = extractPlyFieldData(worstPlyField, nx, ny, "maxFI").data;
    } else if ((viewMode === "ply" || viewMode === "failure") && allPlyFields && allPlyFields[selectedPly]) {
      data = extractPlyFieldData(allPlyFields[selectedPly].grid, nx, ny, plyField).data;
    } else {
      return null;
    }
    return extractContours(data, nx, ny, xMin, xMax, yMin, yMax, 10);
  }, [effectiveResult, showContours, viewMode, field, plyField, selectedPly, allPlyFields, worstPlyField]);

  const compute = useCallback(() => {
    if (pressureX === 0 && pressureY === 0) {
      setBaseResult(null);
      return;
    }
    setComputing(true);
    setTimeout(() => {
      const res = computeStressField(
        PLATE_LENGTH, PLATE_WIDTH,
        defects, nDefects,
        pressureX, pressureY,
        material,
        resolution,
      );
      setBaseResult(res);
      setComputing(false);
    }, 50);
  }, [defects, nDefects, pressureX, pressureY, material, resolution]);

  // Render to canvas
  useEffect(() => {
    if (!effectiveResult || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    const { nx, ny } = effectiveResult;

    let imgData: ImageData;

    if (viewMode === "global") {
      imgData = renderToImageData(effectiveResult, field, w, h, colormap);
    } else if (viewMode === "worstPly" && worstPlyField) {
      const { data, min, max } = extractPlyFieldData(worstPlyField, nx, ny, "maxFI");
      imgData = renderFieldToImageData(data, nx, ny, w, h, colormap, min, max);
    } else if ((viewMode === "ply" || viewMode === "failure") && allPlyFields && allPlyFields[selectedPly]) {
      const { data, min, max } = extractPlyFieldData(allPlyFields[selectedPly].grid, nx, ny, plyField);
      imgData = renderFieldToImageData(data, nx, ny, w, h, colormap, min, max);
    } else {
      imgData = renderToImageData(effectiveResult, field, w, h, colormap);
    }

    ctx.putImageData(imgData, 0, 0);

    // Overlay defect outlines
    const scaleX = w / PLATE_LENGTH;
    const scaleY = h / PLATE_WIDTH;

    ctx.lineWidth = 1.5;
    for (let i = 0; i < nDefects; i++) {
      const d = defects[i];
      if (!d) continue;
      ctx.save();
      ctx.translate(d.x * scaleX, d.y * scaleY);
      ctx.rotate((-d.angle * Math.PI) / 180);
      ctx.strokeStyle = DEFECT_COLORS[i];
      ctx.setLineDash([3, 2]);
      ctx.beginPath();
      ctx.ellipse(0, 0, d.half_length * scaleX, (d.width / 2) * scaleY, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Contour lines overlay
    if (showContours && contours && contours.length > 0) {
      ctx.save();
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 0.8;
      ctx.setLineDash([]);

      for (const contour of contours) {
        for (const seg of contour.segments) {
          const px1 = ((seg.x1 - effectiveResult.xMin) / (effectiveResult.xMax - effectiveResult.xMin)) * w;
          const py1 = ((seg.y1 - effectiveResult.yMin) / (effectiveResult.yMax - effectiveResult.yMin)) * h;
          const px2 = ((seg.x2 - effectiveResult.xMin) / (effectiveResult.xMax - effectiveResult.xMin)) * w;
          const py2 = ((seg.y2 - effectiveResult.yMin) / (effectiveResult.yMax - effectiveResult.yMin)) * h;
          ctx.beginPath();
          ctx.moveTo(px1, py1);
          ctx.lineTo(px2, py2);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
  }, [effectiveResult, viewMode, field, plyField, colormap, defects, nDefects, selectedPly, allPlyFields, worstPlyField, showContours, contours]);

  // Mouse hover for value probe
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!effectiveResult || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * PLATE_LENGTH;
    const py = ((e.clientY - rect.top) / rect.height) * PLATE_WIDTH;

    const { nx, ny } = effectiveResult;
    const ix = Math.min(Math.max(Math.round((px / PLATE_LENGTH) * (nx - 1)), 0), nx - 1);
    const iy = Math.min(Math.max(Math.round((py / PLATE_WIDTH) * (ny - 1)), 0), ny - 1);

    let val = 0;
    if (viewMode === "global") {
      val = effectiveResult.grid[iy]?.[ix]?.[field] ?? 0;
    } else if (viewMode === "worstPly" && worstPlyField) {
      val = worstPlyField[iy]?.[ix]?.maxFI ?? 0;
    } else if ((viewMode === "ply" || viewMode === "failure") && allPlyFields?.[selectedPly]) {
      val = (allPlyFields[selectedPly].grid[iy]?.[ix] as unknown as Record<string, number>)?.[plyField] ?? 0;
    }
    setMousePos({ x: px, y: py, val });
  }, [effectiveResult, viewMode, field, plyField, selectedPly, allPlyFields, worstPlyField]);

  // Get current field info for color bar
  const currentFieldInfo = useMemo(() => {
    if (!effectiveResult) return null;
    const { nx, ny } = effectiveResult;
    if (viewMode === "global") {
      return extractField(effectiveResult, field);
    } else if (viewMode === "worstPly" && worstPlyField) {
      return extractPlyFieldData(worstPlyField, nx, ny, "maxFI");
    } else if ((viewMode === "ply" || viewMode === "failure") && allPlyFields?.[selectedPly]) {
      return extractPlyFieldData(allPlyFields[selectedPly].grid, nx, ny, plyField);
    }
    return null;
  }, [effectiveResult, viewMode, field, plyField, selectedPly, allPlyFields, worstPlyField]);

  // Determine unit based on active view + active field
  const unit = useMemo(() => {
    if (viewMode === "worstPly") return ""; // failure index
    if (viewMode === "failure") return ""; // failure indices are dimensionless
    if (viewMode === "ply") return "MPa"; // ply stresses are always MPa
    // global mode
    return field === "tsaiWu" ? "" : "MPa";
  }, [viewMode, field]);

  const hasMLPrediction = predictions?.max_s11 != null && isFinite(predictions.max_s11!);

  return (
    <div className="flex flex-col h-full gap-2">
      {/* Row 1: View mode + field selectors */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* View mode segmented control */}
        <div className="flex rounded-md overflow-hidden" style={{ background: COL.panel, border: `1px solid ${COL.border}` }}>
          <SegBtn active={viewMode === "global"} onClick={() => setViewMode("global")}>Global</SegBtn>
          <SegBtn active={viewMode === "ply"} onClick={() => setViewMode("ply")}>Ply</SegBtn>
          <SegBtn active={viewMode === "failure"} onClick={() => setViewMode("failure")}>Failure</SegBtn>
          <SegBtn active={viewMode === "worstPly"} onClick={() => setViewMode("worstPly")}>Worst Ply</SegBtn>
        </div>

        {/* Field selector — context-aware */}
        {viewMode === "global" && (
          <select
            className="text-[11px] px-2 py-1 rounded-md outline-none"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            value={field}
            onChange={(e) => setField(e.target.value as FieldComponent)}
          >
            {GLOBAL_FIELDS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        )}

        {viewMode === "ply" && (
          <select
            className="text-[11px] px-2 py-1 rounded-md outline-none"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            value={plyField}
            onChange={(e) => setPlyField(e.target.value as PlyFieldKey)}
          >
            {PLY_FIELDS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        )}

        {viewMode === "failure" && (
          <select
            className="text-[11px] px-2 py-1 rounded-md outline-none"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            value={plyField}
            onChange={(e) => setPlyField(e.target.value as PlyFieldKey)}
          >
            {FAILURE_FIELDS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        )}

        {/* Ply selector — when in ply or failure mode */}
        {(viewMode === "ply" || viewMode === "failure") && (
          <div className="flex items-center gap-1.5">
            <span className="text-[10px]" style={{ color: COL.textDim }}>Ply:</span>
            <select
              className="text-[11px] px-2 py-1 rounded-md outline-none"
              style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
              value={selectedPly}
              onChange={(e) => setSelectedPly(Number(e.target.value))}
            >
              {plyAngles.map((angle, i) => (
                <option key={i} value={i}>#{i + 1} ({angle}°)</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Row 2: Resolution, Material, Colormap, Toggles, Compute */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px]" style={{ color: COL.textDim }}>Grid:</span>
          <input
            type="range" min={20} max={120} step={10} value={resolution}
            className="w-16 accent-indigo-500"
            onChange={(e) => setResolution(Number(e.target.value))}
          />
          <span className="text-[10px] tabular-nums w-8" style={{ color: COL.textMid }}>{resolution}</span>
        </div>

        <select
          className="text-[11px] px-2 py-1 rounded-md outline-none"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
          value={materialId}
          onChange={(e) => setMaterialId(e.target.value)}
        >
          {Object.keys(MATERIAL_DB).map(id => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>

        <select
          className="text-[11px] px-2 py-1 rounded-md outline-none"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
          value={colormap}
          onChange={(e) => setColormap(e.target.value as ColorMap)}
        >
          {COLORMAP_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        {/* Toggle: ML calibration */}
        {hasMLPrediction && (
          <label className="flex items-center gap-1 text-[10px] cursor-pointer" style={{ color: mlCalibrated ? COL.accent : COL.textDim }}>
            <input type="checkbox" checked={mlCalibrated} onChange={(e) => setMlCalibrated(e.target.checked)} className="accent-indigo-500" />
            ML
          </label>
        )}

        {/* Toggle: Contours */}
        <label className="flex items-center gap-1 text-[10px] cursor-pointer" style={{ color: showContours ? COL.accent : COL.textDim }}>
          <input type="checkbox" checked={showContours} onChange={(e) => setShowContours(e.target.checked)} className="accent-indigo-500" />
          Contours
        </label>

        <button
          className="px-3 py-1 rounded-md text-[11px] font-semibold btn-press ml-auto"
          style={{
            background: computing ? "rgba(255,255,255,0.06)" : COL.accent,
            color: computing ? COL.textDim : "#fff",
            border: `1px solid ${computing ? COL.border : "rgba(99,102,241,0.3)"}`,
            cursor: computing ? "not-allowed" : "pointer",
          }}
          onClick={compute}
          disabled={computing}
        >
          {computing ? "Computing..." : "Compute"}
        </button>
      </div>

      {/* Canvas area */}
      <div className="flex-1 min-h-0 flex gap-3">
        <div className="flex-1 relative rounded-lg overflow-hidden" style={{ background: COL.canvasBg, border: `1px solid ${COL.border}` }}>
          <canvas
            ref={canvasRef}
            width={Math.min(1200 * (typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1), 2400)}
            height={Math.min(600 * (typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1), 1200)}
            className="w-full h-full"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setMousePos(null)}
          />

          {/* Value probe tooltip */}
          {mousePos && (
            <div
              className="absolute pointer-events-none px-2 py-1 rounded text-[10px]"
              style={{
                left: `${(mousePos.x / PLATE_LENGTH) * 100}%`,
                top: 4,
                background: "rgba(0,0,0,0.8)",
                color: COL.text,
                border: `1px solid ${COL.border}`,
                transform: "translateX(-50%)",
                whiteSpace: "nowrap",
              }}
            >
              ({mousePos.x.toFixed(1)}, {mousePos.y.toFixed(1)}) mm
              &nbsp;&rarr;&nbsp;
              <strong>{mousePos.val.toFixed(2)} {unit}</strong>
            </div>
          )}

          {/* No data state */}
          {!baseResult && !computing && (
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-[11px]" style={{ color: COL.textDim }}>
                Set loads and click Compute to generate stress field
              </span>
            </div>
          )}

          {/* ML badge */}
          {mlCalibrated && mlScaleResult && (
            <div
              className="absolute top-2 right-2 px-2 py-0.5 rounded text-[9px] font-semibold"
              style={{ background: "rgba(99,102,241,0.2)", color: COL.accent2, border: `1px solid rgba(99,102,241,0.3)` }}
            >
              ML-Calibrated &times;{mlScaleResult.factor.toFixed(2)}
            </div>
          )}
        </div>

        {/* Sidebar: color bar + stats */}
        <div className="w-44 shrink-0 flex flex-col gap-3 overflow-y-auto">
          {effectiveResult && (
            <>
              <ColorBar min={currentFieldInfo?.min ?? 0} max={currentFieldInfo?.max ?? 1} colormap={colormap} unit={unit} />

              <div className="flex flex-col gap-1">
                <div className="text-[10px] font-semibold" style={{ color: COL.textMid }}>Field Statistics</div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>Min:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{(currentFieldInfo?.min ?? 0).toFixed(2)} {unit}</span>
                </div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>Max:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{(currentFieldInfo?.max ?? 0).toFixed(2)} {unit}</span>
                </div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>Range:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{((currentFieldInfo?.max ?? 0) - (currentFieldInfo?.min ?? 0)).toFixed(2)}</span>
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <div className="text-[10px] font-semibold" style={{ color: COL.textMid }}>Peak Stresses</div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>von Mises:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{effectiveResult.globalMax.vonMises.toFixed(1)} MPa</span>
                </div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>σx max:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{effectiveResult.globalMax.sigX.toFixed(1)} MPa</span>
                </div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>σy max:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{effectiveResult.globalMax.sigY.toFixed(1)} MPa</span>
                </div>
                <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                  <span>|τxy| max:</span>
                  <span className="tabular-nums" style={{ color: COL.text }}>{effectiveResult.globalMax.tauXY.toFixed(1)} MPa</span>
                </div>
              </div>

              {/* Ply info */}
              {(viewMode === "ply" || viewMode === "failure") && allPlyFields?.[selectedPly] && (
                <div className="flex flex-col gap-1">
                  <div className="text-[10px] font-semibold" style={{ color: COL.textMid }}>
                    Ply #{selectedPly + 1} ({plyAngles[selectedPly]}°)
                  </div>
                  <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                    <span>Peak FI:</span>
                    <span className="tabular-nums" style={{
                      color: allPlyFields[selectedPly].maxFI >= 1 ? COL.danger : allPlyFields[selectedPly].maxFI >= 0.8 ? COL.warning : COL.success,
                    }}>
                      {allPlyFields[selectedPly].maxFI.toFixed(3)}
                    </span>
                  </div>
                  <div className="flex justify-between text-[10px]" style={{ color: COL.textDim }}>
                    <span>Mode:</span>
                    <span style={{ color: COL.text }}>{allPlyFields[selectedPly].dominantMode}</span>
                  </div>
                </div>
              )}

              {/* Worst ply summary */}
              {viewMode === "worstPly" && allPlyFields && (
                <div className="flex flex-col gap-1">
                  <div className="text-[10px] font-semibold" style={{ color: COL.textMid }}>Ply Failure Summary</div>
                  {allPlyFields.map((pf, i) => (
                    <div key={i} className="flex justify-between text-[9px]" style={{ color: COL.textDim }}>
                      <span>#{i + 1} ({pf.angle}°)</span>
                      <span className="tabular-nums" style={{
                        color: pf.maxFI >= 1 ? COL.danger : pf.maxFI >= 0.8 ? COL.warning : COL.text,
                      }}>
                        {pf.maxFI.toFixed(3)}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Laminate info */}
              {viewMode !== "global" && (
                <div className="flex flex-col gap-0.5 text-[9px]" style={{ color: COL.textDim }}>
                  <span>Laminate: {laminateCode ?? "[0/±45/90]s"}</span>
                  <span>Material: {laminateMaterialId ?? DEFAULT_MATERIAL_ID}</span>
                  <span>{plyAngles.length} plies</span>
                </div>
              )}

              <div className="text-[9px] mt-auto" style={{ color: COL.textDim }}>
                Lekhnitskii anisotropic solution · {effectiveResult.nx}×{effectiveResult.ny} grid
                {mlCalibrated && mlScaleResult ? ` · ML ×${mlScaleResult.factor.toFixed(2)}` : ""}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
