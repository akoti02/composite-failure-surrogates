import { useState, useMemo } from "react";
import { COL } from "../lib/constants";
import { MATERIAL_DB, DEFAULT_MATERIAL_ID, type MaterialProperties } from "../lib/materials";
import {
  parseLaminateCode, expandPlies, analyzeLaminate, progressiveFailure,
  LAMINATE_PRESETS, type PlyDef, type ABDResult, type PlyResult,
} from "../lib/clt";

/** Polar plot of stiffness for laminate visualization */
function StiffnessPolar({ abd }: { abd: ABDResult }) {
  const w = 220, h = 220;
  const cx = w / 2, cy = h / 2;
  const r = 90;

  // Compute normalized A11(θ) polar plot
  const points: string[] = [];
  const { A } = abd;

  // First pass: find max Ath for normalization
  let maxAth = 0;
  for (let deg = 0; deg <= 360; deg += 3) {
    const theta = (deg * Math.PI) / 180;
    const c = Math.cos(theta), s = Math.sin(theta);
    const c2 = c * c, s2 = s * s, cs = c * s;
    const Ath = A[0][0] * c2 * c2 + 2 * (A[0][1] + 2 * A[2][2]) * c2 * s2 + A[1][1] * s2 * s2
      + 4 * A[0][2] * c2 * cs + 4 * A[1][2] * s2 * cs;
    if (Math.abs(Ath) > maxAth) maxAth = Math.abs(Ath);
  }
  if (maxAth < 1e-10) maxAth = 1;

  // Second pass: plot
  for (let deg = 0; deg <= 360; deg += 3) {
    const theta = (deg * Math.PI) / 180;
    const c = Math.cos(theta), s = Math.sin(theta);
    const c2 = c * c, s2 = s * s, cs = c * s;
    const Ath = A[0][0] * c2 * c2 + 2 * (A[0][1] + 2 * A[2][2]) * c2 * s2 + A[1][1] * s2 * s2
      + 4 * A[0][2] * c2 * cs + 4 * A[1][2] * s2 * cs;
    const rr = (Math.abs(Ath) / maxAth) * r * 0.85;
    const px = cx + rr * c;
    const py = cy - rr * s;
    points.push(`${px.toFixed(1)},${py.toFixed(1)}`);
  }

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {/* Concentric circles */}
      {[0.25, 0.5, 0.75, 1].map(f => (
        <circle key={f} cx={cx} cy={cy} r={r * f} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={0.5} />
      ))}
      {/* Axes */}
      <line x1={cx - r} y1={cy} x2={cx + r} y2={cy} stroke="rgba(255,255,255,0.08)" strokeWidth={0.5} />
      <line x1={cx} y1={cy - r} x2={cx} y2={cy + r} stroke="rgba(255,255,255,0.08)" strokeWidth={0.5} />
      {/* Labels */}
      <text x={cx + r + 4} y={cy + 3} fill={COL.textDim} fontSize={8}>0°</text>
      <text x={cx - 2} y={cy - r - 4} fill={COL.textDim} fontSize={8} textAnchor="middle">90°</text>
      {/* Polar curve */}
      <polygon points={points.join(" ")} fill="rgba(99,102,241,0.15)" stroke={COL.accent} strokeWidth={1.5} />
    </svg>
  );
}

/** Ply stack visualization — horizontal layout */
function PlyStackViz({ plies, materials, results }: {
  plies: PlyDef[]; materials: Record<string, MaterialProperties>; results?: PlyResult[];
}) {
  const n = plies.length;
  if (n === 0) return null;

  const plyH = Math.min(18, Math.max(14, 160 / n));
  const totalH = plyH * n;
  const w = 500;
  const barLeft = 24;
  const barRight = 50; // space for angle label

  // Angle → hue mapping
  const angleColor = (angle: number) => {
    const hue = ((angle + 90) / 180) * 300;
    return `hsl(${hue}, 60%, 50%)`;
  };

  return (
    <div>
      <div className="text-[10px] font-semibold mb-1" style={{ color: COL.textMid }}>
        Ply Stack ({n} plies, {(plies.reduce((s, p) => s + (p.thickness ?? materials[p.materialId]?.plyThickness ?? 0.125), 0)).toFixed(2)} mm)
      </div>
      <svg width="100%" viewBox={`0 0 ${w} ${totalH + 4}`} style={{ maxWidth: w }}>
        {plies.map((ply, i) => {
          const y = 2 + i * plyH;
          const failed = results?.[i]?.failed;
          const fi = results?.[i] ? Math.max(results[i].tsaiWu, results[i].maxStress) : 0;
          const bgOpacity = failed ? 0.5 : 0.2;
          const barW = w - barLeft - barRight;

          return (
            <g key={i}>
              <rect
                x={barLeft} y={y} width={barW} height={plyH - 2}
                fill={angleColor(ply.angle)}
                fillOpacity={bgOpacity}
                stroke={failed ? COL.danger : "rgba(255,255,255,0.1)"}
                strokeWidth={failed ? 1.5 : 0.5}
                rx={2}
              />
              {/* Fiber direction lines */}
              <g clipPath={`url(#clip-${i})`}>
                <clipPath id={`clip-${i}`}>
                  <rect x={barLeft} y={y} width={barW} height={plyH - 2} rx={2} />
                </clipPath>
                {Array.from({ length: 20 }, (_, j) => {
                  const cx = barLeft + barW / 2;
                  const cy = y + (plyH - 2) / 2;
                  const rad = (ply.angle * Math.PI) / 180;
                  const dx = Math.cos(rad) * 300;
                  const dy = -Math.sin(rad) * 300;
                  const offset = (j - 10) * 8;
                  return (
                    <line
                      key={j}
                      x1={cx - dx + offset * Math.sin(rad)} y1={cy - dy - offset * Math.cos(rad)}
                      x2={cx + dx + offset * Math.sin(rad)} y2={cy + dy - offset * Math.cos(rad)}
                      stroke={angleColor(ply.angle)} strokeOpacity={0.3} strokeWidth={0.5}
                    />
                  );
                })}
              </g>
              {/* Ply number label */}
              <text x={barLeft - 4} y={y + plyH / 2} fill={COL.textDim} fontSize={8} textAnchor="end" dominantBaseline="central">
                {i + 1}
              </text>
              {/* Angle label */}
              <text x={barLeft + barW + 4} y={y + plyH / 2} fill={COL.textMid} fontSize={9} textAnchor="start" dominantBaseline="central">
                {ply.angle}°
              </text>
              {/* Failure index in bar center */}
              {fi > 0 && (
                <text x={barLeft + barW / 2} y={y + plyH / 2} fill={fi >= 1 ? COL.danger : COL.textDim} fontSize={8} textAnchor="middle" dominantBaseline="central">
                  FI={fi.toFixed(2)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** ABD Matrix display */
function ABDDisplay({ abd }: { abd: ABDResult }) {
  const fmtCell = (v: number) => {
    if (Math.abs(v) < 0.001) return "0";
    if (Math.abs(v) >= 10000) return v.toExponential(2);
    return v.toFixed(2);
  };

  const matrixBlock = (label: string, mat: number[][], unit: string) => (
    <div className="flex flex-col gap-0.5">
      <div className="text-[10px] font-semibold" style={{ color: COL.textMid }}>{label} <span style={{ color: COL.textDim }}>({unit})</span></div>
      <div className="grid grid-cols-3 gap-px rounded overflow-hidden" style={{ background: COL.border }}>
        {mat.flat().map((v, i) => (
          <div
            key={i}
            className="text-[9px] tabular-nums px-1.5 py-1 text-center"
            style={{
              background: Math.abs(v) < 0.001 ? COL.bgDark : COL.card,
              color: Math.abs(v) < 0.001 ? COL.textDim : COL.text,
            }}
          >
            {fmtCell(v)}
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-3">
        {matrixBlock("[A]", abd.A, "N/mm")}
        {matrixBlock("[B]", abd.B, "N")}
        {matrixBlock("[D]", abd.D, "N·mm")}
      </div>
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: "Ex", value: abd.Ex, unit: "GPa" },
          { label: "Ey", value: abd.Ey, unit: "GPa" },
          { label: "Gxy", value: abd.Gxy, unit: "GPa" },
          { label: "νxy", value: abd.vxy, unit: "" },
        ].map(({ label, value, unit }) => (
          <div key={label} className="px-2 py-1.5 rounded-md" style={{ background: COL.card, border: `1px solid ${COL.border}` }}>
            <div className="text-[9px]" style={{ color: COL.textDim }}>{label}</div>
            <div className="text-[12px] font-semibold tabular-nums" style={{ color: COL.text }}>
              {value.toFixed(2)} <span className="text-[9px] font-normal" style={{ color: COL.textDim }}>{unit}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Progressive failure curve */
function FailureCurve({ curve }: { curve: { loadFactor: number; maxFI: number; failedPlies: number }[] }) {
  const w = 360, h = 160;
  const mx = 40, my = 20;
  const pw = w - mx * 2, ph = h - my * 2;

  const maxLF = Math.max(...curve.map(c => c.loadFactor));
  const maxFI = Math.max(...curve.map(c => c.maxFI), 1.5);

  const points = curve.map(c => {
    const x = mx + (c.loadFactor / maxLF) * pw;
    const y = my + ph - (Math.min(c.maxFI, maxFI) / maxFI) * ph;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  // Find FPF point (first point where maxFI >= 1)
  const fpfIdx = curve.findIndex(c => c.maxFI >= 1);
  const fpf = fpfIdx >= 0 ? curve[fpfIdx] : null;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {/* Grid */}
      <rect x={mx} y={my} width={pw} height={ph} fill="none" stroke="rgba(255,255,255,0.06)" />
      {/* FI = 1 threshold line */}
      <line
        x1={mx} y1={my + ph - (1 / maxFI) * ph}
        x2={mx + pw} y2={my + ph - (1 / maxFI) * ph}
        stroke={COL.danger} strokeWidth={0.5} strokeDasharray="4,3" strokeOpacity={0.5}
      />
      <text x={mx + pw + 4} y={my + ph - (1 / maxFI) * ph + 3} fill={COL.danger} fontSize={8} fillOpacity={0.6}>FI=1</text>

      {/* Curve */}
      <polyline points={points} fill="none" stroke={COL.accent} strokeWidth={1.5} />

      {/* FPF marker */}
      {fpf && (
        <>
          <circle
            cx={mx + (fpf.loadFactor / maxLF) * pw}
            cy={my + ph - (Math.min(fpf.maxFI, maxFI) / maxFI) * ph}
            r={3} fill={COL.danger} stroke="#fff" strokeWidth={0.5}
          />
          <text
            x={mx + (fpf.loadFactor / maxLF) * pw + 6}
            y={my + ph - (Math.min(fpf.maxFI, maxFI) / maxFI) * ph - 4}
            fill={COL.danger} fontSize={8}
          >
            FPF @ {fpf.loadFactor.toFixed(2)}x
          </text>
        </>
      )}

      {/* Axes labels */}
      <text x={w / 2} y={h - 2} fill={COL.textDim} fontSize={9} textAnchor="middle">Load Factor</text>
      <text x={8} y={h / 2} fill={COL.textDim} fontSize={9} textAnchor="middle" transform={`rotate(-90, 8, ${h / 2})`}>Max FI</text>

      {/* Tick labels */}
      {[0, 0.5, 1, 1.5, 2].map(lf => (
        <text key={lf} x={mx + (lf / maxLF) * pw} y={my + ph + 12} fill={COL.textDim} fontSize={8} textAnchor="middle">
          {lf.toFixed(1)}
        </text>
      ))}
    </svg>
  );
}

interface LaminateBuilderProps {
  laminateCode?: string;
  onLaminateCodeChange?: (code: string) => void;
  materialId?: string;
  onMaterialIdChange?: (id: string) => void;
}

export function LaminateBuilder(props: LaminateBuilderProps) {
  const [internalCode, setInternalCode] = useState("[0/±45/90]s");
  const [internalMatId, setInternalMatId] = useState(DEFAULT_MATERIAL_ID);

  const laminateCode = props.laminateCode ?? internalCode;
  const setLaminateCode = (v: string) => { props.onLaminateCodeChange?.(v); setInternalCode(v); };
  const materialId = props.materialId ?? internalMatId;
  const setMaterialId = (v: string) => { props.onMaterialIdChange?.(v); setInternalMatId(v); };
  const [Nx, setNx] = useState(100);
  const [Ny, setNy] = useState(0);
  const [Nxy, setNxy] = useState(0);
  const [Mx, setMx] = useState(0);
  const [My, setMy] = useState(0);
  const [Mxy, setMxy] = useState(0);
  const [showProgressive, setShowProgressive] = useState(false);
  const [analysisTab, setAnalysisTab] = useState<"stiffness" | "stress" | "failure">("stiffness");

  const materials = MATERIAL_DB;

  // Parse laminate and run analysis
  const analysis = useMemo(() => {
    try {
      const def = parseLaminateCode(laminateCode, materialId);
      const plies = expandPlies(def);
      if (plies.length === 0) return null;

      const result = analyzeLaminate(plies, materials, Nx, Ny, Nxy, Mx, My, Mxy);

      // Progressive failure
      let progCurve: { loadFactor: number; maxFI: number; failedPlies: number }[] | null = null;
      if (showProgressive && (Nx !== 0 || Ny !== 0 || Nxy !== 0)) {
        const pliesCopy = expandPlies(def); // fresh copy
        progCurve = progressiveFailure(pliesCopy, { ...materials }, Nx, Ny, Nxy);
      }

      return { def, plies, result, progCurve };
    } catch {
      return null;
    }
  }, [laminateCode, materialId, Nx, Ny, Nxy, Mx, My, Mxy, materials, showProgressive]);

  const tabs = [
    { id: "stiffness" as const, label: "Stiffness" },
    { id: "stress" as const, label: "Ply Stress" },
    { id: "failure" as const, label: "Failure" },
  ];

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Top controls */}
      <div className="flex gap-3 items-end flex-wrap">
        <div className="flex flex-col gap-1">
          <label className="text-[10px]" style={{ color: COL.textDim }}>Laminate Code</label>
          <input
            className="text-[12px] font-mono px-2.5 py-1.5 rounded-md outline-none w-48"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            value={laminateCode}
            onChange={(e) => setLaminateCode(e.target.value)}
            placeholder="[0/±45/90]s"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[10px]" style={{ color: COL.textDim }}>Material</label>
          <select
            className="text-[11px] px-2 py-1.5 rounded-md outline-none"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            value={materialId}
            onChange={(e) => setMaterialId(e.target.value)}
          >
            {Object.keys(materials).map(id => (
              <option key={id} value={id}>{id}{id !== "T300/5208" ? " (analytical only)" : ""}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[10px]" style={{ color: COL.textDim }}>Preset</label>
          <select
            className="text-[11px] px-2 py-1.5 rounded-md outline-none"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            value=""
            onChange={(e) => { if (e.target.value) setLaminateCode(LAMINATE_PRESETS[e.target.value]); e.target.value = ""; }}
          >
            <option value="" disabled>Select preset...</option>
            {Object.entries(LAMINATE_PRESETS).map(([name, code]) => (
              <option key={name} value={name}>{name} → {code}</option>
            ))}
          </select>
        </div>

        {analysis && (
          <div className="text-[10px] ml-auto" style={{ color: COL.textDim }}>
            {analysis.plies.length} plies · {analysis.result.abd.totalThickness.toFixed(2)} mm
          </div>
        )}
      </div>

      {/* Loads */}
      <div className="grid grid-cols-6 gap-2">
        <div className="flex flex-col gap-0.5">
          <label className="text-[9px]" style={{ color: COL.textDim }}>Nx (N/mm)</label>
          <input className="text-[11px] px-2 py-1 rounded-md outline-none tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number" value={Nx} onChange={(e) => setNx(Number(e.target.value))} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[9px]" style={{ color: COL.textDim }}>Ny (N/mm)</label>
          <input className="text-[11px] px-2 py-1 rounded-md outline-none tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number" value={Ny} onChange={(e) => setNy(Number(e.target.value))} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[9px]" style={{ color: COL.textDim }}>Nxy (N/mm)</label>
          <input className="text-[11px] px-2 py-1 rounded-md outline-none tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number" value={Nxy} onChange={(e) => setNxy(Number(e.target.value))} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[9px]" style={{ color: COL.textDim }}>Mx (N·mm/mm)</label>
          <input className="text-[11px] px-2 py-1 rounded-md outline-none tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number" value={Mx} onChange={(e) => setMx(Number(e.target.value))} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[9px]" style={{ color: COL.textDim }}>My (N·mm/mm)</label>
          <input className="text-[11px] px-2 py-1 rounded-md outline-none tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number" value={My} onChange={(e) => setMy(Number(e.target.value))} />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-[9px]" style={{ color: COL.textDim }}>Mxy (N·mm/mm)</label>
          <input className="text-[11px] px-2 py-1 rounded-md outline-none tabular-nums"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            type="number" value={Mxy} onChange={(e) => setMxy(Number(e.target.value))} />
        </div>
      </div>

      {/* Analysis tabs */}
      <div className="flex gap-1 border-b" style={{ borderColor: COL.border }}>
        {tabs.map(t => (
          <button
            key={t.id}
            className="px-3 py-1.5 text-[11px] font-semibold transition-colors"
            style={{
              color: analysisTab === t.id ? COL.accent : COL.textDim,
              borderBottom: analysisTab === t.id ? `2px solid ${COL.accent}` : "2px solid transparent",
            }}
            onClick={() => setAnalysisTab(t.id)}
          >
            {t.label}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 text-[10px] cursor-pointer" style={{ color: COL.textDim }}>
          <input type="checkbox" checked={showProgressive} onChange={(e) => setShowProgressive(e.target.checked)} className="accent-indigo-500" />
          Progressive failure
        </label>
      </div>

      {/* Analysis content */}
      {!analysis ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[11px]" style={{ color: COL.textDim }}>
            Enter a valid laminate code (e.g., [0/±45/90]s)
          </span>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto flex flex-col gap-4">
          {analysisTab === "stiffness" && (
            <div className="flex flex-col gap-4">
              <div className="flex gap-4">
                <div className="flex-1 min-w-0">
                  <ABDDisplay abd={analysis.result.abd} />
                </div>
                <div className="shrink-0 flex flex-col items-center gap-1">
                  <div className="text-[10px] font-semibold" style={{ color: COL.textMid }}>Stiffness Polar</div>
                  <StiffnessPolar abd={analysis.result.abd} />
                </div>
              </div>
              <PlyStackViz plies={analysis.plies} materials={materials} />
            </div>
          )}

          {analysisTab === "stress" && (
            <div className="flex flex-col gap-4">
              <div>
                <div className="text-[10px] font-semibold mb-2" style={{ color: COL.textMid }}>
                  Ply Stresses (Material Axes)
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-[10px]" style={{ borderCollapse: "separate", borderSpacing: "0 1px" }}>
                    <thead>
                      <tr style={{ color: COL.textDim }}>
                        <th className="text-left px-2 py-1">#</th>
                        <th className="text-right px-2">θ</th>
                        <th className="text-right px-2">σ₁</th>
                        <th className="text-right px-2">σ₂</th>
                        <th className="text-right px-2">τ₁₂</th>
                        <th className="text-right px-2">Tsai-Wu</th>
                        <th className="text-right px-2">Max σ</th>
                        <th className="text-center px-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.result.plies.map((p, i) => (
                        <tr key={i} style={{
                          background: p.failed ? "rgba(248,113,113,0.06)" : i % 2 === 0 ? COL.card : "transparent",
                          color: COL.text,
                        }}>
                          <td className="px-2 py-1" style={{ color: COL.textDim }}>{i + 1}</td>
                          <td className="text-right px-2 tabular-nums">{p.angle}°</td>
                          <td className="text-right px-2 tabular-nums">{p.sigma1.toFixed(1)}</td>
                          <td className="text-right px-2 tabular-nums">{p.sigma2.toFixed(1)}</td>
                          <td className="text-right px-2 tabular-nums">{p.tau12.toFixed(1)}</td>
                          <td className="text-right px-2 tabular-nums" style={{ color: p.tsaiWu >= 1 ? COL.danger : COL.text }}>
                            {p.tsaiWu.toFixed(3)}
                          </td>
                          <td className="text-right px-2 tabular-nums" style={{ color: p.maxStress >= 1 ? COL.danger : COL.text }}>
                            {p.maxStress.toFixed(3)}
                          </td>
                          <td className="text-center px-2">
                            {p.failed ? (
                              <span style={{ color: COL.danger, fontSize: 9 }}>{p.failureMode}</span>
                            ) : (
                              <span style={{ color: COL.success }}>OK</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-2 text-[10px] flex gap-4 flex-wrap" style={{ color: COL.textDim }}>
                  <span>ε₀: [{analysis.result.midplaneStrain.map(v => v.toExponential(3)).join(", ")}]</span>
                  <span>κ: [{analysis.result.midplaneCurvature.map(v => v.toExponential(3)).join(", ")}] /mm</span>
                </div>
              </div>
              <PlyStackViz plies={analysis.plies} materials={materials} results={analysis.result.plies} />
            </div>
          )}

          {analysisTab === "failure" && (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 rounded-lg" style={{
                  background: analysis.result.firstPlyFailure
                    ? analysis.result.firstPlyFailure.load < 1 ? COL.critBg : COL.warnBg
                    : COL.safeBg,
                  border: `1px solid ${COL.border}`,
                }}>
                  <div className="text-[9px]" style={{ color: COL.textDim }}>First Ply Failure</div>
                  <div className="text-[16px] font-bold tabular-nums" style={{
                    color: analysis.result.firstPlyFailure
                      ? analysis.result.firstPlyFailure.load < 1 ? COL.danger : COL.warning
                      : COL.success,
                  }}>
                    {analysis.result.firstPlyFailure
                      ? `${analysis.result.firstPlyFailure.load.toFixed(3)}×`
                      : "No failure"}
                  </div>
                  {analysis.result.firstPlyFailure && (
                    <div className="text-[9px] mt-0.5" style={{ color: COL.textDim }}>
                      Ply {analysis.result.firstPlyFailure.plyIndex + 1} · {analysis.result.firstPlyFailure.mode}
                    </div>
                  )}
                </div>

                <div className="p-3 rounded-lg" style={{ background: COL.card, border: `1px solid ${COL.border}` }}>
                  <div className="text-[9px]" style={{ color: COL.textDim }}>Last Ply Failure</div>
                  <div className="text-[16px] font-bold tabular-nums" style={{ color: COL.text }}>
                    {analysis.result.lastPlyFailure ? `${analysis.result.lastPlyFailure.load.toFixed(3)}×` : "--"}
                  </div>
                  <div className="text-[9px] mt-0.5" style={{ color: COL.textDim }}>
                    FPF/LPF ratio: {analysis.result.firstPlyFailure && analysis.result.lastPlyFailure
                      ? (analysis.result.lastPlyFailure.load / analysis.result.firstPlyFailure.load).toFixed(2)
                      : "--"}
                  </div>
                </div>

                <div className="p-3 rounded-lg" style={{ background: COL.card, border: `1px solid ${COL.border}` }}>
                  <div className="text-[9px]" style={{ color: COL.textDim }}>Failed Plies</div>
                  <div className="text-[16px] font-bold tabular-nums" style={{
                    color: analysis.result.plies.some(p => p.failed) ? COL.danger : COL.success,
                  }}>
                    {analysis.result.plies.filter(p => p.failed).length} / {analysis.result.plies.length}
                  </div>
                  <div className="text-[9px] mt-0.5" style={{ color: COL.textDim }}>
                    at applied load
                  </div>
                </div>
              </div>

              {/* Hashin modes bar chart */}
              <div>
                <div className="text-[10px] font-semibold mb-2" style={{ color: COL.textMid }}>Hashin Damage Mode Peak Indices</div>
                {["Fibre Tension", "Fibre Compression", "Matrix Tension", "Matrix Compression"].map((mode, mi) => {
                  const keys: (keyof PlyResult)[] = ["hashinFT", "hashinFC", "hashinMT", "hashinMC"];
                  const maxVal = Math.max(...analysis.result.plies.map(p => p[keys[mi]] as number));
                  const pct = Math.min(maxVal / 1.5, 1) * 100;
                  return (
                    <div key={mode} className="flex items-center gap-2 h-7">
                      <span className="text-[10px] w-32 shrink-0" style={{ color: COL.textDim }}>{mode}</span>
                      <div className="flex-1 h-2 rounded-full" style={{ background: "rgba(255,255,255,0.04)" }}>
                        <div className="h-full rounded-full transition-all" style={{
                          width: `${pct}%`,
                          background: maxVal >= 1 ? COL.danger : maxVal >= 0.8 ? COL.warning : COL.accent,
                        }} />
                      </div>
                      <span className="text-[10px] tabular-nums w-12 text-right" style={{
                        color: maxVal >= 1 ? COL.danger : COL.text,
                      }}>
                        {maxVal.toFixed(3)}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Progressive failure curve */}
              {analysis.progCurve && (
                <div>
                  <div className="text-[10px] font-semibold mb-1" style={{ color: COL.textMid }}>
                    Progressive Failure Envelope (Camanho Degradation)
                  </div>
                  <FailureCurve curve={analysis.progCurve} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
