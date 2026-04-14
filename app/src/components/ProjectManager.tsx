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

function formatTime(ts: number): string {
  const d = new Date(ts);
  const now = Date.now();
  const diff = now - ts;
  if (diff < 60000) return "just now";
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
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
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(snapshot.name);

  const hasFailed = snapshot.results?.failed_tsai_wu === 1 || snapshot.results?.failed_hashin === 1;
  const hasResults = snapshot.results !== null;

  return (
    <div
      className="p-2.5 rounded-lg transition-all cursor-pointer group"
      style={{
        background: isActive ? COL.accentMuted : isComparing ? "rgba(56, 189, 248, 0.06)" : COL.card,
        border: `1px solid ${isActive ? `${COL.accent}40` : isComparing ? "rgba(56,189,248,0.2)" : COL.border}`,
      }}
      onClick={onRestore}
    >
      <div className="flex items-center gap-2">
        {editing ? (
          <input
            className="text-[11px] font-semibold px-1 py-0.5 rounded outline-none flex-1"
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
            className="text-[11px] font-semibold flex-1"
            style={{ color: COL.text }}
            onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
          >
            {snapshot.name}
          </span>
        )}

        <span className="text-[9px]" style={{ color: COL.textDim }}>{formatTime(snapshot.timestamp)}</span>
      </div>

      <div className="flex items-center gap-2 mt-1.5 text-[9px]" style={{ color: COL.textDim }}>
        <span>{snapshot.nDefects} defects</span>
        <span>·</span>
        <span>Px={snapshot.pressureX}</span>
        {hasResults && (
          <>
            <span>·</span>
            <span style={{ color: hasFailed ? COL.danger : COL.success }}>
              {hasFailed ? "FAIL" : "PASS"}
            </span>
            {snapshot.results?.max_s11 != null && (
              <>
                <span>·</span>
                <span>S11={snapshot.results.max_s11.toFixed(0)} MPa</span>
              </>
            )}
          </>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          className="text-[9px] px-2 py-0.5 rounded"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
          onClick={(e) => { e.stopPropagation(); onToggleCompare(); }}
        >
          {isComparing ? "Remove from compare" : "Compare"}
        </button>
        <button
          className="text-[9px] px-2 py-0.5 rounded"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.danger }}
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

function ComparisonView({ snapshots }: { snapshots: AnalysisSnapshot[] }) {
  if (snapshots.length < 2) {
    return (
      <div className="text-[11px] py-8 text-center" style={{ color: COL.textDim }}>
        Select 2+ snapshots to compare
      </div>
    );
  }

  const fields: { key: keyof PredictionResults; label: string; unit: string; danger?: number }[] = [
    { key: "tsai_wu_index", label: "Tsai-Wu Index", unit: "", danger: 1 },
    { key: "max_s11", label: "Max S11", unit: "MPa" },
    { key: "min_s11", label: "Min S11", unit: "MPa" },
    { key: "max_s12", label: "Max S12", unit: "MPa" },
    { key: "max_hashin_ft", label: "Hashin FT", unit: "", danger: 1 },
    { key: "max_hashin_mt", label: "Hashin MT", unit: "", danger: 1 },
    { key: "max_hashin_mc", label: "Hashin MC", unit: "", danger: 1 },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]" style={{ borderCollapse: "separate", borderSpacing: "0 1px" }}>
        <thead>
          <tr>
            <th className="text-left px-2 py-1.5" style={{ color: COL.textDim }}>Metric</th>
            {snapshots.map(s => (
              <th key={s.id} className="text-right px-2 py-1.5 max-w-[120px]" style={{ color: COL.textMid }}>
                <div className="truncate">{s.name}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* Input comparison */}
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1" style={{ color: COL.textDim }}>Defects</td>
            {snapshots.map(s => <td key={s.id} className="text-right px-2 tabular-nums" style={{ color: COL.text }}>{s.nDefects}</td>)}
          </tr>
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1" style={{ color: COL.textDim }}>Pressure X</td>
            {snapshots.map(s => <td key={s.id} className="text-right px-2 tabular-nums" style={{ color: COL.text }}>{s.pressureX} MPa</td>)}
          </tr>
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1" style={{ color: COL.textDim }}>Pressure Y</td>
            {snapshots.map(s => <td key={s.id} className="text-right px-2 tabular-nums" style={{ color: COL.text }}>{s.pressureY} MPa</td>)}
          </tr>

          {/* Results comparison */}
          {fields.map(f => {
            const vals = snapshots.map(s => (s.results?.[f.key] as number) ?? null);
            const validVals = vals.filter((v): v is number => v != null && isFinite(v));
            const best = (f.key.includes("hashin") || f.key === "tsai_wu_index") && validVals.length > 0
              ? Math.min(...validVals) : undefined;

            return (
              <tr key={f.key} style={{ background: COL.card }}>
                <td className="px-2 py-1" style={{ color: COL.textDim }}>{f.label}</td>
                {vals.map((v, i) => {
                  const isDanger = f.danger != null && v != null && v >= f.danger;
                  const isBest = v === best && validVals.length > 1;
                  return (
                    <td
                      key={snapshots[i].id}
                      className="text-right px-2 tabular-nums font-semibold"
                      style={{
                        color: isDanger ? COL.danger : isBest ? COL.success : COL.text,
                      }}
                    >
                      {v != null && isFinite(v) ? v.toFixed(f.unit ? 2 : 4) : "--"}
                      {f.unit && <span className="font-normal text-[8px] ml-0.5" style={{ color: COL.textDim }}>{f.unit}</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}

          {/* Verdict */}
          <tr style={{ background: COL.bgDark }}>
            <td className="px-2 py-1 font-semibold" style={{ color: COL.textMid }}>Verdict</td>
            {snapshots.map(s => {
              const failed = s.results?.failed_tsai_wu === 1 || s.results?.failed_hashin === 1;
              return (
                <td key={s.id} className="text-right px-2 font-bold" style={{ color: failed ? COL.danger : COL.success }}>
                  {s.results ? (failed ? "FAIL" : "PASS") : "--"}
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
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setHistory(getHistory());
  }, []);

  if (history.length === 0) {
    return (
      <div className="text-[11px] py-8 text-center" style={{ color: COL.textDim }}>
        No analysis history yet
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-semibold" style={{ color: COL.textMid }}>
          {history.length} analyses
        </span>
        <button
          className="text-[9px] px-2 py-0.5 rounded"
          style={{ border: `1px solid ${COL.border}`, color: COL.textDim }}
          onClick={() => { clearHistory(); setHistory([]); }}
        >
          Clear
        </button>
      </div>
      <div className="max-h-80 overflow-y-auto flex flex-col gap-0.5">
        {[...history].reverse().slice(0, 50).map(h => {
          const failed = h.failedTsaiWu || h.failedHashin;
          return (
            <div
              key={h.id}
              className="flex items-center gap-2 px-2 py-1 rounded text-[9px]"
              style={{ background: COL.card, border: `1px solid ${COL.border}` }}
            >
              <span style={{ color: COL.textDim }}>{formatTime(h.timestamp)}</span>
              <span style={{ color: COL.textMid }}>{h.nDefects}d Px={h.pressureX}</span>
              <span className="ml-auto tabular-nums" style={{ color: COL.text }}>
                {h.maxS11 != null ? `S11=${h.maxS11.toFixed(0)} MPa` : "--"}
              </span>
              <span style={{ color: failed ? COL.danger : COL.success }}>
                {failed == null ? "·" : failed ? "FAIL" : "PASS"}
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
  const [project, setProject] = useState<Project>(() => loadProject() || createProject());
  const [tab, setTab] = useState<"snapshots" | "compare" | "history">("snapshots");
  const [saveName, setSaveName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-save project on change
  useEffect(() => {
    saveProject(project);
  }, [project]);

  const handleSave = useCallback(() => {
    const name = saveName.trim() || `Analysis ${project.snapshots.length + 1}`;
    const snap = createSnapshot(name, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, results);
    setProject(prev => addSnapshot(prev, snap));
    setSaveName("");
  }, [saveName, nDefects, pressureX, pressureY, materialKey, layupKey, bcMode, defects, results, project.snapshots.length]);

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
          alert("Failed to import: invalid project file format");
        }
      } catch (err) {
        alert(`Failed to import project: ${err}`);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }, []);

  const tabs = [
    { id: "snapshots" as const, label: `Snapshots (${project.snapshots.length})` },
    { id: "compare" as const, label: `Compare (${compareSnapshots.length})` },
    { id: "history" as const, label: "History" },
  ];

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Project header */}
      <div className="flex items-center gap-2">
        <input
          className="text-[13px] font-semibold px-2 py-1 rounded-md outline-none"
          style={{ background: "transparent", color: COL.text, border: `1px solid transparent` }}
          value={project.name}
          onChange={(e) => setProject(prev => ({ ...prev, name: e.target.value }))}
          onFocus={(e) => (e.target.style.borderColor = COL.borderMed)}
          onBlur={(e) => (e.target.style.borderColor = "transparent")}
        />

        <div className="ml-auto flex items-center gap-1.5">
          <button
            className="text-[10px] px-2.5 py-1 rounded-md"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            onClick={handleExport}
          >
            Export .rp3
          </button>
          <button
            className="text-[10px] px-2.5 py-1 rounded-md"
            style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.textMid }}
            onClick={() => fileInputRef.current?.click()}
          >
            Import
          </button>
          <input ref={fileInputRef} type="file" accept=".json,.rp3.json" className="hidden" onChange={handleImport} />
        </div>
      </div>

      {/* Save new snapshot */}
      <div className="flex items-center gap-2">
        <input
          className="flex-1 text-[11px] px-2.5 py-1.5 rounded-md outline-none"
          style={{ background: COL.panel, border: `1px solid ${COL.border}`, color: COL.text }}
          value={saveName}
          onChange={(e) => setSaveName(e.target.value)}
          placeholder="Snapshot name..."
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); }}
        />
        <button
          className="px-3 py-1.5 rounded-md text-[11px] font-semibold btn-press"
          style={{ background: COL.accent, color: "#fff", border: `1px solid rgba(99,102,241,0.3)` }}
          onClick={handleSave}
        >
          Save
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b" style={{ borderColor: COL.border }}>
        {tabs.map(t => (
          <button
            key={t.id}
            className="px-3 py-1.5 text-[11px] font-semibold transition-colors"
            style={{
              color: tab === t.id ? COL.accent : COL.textDim,
              borderBottom: tab === t.id ? `2px solid ${COL.accent}` : "2px solid transparent",
            }}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "snapshots" && (
          <div className="flex flex-col gap-1.5">
            {project.snapshots.length === 0 ? (
              <div className="text-[11px] py-8 text-center" style={{ color: COL.textDim }}>
                No saved snapshots. Run an analysis and save it.
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
