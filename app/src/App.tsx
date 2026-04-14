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
import { LaminateBuilder } from "./components/LaminateBuilder";
import { DesignExplorer } from "./components/DesignExplorer";
import { ProjectManager } from "./components/ProjectManager";
import type { RawInputs, PredictionResults, DefectParams } from "./lib/types";
import type { AnalysisSnapshot } from "./lib/project";
import { PRESETS, DEFAULT_DEFECT, DEFAULT_DEFECTS } from "./lib/presets";
import { MAX_DEFECTS, COL } from "./lib/constants";
import { MATERIAL_DB, LAYUP_DB, DEFAULT_MATERIAL_ID, DEFAULT_LAYUP_ID, DEFAULT_BC_MODE } from "./lib/materials";
import { addHistoryEntry } from "./lib/project";

function buildRawInputs(
  nDefects: number,
  pressureX: number,
  pressureY: number,
  materialKey: string,
  layupKey: string,
  bcMode: string,
  defects: DefectParams[]
): RawInputs {
  const mat = MATERIAL_DB[materialKey];
  const layup = LAYUP_DB[layupKey];
  const raw: RawInputs = {
    n_defects: nDefects,
    pressure_x: pressureX,
    pressure_y: pressureY,
    material_id: mat?.id ?? 1,
    layup_id: layup?.id ?? 1,
    bc_mode: bcMode,
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
  pressureX?: number, pressureY?: number,
  materialKey?: string, layupKey?: string, bcMode?: string,
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
  if (materialKey) {
    const mat = MATERIAL_DB[materialKey];
    lines.push(`  Material: ${mat?.name ?? materialKey} (id=${mat?.id ?? "?"})`);
  }
  if (layupKey) {
    const layup = LAYUP_DB[layupKey];
    lines.push(`  Layup: ${layup?.name ?? layupKey} (id=${layup?.id ?? "?"})`);
  }
  if (bcMode) lines.push(`  BC Mode: ${bcMode}`);
  if (defects) {
    for (let i = 0; i < nDefects; i++) {
      const d = defects[i];
      if (d) lines.push(`  Defect ${i+1}: x=${d.x}mm y=${d.y}mm len=${d.half_length*2}mm w=${d.width}mm th=${d.angle} deg`);
    }
  }
  lines.push("");

  lines.push("Stress Analysis:");
  lines.push(`  Max Fibre Stress (S11):  ${fmtMPa(results.max_s11)}`);
  lines.push(`  Min Fibre Stress (S11):  ${fmtMPa(results.min_s11)}`);
  lines.push(`  Peak Shear (S12):        ${fmtMPa(results.max_s12)}`);
  lines.push("");
  lines.push("Failure Assessment:");
  lines.push(`  Tsai-Wu Index:  ${fmt(results.tsai_wu_index)}`);
  lines.push(`  Tsai-Wu Failed: ${results.failed_tsai_wu === 1 ? "YES" : results.failed_tsai_wu === 0 ? "NO" : "--"}`);
  lines.push(`  Hashin Failed:  ${results.failed_hashin === 1 ? "YES" : results.failed_hashin === 0 ? "NO" : "--"}`);
  lines.push(`  Puck Failed:    ${results.failed_puck === 1 ? "YES" : results.failed_puck === 0 ? "NO" : "--"}`);
  lines.push(`  LaRC Failed:    ${results.failed_larc === 1 ? "YES" : results.failed_larc === 0 ? "NO" : "--"}`);
  lines.push("");
  lines.push("Hashin Damage Modes:");
  lines.push(`  Fibre Tension:      ${fmt(results.max_hashin_ft)}`);
  lines.push(`  Matrix Tension:     ${fmt(results.max_hashin_mt)}`);
  lines.push(`  Matrix Compression: ${fmt(results.max_hashin_mc)}`);
  return lines.join("\n");
}

const initDefects = (): DefectParams[] =>
  Array.from({ length: MAX_DEFECTS }, (_, i) => ({ ...(DEFAULT_DEFECTS[i] || DEFAULT_DEFECT) }));

type FocusTarget = null | "canvas" | "results" | "laminate";
type AppTab = "analysis" | "explorer";

const TABS: { id: AppTab; label: string; icon: string }[] = [
  { id: "analysis", label: "Analysis", icon: "◎" },
  { id: "explorer", label: "Explorer", icon: "◐" },
];

const GITHUB_REPO = "akoti02/composite-failure-surrogates";
const CURRENT_VERSION = "0.2.0";

interface ReleaseInfo {
  tag: string;
  version: string;
  downloadUrl: string;
}

function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] || 0) - (pb[i] || 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function UpdateBanner() {
  const [release, setRelease] = useState<ReleaseInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    fetch(`https://api.github.com/repos/${GITHUB_REPO}/releases/latest`)
      .then(r => r.json())
      .then(data => {
        const tag = data.tag_name as string;
        const version = tag.replace(/^v/, "");
        if (compareVersions(version, CURRENT_VERSION) > 0) {
          const exe = (data.assets as { name: string; browser_download_url: string }[])
            ?.find(a => a.name.endsWith("-setup.exe"));
          setRelease({
            tag,
            version,
            downloadUrl: exe?.browser_download_url
              ?? `https://github.com/${GITHUB_REPO}/releases/tag/${tag}`,
          });
        }
      })
      .catch(() => { /* offline or rate-limited — silently skip */ });
  }, []);

  if (!release || dismissed) return null;

  return (
    <div
      className="flex items-center justify-center gap-3 text-[11px] py-1.5 px-4"
      style={{ background: "#7c3aed22", borderBottom: "1px solid #7c3aed44", color: "#c4b5fd" }}
    >
      <span>Version {release.version} is available</span>
      <button
        className="px-3 py-0.5 rounded-md text-[11px] font-semibold cursor-pointer"
        style={{ background: "#7c3aed", color: "#fff", border: "none" }}
        onClick={() => import("@tauri-apps/plugin-opener").then(m => m.openUrl(release.downloadUrl)).catch(() => window.open(release.downloadUrl, "_blank"))}
      >
        Download update
      </button>
      <button
        className="text-[11px] cursor-pointer"
        style={{ color: "#c4b5fd80", background: "none", border: "none" }}
        onClick={() => setDismissed(true)}
      >
        Dismiss
      </button>
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
  const [materialKey, setMaterialKey] = useState(DEFAULT_MATERIAL_ID);
  const [layupKey, setLayupKey] = useState(DEFAULT_LAYUP_ID);
  const [bcMode, setBcMode] = useState(DEFAULT_BC_MODE);
  const [defects, setDefects] = useState<DefectParams[]>(initDefects);
  const loadedRef = useRef(false);

  // Laminate state (shared between Stress Field and Laminate tabs)
  const [laminateCode, setLaminateCode] = useState("[0/±45/90]s");
  const [laminateMaterialId, setLaminateMaterialId] = useState("T300/5208");

  // UI state
  const [focusTarget, setFocusTarget] = useState<FocusTarget>(null);
  const [activeTab, setActiveTab] = useState<AppTab>("analysis");
  const [activePreset, setActivePreset] = useState("");
  const [showProjects, setShowProjects] = useState(false);
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
        if (s.materialKey) setMaterialKey(s.materialKey);
        if (s.layupKey) setLayupKey(s.layupKey);
        if (s.bcMode) setBcMode(s.bcMode);
        // Legacy migration: ignore old plyThickness/layupRotation
        if (s.defects) setDefects(s.defects);
        if (s.laminateCode) setLaminateCode(s.laminateCode);
        if (s.laminateMaterialId) setLaminateMaterialId(s.laminateMaterialId);
      } catch { /* ignore corrupt saves */ }
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      localStorage.setItem("rp3-autosave", JSON.stringify({
        nDefects, pressureX, pressureY, materialKey, layupKey, bcMode,
        defects, laminateCode, laminateMaterialId,
      }));
    }, 500); // debounce saves by 500ms
    return () => clearTimeout(timer);
  }, [nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, laminateCode, laminateMaterialId]);

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
    if (!p) { setActivePreset(""); return; }
    setActivePreset(name);
    setNDefects(p.n_defects);
    setPressureX(p.pressure_x);
    setPressureY(p.pressure_y);
    // Find material/layup keys by numeric id
    const matEntry = Object.entries(MATERIAL_DB).find(([, m]) => m.id === p.material_id);
    if (matEntry) setMaterialKey(matEntry[0]);
    const layupEntry = Object.entries(LAYUP_DB).find(([, l]) => l.id === p.layup_id);
    if (layupEntry) setLayupKey(layupEntry[0]);
    setBcMode(p.bc_mode);
    const newDefects = initDefects();
    p.defects.forEach((d, i) => { newDefects[i] = { ...d }; });
    setDefects(newDefects);
    setResults(null);
  }, []);

  // Core prediction function — used by both auto-predict and manual Run.
  // Uses a generation counter to discard stale in-flight predictions when
  // inputs change, preventing old results from overwriting new state.
  const predictingRef = useRef(false);
  const generationRef = useRef(0);
  const runPrediction = useCallback(async (saveToHistory: boolean) => {
    if (!modelsReady) return;
    const gen = ++generationRef.current;
    predictingRef.current = true;
    setPredicting(true);
    try {
      const raw = buildRawInputs(nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects);
      const resp = await invoke<{ ok: boolean; results: PredictionResults; error?: string }>("predict", { params: raw });
      if (gen !== generationRef.current) return; // stale — inputs changed while we were waiting
      if (resp.ok) {
        setResults(resp.results);
        setStatus("Live");
        if (saveToHistory) addHistoryEntry(nDefects, pressureX, pressureY, resp.results);
      } else {
        setStatus(`Error: ${resp.error}`);
      }
    } catch (e) {
      if (gen !== generationRef.current) return; // stale
      const msg = e instanceof Error ? e.message : String(e);
      console.error("Prediction failed:", msg);
      setStatus(`Error: ${msg.slice(0, 80)}`);
    } finally {
      if (gen === generationRef.current) {
        predictingRef.current = false;
        setPredicting(false);
      }
    }
  }, [modelsReady, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects]);

  // Live prediction — auto-triggers on any input change (200ms debounce)
  useEffect(() => {
    if (!modelsReady) return;
    const timer = setTimeout(() => runPrediction(false), 200);
    return () => clearTimeout(timer);
  }, [modelsReady, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, runPrediction]);

  // Manual predict (Run button / Enter key) — also saves to history
  const handlePredict = useCallback(() => {
    runPrediction(true);
  }, [runPrediction]);

  const handleReset = useCallback(() => {
    setActivePreset("");
    setNDefects(3);
    setPressureX(100.0);
    setPressureY(0.0);
    setMaterialKey(DEFAULT_MATERIAL_ID);
    setLayupKey(DEFAULT_LAYUP_ID);
    setBcMode(DEFAULT_BC_MODE);
    setDefects(initDefects());
    setResults(null);
    setStatus(modelsReady ? `Ready -- ${modelCount} models loaded` : "Loading models...");
  }, [modelsReady, modelCount]);

  const handleExport = useCallback(() => {
    if (!results) return;
    const text = formatResultsForExport(results, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects);
    navigator.clipboard.writeText(text).then(() => {
      setStatus("Results copied to clipboard");
      setTimeout(() => setStatus("Analysis complete"), 2000);
    }).catch(() => {
      setStatus("Clipboard write failed");
    });
  }, [results, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects]);

  const handleRestoreSnapshot = useCallback((snap: AnalysisSnapshot) => {
    setActivePreset("");
    setNDefects(snap.nDefects);
    setPressureX(snap.pressureX);
    setPressureY(snap.pressureY);
    setMaterialKey(snap.materialKey);
    setLayupKey(snap.layupKey);
    setBcMode(snap.bcMode);
    const newDefects = initDefects();
    snap.defects.forEach((d, i) => { newDefects[i] = { ...d }; });
    setDefects(newDefects);
    setResults(snap.results);
  }, []);

  const handleToggleCompare = useCallback((snap: AnalysisSnapshot) => {
    setCompareSnapshots(prev =>
      prev.some(s => s.id === snap.id)
        ? prev.filter(s => s.id !== snap.id)
        : [...prev, snap]
    );
  }, []);

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

  // Wrap input setters to clear preset label on manual changes
  const setNDefectsManual = useCallback((v: number) => { setActivePreset(""); setNDefects(v); }, []);
  const setPressureXManual = useCallback((v: number) => { setActivePreset(""); setPressureX(v); }, []);
  const setPressureYManual = useCallback((v: number) => { setActivePreset(""); setPressureY(v); }, []);
  const setMaterialKeyManual = useCallback((v: string) => { setActivePreset(""); setMaterialKey(v); }, []);
  const setLayupKeyManual = useCallback((v: string) => { setActivePreset(""); setLayupKey(v); }, []);
  const setBcModeManual = useCallback((v: string) => { setActivePreset(""); setBcMode(v); }, []);

  const updateDefect = useCallback((index: number, field: keyof DefectParams, value: number) => {
    setActivePreset("");
    setDefects((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  }, []);

  const canvasProps = {
    nDefects, defects, pressureX, pressureY,
  };

  return (
    <div className="flex flex-col h-screen" style={{ background: COL.bg }}>
      <UpdateBanner />
      <Header
        status={status} modelsReady={modelsReady} predicting={predicting}
        activePreset={activePreset}
        onPreset={handlePreset} onExport={handleExport} hasResults={results !== null}
        onPredict={handlePredict} onReset={handleReset}
        onProjects={() => setShowProjects(true)}
        onLaminate={() => setFocusTarget("laminate")}
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
        {/* Analysis tab — inputs + predictions + laminate info */}
        {activeTab === "analysis" && (
          <div className="h-full grid grid-cols-1 lg:grid-cols-[42fr_58fr] min-h-0">
            <div className="flex flex-col min-h-0" style={{ borderRight: `1px solid ${COL.border}` }}>
              {/* Compact plate preview — click to expand */}
              <div
                className="shrink-0 relative group cursor-pointer"
                style={{ height: 140, background: COL.bgDark, borderBottom: `1px solid ${COL.border}`, overflow: "hidden" }}
                onClick={() => setFocusTarget("canvas")}
              >
                <div style={{ transform: "scale(0.55)", transformOrigin: "top center", pointerEvents: "none" }}>
                  <PlateCanvas {...canvasProps} />
                </div>
                <div className="absolute inset-0 flex items-end justify-center pb-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                  style={{ background: "linear-gradient(transparent 40%, rgba(0,0,0,0.6))" }}>
                  <span className="text-[11px] font-medium" style={{ color: "rgba(255,255,255,0.7)" }}>Click to expand plate view</span>
                </div>
              </div>

              {/* INPUT PANEL — primary content, gets all remaining space */}
              <InputPanel
                nDefects={nDefects} setNDefects={setNDefectsManual}
                pressureX={pressureX} setPressureX={setPressureXManual}
                pressureY={pressureY} setPressureY={setPressureYManual}
                materialKey={materialKey} setMaterialKey={setMaterialKeyManual}
                layupKey={layupKey} setLayupKey={setLayupKeyManual}
                bcMode={bcMode} setBcMode={setBcModeManual}
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

        {/* Explorer tab — parameter sweeps, Monte Carlo, sensitivity */}
        {activeTab === "explorer" && (
          <div className="h-full px-4 py-3">
            <DesignExplorer
              nDefects={nDefects}
              pressureX={pressureX}
              pressureY={pressureY}
              materialKey={materialKey}
              layupKey={layupKey}
              bcMode={bcMode}
              defects={defects}
              modelsReady={modelsReady}
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

      <FocusModal
        open={focusTarget === "laminate"}
        onClose={() => setFocusTarget(null)}
        title="Laminate Analysis"
      >
        <LaminateBuilder
          laminateCode={laminateCode}
          onLaminateCodeChange={setLaminateCode}
          materialId={laminateMaterialId}
          onMaterialIdChange={setLaminateMaterialId}
        />
      </FocusModal>

      <FocusModal
        open={showProjects}
        onClose={() => setShowProjects(false)}
        title="Projects"
      >
        <ProjectManager
          nDefects={nDefects} pressureX={pressureX} pressureY={pressureY}
          materialKey={materialKey} layupKey={layupKey} bcMode={bcMode}
          defects={defects} results={results}
          onRestoreSnapshot={handleRestoreSnapshot}
          compareSnapshots={compareSnapshots}
          onToggleCompare={handleToggleCompare}
        />
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
