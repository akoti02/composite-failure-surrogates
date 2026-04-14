import { useState, useEffect, useCallback, useRef, Component } from "react";
import type { ReactNode, ErrorInfo } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Header } from "./components/Header";
import { useLang, useT } from "./lib/i18n";
import type { TKey } from "./lib/i18n";

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
      // Error boundary cannot use hooks, so strings stay English here.
      return (
        <div style={{ padding: 40, color: COL.danger, background: COL.bgDark, height: "100vh", fontFamily: "monospace" }}>
          <h2 style={{ fontSize: 20, marginBottom: 12 }}>Something went wrong / Что-то пошло не так</h2>
          <p style={{ fontSize: 14, color: COL.textMid, marginBottom: 16 }}>{this.state.error}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: "" })}
            style={{ padding: "10px 18px", background: COL.accent, color: "#041017", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14, fontWeight: 600, boxShadow: "0 0 16px rgba(0,234,255,0.5)" }}
          >
            Try Again / Повторить
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
  t: (k: TKey, vars?: Record<string, string | number>) => string,
  unitMPa: string, unitMM: string, unitDeg: string,
  pressureX?: number, pressureY?: number,
  materialKey?: string, layupKey?: string, bcMode?: string,
  defects?: DefectParams[]
): string {
  const lines: string[] = [t("export_title"), "=====================", ""];
  const fmt = (v?: number) => v != null && isFinite(v) ? v.toFixed(4) : "--";
  const fmtMPa = (v?: number) => v != null && isFinite(v) ? `${v.toFixed(2)} ${unitMPa}` : "--";
  const yn = (v?: number) => v === 1 ? t("export_yes") : v === 0 ? t("export_no") : "--";

  lines.push(`${t("export_input")}:`);
  lines.push(`  ${t("export_n_defects")}: ${nDefects}`);
  if (pressureX != null) lines.push(`  ${t("pressure_x")}: ${pressureX} ${unitMPa}`);
  if (pressureY != null) lines.push(`  ${t("pressure_y")}: ${pressureY} ${unitMPa}`);
  if (materialKey) {
    const mat = MATERIAL_DB[materialKey];
    lines.push(`  ${t("material")}: ${mat?.name ?? materialKey} (id=${mat?.id ?? "?"})`);
  }
  if (layupKey) {
    const layup = LAYUP_DB[layupKey];
    lines.push(`  ${t("layup")}: ${layup?.name ?? layupKey} (id=${layup?.id ?? "?"})`);
  }
  if (bcMode) lines.push(`  ${t("export_bc_mode")}: ${bcMode}`);
  if (defects) {
    for (let i = 0; i < nDefects; i++) {
      const d = defects[i];
      if (d) lines.push(`  ${t("defect")} ${i+1}: x=${d.x}${unitMM} y=${d.y}${unitMM} len=${d.half_length*2}${unitMM} w=${d.width}${unitMM} θ=${d.angle}${unitDeg}`);
    }
  }
  lines.push("");

  lines.push(`${t("export_stress")}:`);
  lines.push(`  ${t("max_fibre_stress")}:  ${fmtMPa(results.max_s11)}`);
  lines.push(`  ${t("min_fibre_stress")}:  ${fmtMPa(results.min_s11)}`);
  lines.push(`  ${t("peak_shear")}:        ${fmtMPa(results.max_s12)}`);
  lines.push("");
  lines.push(`${t("export_failure_assess")}:`);
  lines.push(`  ${t("export_tsai_wu_index")}:  ${fmt(results.tsai_wu_index)}`);
  lines.push(`  ${t("export_tsai_wu_failed")}: ${yn(results.failed_tsai_wu)}`);
  lines.push(`  ${t("export_hashin_failed")}:  ${yn(results.failed_hashin)}`);
  lines.push(`  ${t("export_puck_failed")}:    ${yn(results.failed_puck)}`);
  lines.push(`  ${t("export_larc_failed")}:    ${yn(results.failed_larc)}`);
  lines.push("");
  lines.push(`${t("export_hashin_modes")}:`);
  lines.push(`  ${t("fibre_tension")}:      ${fmt(results.max_hashin_ft)}`);
  lines.push(`  ${t("matrix_tension")}:     ${fmt(results.max_hashin_mt)}`);
  lines.push(`  ${t("matrix_compression")}: ${fmt(results.max_hashin_mc)}`);
  return lines.join("\n");
}

const initDefects = (): DefectParams[] =>
  Array.from({ length: MAX_DEFECTS }, (_, i) => ({ ...(DEFAULT_DEFECTS[i] || DEFAULT_DEFECT) }));

type FocusTarget = null | "canvas" | "results" | "laminate";
type AppTab = "analysis" | "explorer";

const TABS: { id: AppTab; labelKey: TKey; icon: string }[] = [
  { id: "analysis", labelKey: "tab_analysis", icon: "◎" },
  { id: "explorer", labelKey: "tab_explorer", icon: "◐" },
];

/**
 * Tauri auto-updater banner.
 *
 * On mount we call `check()` from @tauri-apps/plugin-updater, which hits the
 * endpoint configured in tauri.conf.json (a signed latest.json on the
 * GitHub Release), compares versions, and returns an update handle if one
 * is available. User clicks "Update now" → we stream `downloadAndInstall`
 * with progress → on finish, `relaunch()` restarts into the new version.
 *
 * No manual reinstall. No UAC (Windows NSIS in "passive" mode runs per-user
 * with just a brief progress window). Signed with a public key baked into
 * the app binary, so tampered updates are rejected.
 */
type UpdateState =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "up_to_date" }
  | { kind: "available"; version: string; notes: string; update: UpdateHandle }
  | { kind: "downloading"; pct: number; total: number }
  | { kind: "installing" }
  | { kind: "restarting" }
  | { kind: "failed"; msg: string };

// Custom event Header dispatches when the user clicks "Check for updates".
// UpdateBanner listens and triggers a fresh check().
const CHECK_UPDATES_EVENT = "rp3-check-updates";

interface UpdateHandle {
  version: string;
  body?: string | null;
  downloadAndInstall: (onEvent: (e: DownloadEvent) => void) => Promise<void>;
}
type DownloadEvent =
  | { event: "Started"; data: { contentLength?: number } }
  | { event: "Progress"; data: { chunkLength: number } }
  | { event: "Finished" };

function UpdateBanner() {
  const t = useT();
  const [state, setState] = useState<UpdateState>({ kind: "idle" });
  const [dismissed, setDismissed] = useState(false);

  const doCheck = useCallback(async (manual: boolean) => {
    if (manual) setState({ kind: "checking" });
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (!update) {
        // No newer version. If the user asked manually, say so briefly;
        // otherwise stay silent.
        if (manual) {
          setState({ kind: "up_to_date" });
          setTimeout(() => setState(prev => prev.kind === "up_to_date" ? { kind: "idle" } : prev), 3500);
        }
        return;
      }
      setDismissed(false);
      setState({
        kind: "available",
        version: update.version,
        notes: update.body ?? "",
        update: update as unknown as UpdateHandle,
      });
    } catch (e) {
      if (manual) {
        const msg = e instanceof Error ? e.message : String(e);
        setState({ kind: "failed", msg: msg.slice(0, 120) });
      }
      // Silent on startup — offline, not inside Tauri, etc.
    }
  }, []);

  // Automatic check on mount.
  useEffect(() => { doCheck(false); }, [doCheck]);

  // Manual check via window event (dispatched by the Header "Check for
  // updates" button).
  useEffect(() => {
    const handler = () => doCheck(true);
    window.addEventListener(CHECK_UPDATES_EVENT, handler);
    return () => window.removeEventListener(CHECK_UPDATES_EVENT, handler);
  }, [doCheck]);

  const handleInstall = useCallback(async () => {
    if (state.kind !== "available") return;
    const handle = state.update;
    let downloaded = 0;
    let total = 0;
    setState({ kind: "downloading", pct: 0, total: 0 });
    try {
      await handle.downloadAndInstall((e) => {
        if (e.event === "Started") {
          total = e.data.contentLength ?? 0;
          setState({ kind: "downloading", pct: 0, total });
        } else if (e.event === "Progress") {
          downloaded += e.data.chunkLength;
          const pct = total > 0 ? Math.round((downloaded / total) * 100) : 0;
          setState({ kind: "downloading", pct, total });
        } else if (e.event === "Finished") {
          setState({ kind: "installing" });
        }
      });
      setState({ kind: "restarting" });
      // Small delay so the user sees the "restarting" message, then relaunch.
      const { relaunch } = await import("@tauri-apps/plugin-process");
      setTimeout(() => { relaunch().catch(() => {/* ignore */}); }, 400);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setState({ kind: "failed", msg: msg.slice(0, 120) });
    }
  }, [state]);

  if (dismissed && state.kind === "available") return null;
  if (state.kind === "idle") return null;

  // Palette: cyan glow for active/info states, violet for "available", rose for failure.
  const palette = state.kind === "failed"
    ? { bg: "rgba(255,94,135,0.12)", border: "rgba(255,94,135,0.35)", text: "#ffd0dc", btn: "#ff5e87", btnText: "#1a0810", glow: "rgba(255,94,135,0.25)" }
    : state.kind === "available"
      ? { bg: "rgba(183,148,255,0.12)", border: "rgba(183,148,255,0.35)", text: "#e0ccff", btn: "#b794ff", btnText: "#1a0a2e", glow: "rgba(183,148,255,0.4)" }
      : state.kind === "up_to_date"
        ? { bg: "rgba(94,255,176,0.10)", border: "rgba(94,255,176,0.32)", text: "#c9ffe4", btn: COL.success, btnText: "#0b1f15", glow: "rgba(94,255,176,0.32)" }
        : { bg: "rgba(0,234,255,0.10)", border: "rgba(0,234,255,0.32)", text: "#b4f5ff", btn: COL.accent, btnText: "#041017", glow: "rgba(0,234,255,0.4)" };

  return (
    <div
      className="flex items-center justify-center gap-3 text-[12px] py-2 px-4"
      style={{
        background: palette.bg,
        borderBottom: `1px solid ${palette.border}`,
        color: palette.text,
        boxShadow: `0 0 22px ${palette.glow}`,
      }}
    >
      {state.kind === "available" && (
        <>
          <span className="font-semibold">{t("update_available", { v: state.version })}</span>
          {state.notes && (
            <span className="opacity-75 truncate max-w-[400px]" title={state.notes}>
              — {state.notes.split("\n")[0]}
            </span>
          )}
          <button
            className="px-3 py-1 rounded-md text-[12px] font-semibold cursor-pointer btn-press"
            style={{ background: palette.btn, color: palette.btnText, border: "none", boxShadow: `0 0 12px ${palette.glow}`, textShadow: "0 0 6px rgba(255,255,255,0.3)" }}
            onClick={handleInstall}
          >
            {t("update_download")}
          </button>
          <button
            className="text-[12px] cursor-pointer"
            style={{ color: `${palette.text}99`, background: "none", border: "none" }}
            onClick={() => setDismissed(true)}
          >
            {t("update_dismiss")}
          </button>
        </>
      )}

      {state.kind === "downloading" && (
        <>
          <span className="font-semibold">{t("update_downloading", { pct: state.pct })}</span>
          <div className="w-64 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${state.pct}%`,
                background: COL.accent,
                boxShadow: "0 0 10px rgba(0,234,255,0.7)",
              }}
            />
          </div>
        </>
      )}

      {state.kind === "checking" && (
        <span className="font-semibold">{t("update_checking")}</span>
      )}
      {state.kind === "up_to_date" && (
        <span className="font-semibold">{t("update_up_to_date")}</span>
      )}
      {state.kind === "installing" && (
        <span className="font-semibold">{t("update_installing")}</span>
      )}
      {state.kind === "restarting" && (
        <span className="font-semibold">{t("update_ready")}</span>
      )}
      {state.kind === "failed" && (
        <>
          <span className="font-semibold">{t("update_failed", { msg: state.msg })}</span>
          <button
            className="text-[12px] cursor-pointer"
            style={{ color: `${palette.text}99`, background: "none", border: "none" }}
            onClick={() => setDismissed(true)}
          >
            {t("update_dismiss")}
          </button>
        </>
      )}
    </div>
  );
}

// Visible app version — shown in footer so users can confirm an update
// landed. Update this together with Cargo.toml + tauri.conf.json on each
// version bump (handled by the release workflow's tag).
const APP_VERSION = "0.3.4";

function AppInner() {
  const t = useT();
  const { lang } = useLang();
  const [modelsReady, setModelsReady] = useState(false);
  const [modelCount, setModelCount] = useState(0);
  const [status, setStatus] = useState(() => t("status_loading_models"));
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

  // When the user switches language, refresh the status text to the current
  // lifecycle state (Ready/Loading). Errors and transient messages are left
  // alone because they may not have a translation key.
  useEffect(() => {
    setStatus(
      modelsReady
        ? `${t("status_ready")} — ${modelCount} ${t("status_models_loaded")}`
        : t("status_loading_models")
    );
    // We intentionally depend on `lang` (not `t`) so we only refresh on
    // actual language switches, not every re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

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
          setStatus(`${t("status_ready")} — ${resp.count} ${t("status_models_loaded")}`);
        } else if (resp.ok && resp.count === 0) {
          setModelCount(0);
          setModelsReady(false);
          setStatus(t("status_no_models"));
        } else {
          setStatus(t("status_model_failed"));
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.includes("Cannot read properties") || msg.includes("__TAURI__") || msg.includes("invoke")) {
          setStatus(t("status_standalone"));
        } else {
          setStatus(`${t("status_error")}: ${msg.slice(0, 60)}`);
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
        setStatus(t("live"));
        if (saveToHistory) addHistoryEntry(nDefects, pressureX, pressureY, resp.results);
      } else {
        setStatus(`${t("status_error")}: ${resp.error}`);
      }
    } catch (e) {
      if (gen !== generationRef.current) return; // stale
      const msg = e instanceof Error ? e.message : String(e);
      console.error("Prediction failed:", msg);
      setStatus(`${t("status_error")}: ${msg.slice(0, 80)}`);
    } finally {
      if (gen === generationRef.current) {
        predictingRef.current = false;
        setPredicting(false);
      }
    }
  }, [modelsReady, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, t]);

  // Live prediction — auto-triggers on any input change (200ms debounce)
  useEffect(() => {
    if (!modelsReady) return;
    const timer = setTimeout(() => runPrediction(false), 200);
    return () => clearTimeout(timer);
  }, [modelsReady, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, runPrediction]);

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
    setStatus(modelsReady ? `${t("status_ready")} — ${modelCount} ${t("status_models_loaded")}` : t("status_loading_models"));
  }, [modelsReady, modelCount, t]);

  const handleExport = useCallback(() => {
    if (!results) return;
    const text = formatResultsForExport(
      results, nDefects, t,
      t("unit_mpa"), t("unit_mm"), t("unit_deg"),
      pressureX, pressureY, materialKey, layupKey, bcMode, defects,
    );
    navigator.clipboard.writeText(text).then(() => {
      setStatus(t("status_copied"));
      setTimeout(() => setStatus(t("status_analysis_complete")), 2000);
    }).catch(() => {
      setStatus(t("status_copy_failed"));
    });
  }, [results, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, t]);

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
        onReset={handleReset}
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
            className="flex items-center gap-1.5 px-3.5 py-1 rounded-t-md text-[13px] font-semibold transition-all"
            style={{
              background: activeTab === tab.id ? COL.bg : "transparent",
              color: activeTab === tab.id ? COL.accent : COL.textDim,
              borderBottom: activeTab === tab.id ? `2px solid ${COL.accent}` : "2px solid transparent",
              textShadow: activeTab === tab.id ? "0 0 8px rgba(0,234,255,0.5)" : undefined,
              boxShadow: activeTab === tab.id ? "0 1px 12px -2px rgba(0,234,255,0.25)" : undefined,
            }}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="text-[14px]">{tab.icon}</span>
            {t(tab.labelKey)}
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
                  <span className="text-[12px] font-medium" style={{ color: COL.accent, textShadow: "0 0 6px rgba(0,234,255,0.5)" }}>{t("click_to_expand")}</span>
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

      <footer className="h-8 flex items-center justify-center gap-3 text-[11px]" style={{ color: COL.textDim, background: COL.bgDark, borderTop: `1px solid ${COL.border}` }}>
        <span>{t("app_subtitle")}&nbsp;&nbsp;·&nbsp;&nbsp;AENG30017&nbsp;&nbsp;·&nbsp;&nbsp;{t("footer_student")}</span>
        <span style={{ color: COL.accent, opacity: 0.7, textShadow: "0 0 6px rgba(0,234,255,0.3)" }}>v{APP_VERSION}</span>
      </footer>

      {/* Focus Modals */}
      <FocusModal
        open={focusTarget === "canvas"}
        onClose={() => setFocusTarget(null)}
        title={t("plate_preview")}
      >
        <div className="w-full h-full flex items-center justify-center">
          <PlateCanvas {...canvasProps} />
        </div>
      </FocusModal>

      <FocusModal
        open={focusTarget === "results"}
        onClose={() => setFocusTarget(null)}
        title={t("results")}
      >
        <ResultsPanel results={results} nDefects={nDefects} />
      </FocusModal>

      <FocusModal
        open={focusTarget === "laminate"}
        onClose={() => setFocusTarget(null)}
        title={t("laminate")}
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
        title={t("projects")}
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
