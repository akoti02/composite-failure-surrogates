import { useState, useCallback, useRef, useEffect } from "react";
import { COL } from "../lib/constants";
import {
  type Project, type AnalysisSnapshot, type HistoryEntry,
  createProject, saveProject, loadProject,
  exportProjectJSON, importProjectJSON,
  createSnapshot, addSnapshot, removeSnapshot, updateSnapshot,
  getHistory, clearHistory,
} from "../lib/project";
import type { DefectParams, PredictionResults } from "../lib/types";
import { useT, useLang } from "../lib/i18n";
import type { TKey } from "../lib/i18n";

interface Props {
  // Current app state for saving
  nDefects: number;
  pressureX: number;
  pressureY: number;
  materialKey: string;
  layupKey: string;
  bcMode: string;
  defects: DefectParams[];
  results: PredictionResults | null;
  // Callback to restore a snapshot
  onRestoreSnapshot: (snapshot: AnalysisSnapshot) => void;
  // Comparison mode
  compareSnapshots: AnalysisSnapshot[];
  onToggleCompare: (snapshot: AnalysisSnapshot) => void;
}

function useFormatTime() {
  const t = useT();
  const { lang } = useLang();
  return (ts: number): string => {
    const d = new Date(ts);
    const now = Date.now();
    const diff = now - ts;
    if (diff < 60000) return t("just_now");
    if (diff < 3600000) return t("minutes_ago", { n: Math.floor(diff / 60000) });
    if (diff < 86400000) return t("hours_ago", { n: Math.floor(diff / 3600000) });
    return d.toLocaleDateString(lang === "ru" ? "ru-RU" : "en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  };
}

function SnapshotCard({ snapshot, isActive, isComparing, onRestore, onDelete, onToggleCompare, onUpdateName }: {
  snapshot: AnalysisSnapshot;
  isActive: boolean;
  isComparing: boolean;
  onRestore: () => void;
  onDelete: () => void;
  onToggleCompare: () => void;
  onUpdateName: (name: string) => void;
}) {
  const t = useT();
  const formatTime = useFormatTime();
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(snapshot.name);

  const hasFailed = snapshot.results?.failed_tsai_wu === 1 || snapshot.results?.failed_hashin === 1;
  const hasResults = snapshot.results !== null;

  return (
    <div
      className="p-3 rounded-lg transition-all cursor-pointer group"
      style={{
        background: isActive ? COL.accentMuted : isComparing ? "rgba(127, 219, 255, 0.08)" : COL.card,
        border: `1px solid ${isActive ? COL.borderBright : isComparing ? "rgba(127,219,255,0.3)" : COL.border}`,
        boxShadow: isActive ? COL.accentGlowSoft : undefined,
      }}
      onClick={onRestore}
    >
      <div className="flex items-center gap-2">
        {editing ? (
          <input
            className="text-[13px] font-semibold px-1.5 py-1 rounded outline-none flex-1"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={() => { onUpdateName(editName); setEditing(false); }}
            onKeyDown={(e) => { if (e.key === "Enter") { onUpdateName(editName); setEditing(false); } }}
            onClick={(e) => e.stopPropagation()}
            autoFocus
          />
        ) : (
          <span
            className="text-[13px] font-semibold flex-1"
            style={{ color: COL.text }}
            onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
          >
            {snapshot.name}
          </span>
        )}

        <span className="text-[11px]" style={{ color: COL.textDim }}>{formatTime(snapshot.timestamp)}</span>
      </div>

      <div className="flex items-center gap-2 mt-1.5 text-[11px]" style={{ color: COL.textDim }}>
        <span>{snapshot.nDefects} {t("defects_short")}</span>
        <span>·</span>
        <span>Px={snapshot.pressureX}</span>
        {hasResults && (
          <>
            <span>·</span>
            <span style={{ color: hasFailed ? COL.danger : COL.success, textShadow: `0 0 6px ${hasFailed ? COL.danger : COL.success}77` }}>
              {hasFailed ? t("fail") : t("pass")}
            </span>
            {snapshot.results?.max_s11 != null && (
              <>
                <span>·</span>
                <span>S11={snapshot.results.max_s11.toFixed(0)} {t("unit_mpa")}</span>
              </>
            )}
          </>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          className="text-[11px] px-2 py-1 rounded"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
          onClick={(e) => { e.stopPropagation(); onToggleCompare(); }}
        >
          {isComparing ? t("remove_from_compare") : t("compare")}
        </button>
        <button
          className="text-[11px] px-2 py-1 rounded"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.danger }}
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
        >
          {t("delete")}
        </button>
      </div>
    </div>
  );
}

function ComparisonView({ snapshots }: { snapshots: AnalysisSnapshot[] }) {
  const t = useT();
  if (snapshots.length < 2) {
    return (
      <div className="text-[13px] py-8 text-center" style={{ color: COL.textMid }}>
        {t("compare_hint")}
      </div>
    );
  }

  const fields: { key: keyof PredictionResults; labelKey: TKey; unitKey?: TKey; danger?: number }[] = [
    { key: "tsai_wu_index", labelKey: "of_tsai_wu", danger: 1 },
    { key: "max_s11",       labelKey: "of_max_s11",  unitKey: "unit_mpa" },
    { key: "min_s11",       labelKey: "of_min_s11",  unitKey: "unit_mpa" },
    { key: "max_s12",       labelKey: "of_max_s12",  unitKey: "unit_mpa" },
    { key: "max_hashin_ft", labelKey: "of_hashin_ft", danger: 1 },
    { key: "max_hashin_mt", labelKey: "of_hashin_mt", danger: 1 },
    { key: "max_hashin_mc", labelKey: "of_hashin_mc", danger: 1 },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]" style={{ borderCollapse: "separate", borderSpacing: "0 1px" }}>
        <thead>
          <tr>
            <th className="text-left px-2 py-2" style={{ color: COL.textDim }}>{t("metric")}</th>
            {snapshots.map(s => (
              <th key={s.id} className="text-right px-2 py-2 max-w-[140px]" style={{ color: COL.text }}>
                <div className="truncate">{s.name}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1.5" style={{ color: COL.textDim }}>{t("defects_col")}</td>
            {snapshots.map(s => <td key={s.id} className="text-right px-2 tabular-nums" style={{ color: COL.text }}>{s.nDefects}</td>)}
          </tr>
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1.5" style={{ color: COL.textDim }}>{t("pressure_x")}</td>
            {snapshots.map(s => <td key={s.id} className="text-right px-2 tabular-nums" style={{ color: COL.text }}>{s.pressureX} {t("unit_mpa")}</td>)}
          </tr>
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1.5" style={{ color: COL.textDim }}>{t("pressure_y")}</td>
            {snapshots.map(s => <td key={s.id} className="text-right px-2 tabular-nums" style={{ color: COL.text }}>{s.pressureY} {t("unit_mpa")}</td>)}
          </tr>

          {fields.map(f => {
            const vals = snapshots.map(s => (s.results?.[f.key] as number) ?? null);
            const validVals = vals.filter((v): v is number => v != null && isFinite(v));
            const best = (f.key.includes("hashin") || f.key === "tsai_wu_index") && validVals.length > 0
              ? Math.min(...validVals) : undefined;
            const unit = f.unitKey ? t(f.unitKey) : "";

            return (
              <tr key={f.key} style={{ background: COL.card }}>
                <td className="px-2 py-1.5" style={{ color: COL.textDim }}>{t(f.labelKey)}</td>
                {vals.map((v, i) => {
                  const isDanger = f.danger != null && v != null && v >= f.danger;
                  const isBest = v === best && validVals.length > 1;
                  return (
                    <td
                      key={snapshots[i].id}
                      className="text-right px-2 tabular-nums font-semibold"
                      style={{
                        color: isDanger ? COL.danger : isBest ? COL.success : COL.text,
                        textShadow: isDanger ? `0 0 6px ${COL.danger}77` : isBest ? `0 0 6px ${COL.success}77` : undefined,
                      }}
                    >
                      {v != null && isFinite(v) ? v.toFixed(unit ? 2 : 4) : "--"}
                      {unit && <span className="font-normal text-[10px] ml-0.5" style={{ color: COL.textDim }}>{unit}</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}

          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1.5 font-semibold" style={{ color: COL.textMid }}>{t("verdict")}</td>
            {snapshots.map(s => {
              const failed = s.results?.failed_tsai_wu === 1 || s.results?.failed_hashin === 1;
              return (
                <td key={s.id} className="text-right px-2 font-bold" style={{ color: failed ? COL.danger : COL.success, textShadow: `0 0 6px ${failed ? COL.danger : COL.success}77` }}>
                  {s.results ? (failed ? t("fail") : t("pass")) : "--"}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function HistoryPanel() {
  const t = useT();
  const formatTime = useFormatTime();
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setHistory(getHistory());
  }, []);

  if (history.length === 0) {
    return (
      <div className="text-[13px] py-8 text-center" style={{ color: COL.textMid }}>
        {t("no_history")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[12px] font-semibold" style={{ color: COL.textMid }}>
          {t("n_analyses", { n: history.length })}
        </span>
        <button
          className="text-[11px] px-2 py-1 rounded"
          style={{ border: `1px solid ${COL.border}`, color: COL.textDim }}
          onClick={() => { clearHistory(); setHistory([]); }}
        >
          {t("clear")}
        </button>
      </div>
      <div className="max-h-80 overflow-y-auto flex flex-col gap-0.5">
        {[...history].reverse().slice(0, 50).map(h => {
          const failed = h.failedTsaiWu || h.failedHashin;
          return (
            <div
              key={h.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded text-[11px]"
              style={{ background: COL.card, border: `1px solid ${COL.border}` }}
            >
              <span style={{ color: COL.textDim }}>{formatTime(h.timestamp)}</span>
              <span style={{ color: COL.textMid }}>{h.nDefects}d Px={h.pressureX}</span>
              <span className="ml-auto tabular-nums" style={{ color: COL.text }}>
                {h.maxS11 != null ? `S11=${h.maxS11.toFixed(0)} ${t("unit_mpa")}` : "--"}
              </span>
              <span style={{ color: failed ? COL.danger : COL.success, textShadow: failed != null ? `0 0 6px ${failed ? COL.danger : COL.success}77` : undefined }}>
                {failed == null ? "·" : failed ? t("fail") : t("pass")}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ProjectManager({
  nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, results,
  onRestoreSnapshot, compareSnapshots, onToggleCompare,
}: Props) {
  const t = useT();
  const [project, setProject] = useState<Project>(() => loadProject() || createProject());
  const [tab, setTab] = useState<"snapshots" | "compare" | "history">("snapshots");
  const [saveName, setSaveName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-save project on change
  useEffect(() => {
    saveProject(project);
  }, [project]);

  const handleSave = useCallback(() => {
    const name = saveName.trim() || `${t("default_analysis_name")} ${project.snapshots.length + 1}`;
    const snap = createSnapshot(name, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, results);
    setProject(prev => addSnapshot(prev, snap));
    setSaveName("");
  }, [saveName, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, results, project.snapshots.length, t]);

  const handleDelete = useCallback((id: string) => {
    setProject(prev => removeSnapshot(prev, id));
  }, []);

  const handleExport = useCallback(() => {
    const json = exportProjectJSON(project);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.name.replace(/\s+/g, "_")}.rp3.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [project]);

  const handleImport = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const imported = importProjectJSON(reader.result as string);
        if (imported) {
          setProject(imported);
        } else {
          alert(t("import_failed"));
        }
      } catch (err) {
        alert(`${t("import_failed_prefix")}: ${err}`);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }, [t]);

  const tabs = [
    { id: "snapshots" as const, label: `${t("snapshots_title")} (${project.snapshots.length})` },
    { id: "compare" as const, label: `${t("compare_title")} (${compareSnapshots.length})` },
    { id: "history" as const, label: t("history_title") },
  ];

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Project header */}
      <div className="flex items-center gap-2">
        <input
          className="text-[15px] font-semibold px-2 py-1.5 rounded-md outline-none"
          style={{ background: "transparent", color: COL.text, border: `1px solid transparent` }}
          value={project.name}
          onChange={(e) => setProject(prev => ({ ...prev, name: e.target.value }))}
          onFocus={(e) => (e.target.style.borderColor = COL.borderBright)}
          onBlur={(e) => (e.target.style.borderColor = "transparent")}
        />

        <div className="ml-auto flex items-center gap-1.5">
          <button
            className="text-[12px] px-3 py-1.5 rounded-md btn-press"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            onClick={handleExport}
          >
            {t("export_rp3")}
          </button>
          <button
            className="text-[12px] px-3 py-1.5 rounded-md btn-press"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            onClick={() => fileInputRef.current?.click()}
          >
            {t("import_rp3")}
          </button>
          <input ref={fileInputRef} type="file" accept=".json,.rp3.json" className="hidden" onChange={handleImport} />
        </div>
      </div>

      {/* Save new snapshot */}
      <div className="flex items-center gap-2">
        <input
          className="flex-1 text-[13px] px-3 py-2 rounded-md outline-none"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
          value={saveName}
          onChange={(e) => setSaveName(e.target.value)}
          placeholder={t("snapshot_placeholder")}
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); }}
        />
        <button
          className="px-4 py-2 rounded-md text-[13px] font-semibold btn-press"
          style={{ background: COL.accent, color: "#041017", border: `1px solid rgba(0,234,255,0.5)`, boxShadow: "0 0 14px rgba(0,234,255,0.4)" }}
          onClick={handleSave}
        >
          {t("save")}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b" style={{ borderColor: COL.border }}>
        {tabs.map(tabItem => (
          <button
            key={tabItem.id}
            className="px-3.5 py-2 text-[13px] font-semibold transition-colors"
            style={{
              color: tab === tabItem.id ? COL.accent : COL.textDim,
              borderBottom: tab === tabItem.id ? `2px solid ${COL.accent}` : "2px solid transparent",
              textShadow: tab === tabItem.id ? "0 0 6px rgba(0,234,255,0.4)" : undefined,
            }}
            onClick={() => setTab(tabItem.id)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "snapshots" && (
          <div className="flex flex-col gap-1.5">
            {project.snapshots.length === 0 ? (
              <div className="text-[13px] py-8 text-center" style={{ color: COL.textMid }}>
                {t("no_snapshots")}
              </div>
            ) : (
              [...project.snapshots].reverse().map(snap => (
                <SnapshotCard
                  key={snap.id}
                  snapshot={snap}
                  isActive={snap.id === project.activeSnapshotId}
                  isComparing={compareSnapshots.some(c => c.id === snap.id)}
                  onRestore={() => {
                    onRestoreSnapshot(snap);
                    setProject(prev => ({ ...prev, activeSnapshotId: snap.id }));
                  }}
                  onDelete={() => handleDelete(snap.id)}
                  onToggleCompare={() => onToggleCompare(snap)}
                  onUpdateName={(name) => setProject(prev => updateSnapshot(prev, snap.id, { name }))}
                />
              ))
            )}
          </div>
        )}

        {tab === "compare" && <ComparisonView snapshots={compareSnapshots} />}
        {tab === "history" && <HistoryPanel />}
      </div>
    </div>
  );
}
