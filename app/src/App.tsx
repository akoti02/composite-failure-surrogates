import { useState, useEffect, useCallback, useRef, Component } from "react";
import type { ReactNode, ErrorInfo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Header } from "./components/Header";

// Error boundary to prevent white screen of death
class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: string }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: "" };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RP3 Error Boundary:", error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, color: COL.danger, background: COL.bgDark, height: "100vh", fontFamily: "monospace" }}>
          <h2 style={{ fontSize: 18, marginBottom: 12 }}>Something went wrong</h2>
          <p style={{ fontSize: 13, color: COL.textMid, marginBottom: 16 }}>{this.state.error}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: "" })}
            style={{ padding: "8px 16px", background: COL.accent, color: "white", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13 }}
          >
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
import { InputPanel } from "./components/InputPanel";
import { ResultsPanel } from "./components/ResultsPanel";
import { PlateCanvas } from "./components/PlateCanvas";
import { FocusModal } from "./components/FocusModal";
import { SplashScreen } from "./components/SplashScreen";
import { StressHeatmap } from "./components/StressHeatmap";
import { LaminateBuilder } from "./components/LaminateBuilder";
import { DesignExplorer } from "./components/DesignExplorer";
import { ProjectManager } from "./components/ProjectManager";
import type { RawInputs, PredictionResults, DefectParams } from "./lib/types";
import { PRESETS, DEFAULT_DEFECT, DEFAULT_DEFECTS } from "./lib/presets";
import { MAX_DEFECTS, COL } from "./lib/constants";
import { addHistoryEntry } from "./lib/project";
import type { AnalysisSnapshot } from "./lib/project";

function buildRawInputs(
  nDefects: number,
  pressureX: number,
  pressureY: number,
  plyThickness: number,
  layupRotation: number,
  defects: DefectParams[]
): RawInputs {
  const raw: RawInputs = {
    n_defects: nDefects,
    pressure_x: pressureX,
    pressure_y: pressureY,
    ply_thickness: plyThickness,
    layup_rotation: layupRotation,
  };
  for (let i = 0; i < MAX_DEFECTS; i++) {
    const d = defects[i] || DEFAULT_DEFECT;
    const idx = i + 1;
    raw[`defect${idx}_x`] = d.x;
    raw[`defect${idx}_y`] = d.y;
    raw[`defect${idx}_half_length`] = d.half_length;
    raw[`defect${idx}_width`] = d.width;
    raw[`defect${idx}_angle`] = d.angle;
    raw[`defect${idx}_roughness`] = d.roughness;
  }
  return raw;
}

function formatResultsForExport(
  results: PredictionResults, nDefects: number,
  pressureX?: number, pressureY?: number, plyThickness?: number, layupRotation?: number,
  defects?: DefectParams[]
): string {
  const lines: string[] = ["RP3 Prediction Results", "=====================", ""];
  const fmt = (v?: number) => v != null && isFinite(v) ? v.toFixed(4) : "--";
  const fmtMPa = (v?: number) => v != null && isFinite(v) ? `${v.toFixed(2)} MPa` : "--";

  // Include input parameters so results are reproducible
  lines.push("Input Configuration:");
  lines.push(`  Number of defects: ${nDefects}`);
  if (pressureX != null) lines.push(`  Pressure X: ${pressureX} MPa`);
  if (pressureY != null) lines.push(`  Pressure Y: ${pressureY} MPa`);
  if (plyThickness != null) lines.push(`  Ply thickness: ${plyThickness} mm`);
  if (layupRotation != null) lines.push(`  Layup rotation: ${layupRotation}°`);
  if (defects) {
    for (let i = 0; i < nDefects; i++) {
      const d = defects[i];
      if (d) lines.push(`  Defect ${i+1}: x=${d.x}mm y=${d.y}mm len=${d.half_length*2}mm w=${d.width}mm θ=${d.angle}°`);
    }
  }
  lines.push("");

  lines.push("Stress Analysis:");
  lines.push(`  Peak Stress (von Mises): ${fmtMPa(results.max_mises)}`);
  lines.push(`  Max Fibre Stress (S11):  ${fmtMPa(results.max_s11)}`);
  lines.push(`  Min Fibre Stress (S11):  ${fmtMPa(results.min_s11)}`);
  lines.push(`  Peak Shear (S12):        ${fmtMPa(results.max_s12)}`);
  lines.push("");
  lines.push("Failure Assessment:");
  lines.push(`  Tsai-Wu Index:  ${fmt(results.tsai_wu_index)}`);
  lines.push(`  Tsai-Wu Failed: ${results.failed_tsai_wu === 1 ? "YES" : results.failed_tsai_wu === 0 ? "NO" : "--"}`);
  lines.push(`  Hashin Failed:  ${results.failed_hashin === 1 ? "YES" : results.failed_hashin === 0 ? "NO" : "--"}`);
  lines.push("");
  lines.push("Hashin Damage Modes:");
  lines.push(`  Fibre Tension:      ${fmt(results.max_hashin_ft)}`);
  lines.push(`  Fibre Compression:  ${fmt(results.max_hashin_fc)}`);
  lines.push(`  Matrix Tension:     ${fmt(results.max_hashin_mt)}`);
  lines.push(`  Matrix Compression: ${fmt(results.max_hashin_mc)}`);
  lines.push("");
  lines.push("Per-Defect Peak Stress:");
  for (let i = 1; i <= nDefects; i++) {
    const key = `max_mises_defect${i}` as keyof PredictionResults;
    lines.push(`  Defect ${i}: ${fmtMPa(results[key] as number | undefined)}`);
  }
  return lines.join("\n");
}

const initDefects = (): DefectParams[] =>
  Array.from({ length: MAX_DEFECTS }, (_, i) => ({ ...(DEFAULT_DEFECTS[i] || DEFAULT_DEFECT) }));

type FocusTarget = null | "canvas" | "results";
type AppTab = "analysis" | "heatmap" | "laminate" | "explorer" | "project";

const TABS: { id: AppTab; label: string; icon: string }[] = [
  { id: "analysis", label: "Analysis", icon: "◎" },
  { id: "heatmap", label: "Stress Field", icon: "▦" },
  { id: "laminate", label: "Laminate", icon: "◈" },
  { id: "explorer", label: "Explorer", icon: "◐" },
  { id: "project", label: "Project", icon: "◫" },
];

/** Build age warning — shows banner if running a build older than 24h */
function BuildAgeBanner() {
  const buildDate = new Date(__BUILD_TIMESTAMP__ + "Z");
  const ageMs = Date.now() - buildDate.getTime();
  const ageHours = ageMs / 3600000;
  if (ageHours < 24) return null;
  const ageDays = Math.floor(ageHours / 24);
  return (
    <div
      className="text-[11px] text-center py-1 px-4"
      style={{ background: "#7c3aed22", borderBottom: "1px solid #7c3aed44", color: "#c4b5fd" }}
    >
      This build is {ageDays > 0 ? `${ageDays}d ` : ""}{Math.floor(ageHours % 24)}h old ({__BUILD_TIMESTAMP__}).
      Run <code className="text-[10px] bg-black/30 px-1 rounded">npx tauri build</code> to update.
    </div>
  );
}

function AppInner() {
  const [modelsReady, setModelsReady] = useState(false);
  const [modelCount, setModelCount] = useState(0);
  const [status, setStatus] = useState("Loading models...");
  const [predicting, setPredicting] = useState(false);
  const [results, setResults] = useState<PredictionResults | null>(null);

  // Inputs
  const [nDefects, setNDefects] = useState(3);
  const [pressureX, setPressureX] = useState(100.0);
  const [pressureY, setPressureY] = useState(0.0);
  const [plyThickness, setPlyThickness] = useState(0.125);
  const [layupRotation, setLayupRotation] = useState(0.0);
  const [defects, setDefects] = useState<DefectParams[]>(initDefects);
  const loadedRef = useRef(false);

  // Laminate state (shared between Stress Field and Laminate tabs)
  const [laminateCode, setLaminateCode] = useState("[0/±45/90]s");
  const [laminateMaterialId, setLaminateMaterialId] = useState("T300/5208");

  // UI state
  const [focusTarget, setFocusTarget] = useState<FocusTarget>(null);
  const [activeTab, setActiveTab] = useState<AppTab>("analysis");
  const [compareSnapshots, setCompareSnapshots] = useState<AnalysisSnapshot[]>([]);

  // Auto-save state to localStorage so users don't lose work
  useEffect(() => {
    const saved = localStorage.getItem("rp3-autosave");
    if (saved) {
      try {
        const s = JSON.parse(saved);
        if (s.nDefects) setNDefects(s.nDefects);
        if (s.pressureX != null) setPressureX(s.pressureX);
        if (s.pressureY != null) setPressureY(s.pressureY);
        if (s.plyThickness) setPlyThickness(s.plyThickness);
        if (s.layupRotation != null) setLayupRotation(s.layupRotation);
        if (s.defects) setDefects(s.defects);
        if (s.laminateCode) setLaminateCode(s.laminateCode);
        if (s.laminateMaterialId) setLaminateMaterialId(s.laminateMaterialId);
      } catch { /* ignore corrupt saves */ }
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      localStorage.setItem("rp3-autosave", JSON.stringify({
        nDefects, pressureX, pressureY, plyThickness, layupRotation,
        defects, laminateCode, laminateMaterialId,
      }));
    }, 500); // debounce saves by 500ms
    return () => clearTimeout(timer);
  }, [nDefects, pressureX, pressureY, plyThickness, layupRotation, defects, laminateCode, laminateMaterialId]);

  // Load models on mount
  useEffect(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    (async () => {
      try {
        const timeout = new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("Model loading timed out after 120s")), 120_000)
        );
        const resp = await Promise.race([
          invoke<{ ok: boolean; count: number; status: string }>("load_models"),
          timeout,
        ]);
        if (resp.ok && resp.count > 0) {
          setModelCount(resp.count);
          setModelsReady(true);
          setStatus(`Ready — ${resp.count} models loaded`);
        } else if (resp.ok && resp.count === 0) {
          setModelCount(0);
          setModelsReady(false);
          setStatus("No models loaded — check sidecar");
        } else {
          setStatus("Model load failed");
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("Cannot read properties") || msg.includes("__TAURI__") || msg.includes("invoke")) {
          setStatus("Standalone mode — no sidecar");
        } else {
          setStatus(`Error: ${msg.slice(0, 60)}`);
        }
      }
    })();
  }, []);

  const handlePreset = useCallback((name: string) => {
    const p = PRESETS[name];
    if (!p) return;
    setNDefects(p.n_defects);
    setPressureX(p.pressure_x);
    setPressureY(p.pressure_y);
    setPlyThickness(p.ply_thickness);
    setLayupRotation(p.layup_rotation);
    const newDefects = initDefects();
    p.defects.forEach((d, i) => { newDefects[i] = { ...d }; });
    setDefects(newDefects);
    setResults(null);
  }, []);

  const handlePredict = useCallback(async () => {
    if (!modelsReady || predicting) return;
    setPredicting(true);
    setStatus("Analysing...");
    try {
      const raw = buildRawInputs(nDefects, pressureX, pressureY, plyThickness, layupRotation, defects);
      const resp = await invoke<{ ok: boolean; results: PredictionResults; error?: string }>("predict", { params: raw });
      if (resp.ok) {
        setResults(resp.results);
        setStatus("Analysis complete");
        // Auto-save to history
        addHistoryEntry(nDefects, pressureX, pressureY, resp.results);
      } else {
        setStatus(`Error: ${resp.error}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus(`Error: ${msg.slice(0, 60)}`);
    }
    setPredicting(false);
  }, [modelsReady, predicting, nDefects, pressureX, pressureY, plyThickness, layupRotation, defects]);

  const handleReset = useCallback(() => {
    setNDefects(3);
    setPressureX(100.0);
    setPressureY(0.0);
    setPlyThickness(0.125);
    setLayupRotation(0.0);
    setDefects(initDefects());
    setResults(null);
    setStatus(modelsReady ? `Ready -- ${modelCount} models loaded` : "Loading models...");
  }, [modelsReady, modelCount]);

  const handleExport = useCallback(() => {
    if (!results) return;
    const text = formatResultsForExport(results, nDefects, pressureX, pressureY, plyThickness, layupRotation, defects);
    navigator.clipboard.writeText(text).then(() => {
      setStatus("Results copied to clipboard");
      setTimeout(() => setStatus("Analysis complete"), 2000);
    });
  }, [results, nDefects, pressureX, pressureY, plyThickness, layupRotation, defects]);

  // Enter key triggers predict — only when not focused on an input
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" && modelsReady) {
        const tag = (e.target as HTMLElement)?.tagName;
        if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
        handlePredict();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handlePredict, modelsReady]);

  const updateDefect = useCallback((index: number, field: keyof DefectParams, value: number) => {
    setDefects((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }, []);

  const handleRestoreSnapshot = useCallback((snap: AnalysisSnapshot) => {
    setNDefects(snap.nDefects);
    setPressureX(snap.pressureX);
    setPressureY(snap.pressureY);
    setPlyThickness(snap.plyThickness);
    setLayupRotation(snap.layupRotation);
    const newDefects = initDefects();
    snap.defects.forEach((d, i) => { newDefects[i] = { ...d }; });
    setDefects(newDefects);
    setResults(snap.results);
    setActiveTab("analysis");
    setStatus(snap.results ? "Snapshot restored" : "Snapshot restored (no results)");
  }, []);

  const handleToggleCompare = useCallback((snap: AnalysisSnapshot) => {
    setCompareSnapshots(prev => {
      const exists = prev.some(s => s.id === snap.id);
      if (exists) return prev.filter(s => s.id !== snap.id);
      return [...prev, snap];
    });
  }, []);

  const canvasProps = {
    nDefects, defects, pressureX, pressureY, layupRotation,
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: COL.bg }}>
      <BuildAgeBanner />
      <Header
        status={status} modelsReady={modelsReady} predicting={predicting}
        onPreset={handlePreset} onExport={handleExport} hasResults={results !== null}
        onPredict={handlePredict} onReset={handleReset}
      />

      {/* Tab bar — arrow keys navigate between tabs */}
      <div
        className="shrink-0 flex items-center gap-0.5 px-4 h-9"
        role="tablist"
        aria-label="Application sections"
        style={{ background: COL.bgDark, borderBottom: `1px solid ${COL.border}` }}
        onKeyDown={(e) => {
          const idx = TABS.findIndex(t => t.id === activeTab);
          if (e.key === "ArrowRight" && idx < TABS.length - 1) { setActiveTab(TABS[idx + 1].id); e.preventDefault(); }
          if (e.key === "ArrowLeft" && idx > 0) { setActiveTab(TABS[idx - 1].id); e.preventDefault(); }
        }}
      >
        {TABS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            className="flex items-center gap-1.5 px-3 py-1 rounded-t-md text-[11px] font-semibold transition-all"
            style={{
              background: activeTab === tab.id ? COL.bg : "transparent",
              color: activeTab === tab.id ? COL.text : COL.textDim,
              borderBottom: activeTab === tab.id ? `2px solid ${COL.accent}` : "2px solid transparent",
            }}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="text-[12px]">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {/* Analysis tab — original layout */}
        {activeTab === "analysis" && (
          <div className="h-full grid grid-cols-1 lg:grid-cols-[45fr_55fr] min-h-0">
            <div className="flex flex-col min-h-0" style={{ borderRight: `1px solid ${COL.border}` }}>
              <div
                className="shrink-0 px-3 pt-2 pb-1 relative group"
                style={{ background: COL.bg, borderBottom: `1px solid ${COL.border}` }}
              >
                <PlateCanvas {...canvasProps} />
                <button
                  className="absolute top-3 right-4 w-6 h-6 flex items-center justify-center rounded-md btn-press opacity-40 hover:opacity-100 transition-opacity"
                  style={{ color: COL.textDim, background: "rgba(0,0,0,0.5)", border: `1px solid ${COL.border}` }}
                  onClick={() => setFocusTarget("canvas")}
                  data-tooltip="Expand canvas"
                >
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
                  </svg>
                </button>
              </div>
              <InputPanel
                nDefects={nDefects} setNDefects={setNDefects}
                pressureX={pressureX} setPressureX={setPressureX}
                pressureY={pressureY} setPressureY={setPressureY}
                plyThickness={plyThickness} setPlyThickness={setPlyThickness}
                layupRotation={layupRotation} setLayupRotation={setLayupRotation}
                defects={defects} updateDefect={updateDefect}
              />
            </div>
            <ResultsPanel
              results={results}
              nDefects={nDefects}
              onExpandModal={() => setFocusTarget("results")}
            />
          </div>
        )}

        {/* Stress Heatmap tab */}
        {activeTab === "heatmap" && (
          <div className="h-full px-4 py-3">
            <StressHeatmap
              defects={defects}
              nDefects={nDefects}
              pressureX={pressureX}
              pressureY={pressureY}
              predictions={results}
              laminateCode={laminateCode}
              laminateMaterialId={laminateMaterialId}
              plyThickness={plyThickness}
              layupRotation={layupRotation}
            />
          </div>
        )}

        {/* Laminate Builder tab */}
        {activeTab === "laminate" && (
          <div className="h-full px-4 py-3">
            <LaminateBuilder
              laminateCode={laminateCode}
              onLaminateCodeChange={setLaminateCode}
              materialId={laminateMaterialId}
              onMaterialIdChange={setLaminateMaterialId}
            />
          </div>
        )}

        {/* Design Explorer tab */}
        {activeTab === "explorer" && (
          <div className="h-full px-4 py-3">
            <DesignExplorer
              nDefects={nDefects}
              pressureX={pressureX}
              pressureY={pressureY}
              plyThickness={plyThickness}
              layupRotation={layupRotation}
              defects={defects}
              modelsReady={modelsReady}
            />
          </div>
        )}

        {/* Project Manager tab */}
        {activeTab === "project" && (
          <div className="h-full px-4 py-3">
            <ProjectManager
              nDefects={nDefects}
              pressureX={pressureX}
              pressureY={pressureY}
              plyThickness={plyThickness}
              layupRotation={layupRotation}
              defects={defects}
              results={results}
              onRestoreSnapshot={handleRestoreSnapshot}
              compareSnapshots={compareSnapshots}
              onToggleCompare={handleToggleCompare}
            />
          </div>
        )}
      </div>

      <footer className="h-7 flex items-center justify-center text-[10px]" style={{ color: COL.textDim, background: COL.bgDark, borderTop: `1px solid ${COL.border}` }}>
        University of Bristol&nbsp;&nbsp;·&nbsp;&nbsp;AENG30017&nbsp;&nbsp;·&nbsp;&nbsp;Artur Akoev
      </footer>

      {/* Focus Modals */}
      <FocusModal
        open={focusTarget === "canvas"}
        onClose={() => setFocusTarget(null)}
        title="Plate Preview"
      >
        <div className="w-full h-full flex items-center justify-center">
          <PlateCanvas {...canvasProps} />
        </div>
      </FocusModal>

      <FocusModal
        open={focusTarget === "results"}
        onClose={() => setFocusTarget(null)}
        title="Results"
      >
        <ResultsPanel results={results} nDefects={nDefects} />
      </FocusModal>

      <SplashScreen onReady={modelsReady} />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AppInner />
    </ErrorBoundary>
  );
}
