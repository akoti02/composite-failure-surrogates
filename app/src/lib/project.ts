/**
 * Project system: save/load analysis configurations + results.
 * Uses localStorage for persistence (Tauri desktop app).
 */

import type { DefectParams, PredictionResults } from "./types";

/** A single saved analysis snapshot */
export interface AnalysisSnapshot {
  id: string;
  name: string;
  timestamp: number;
  // Inputs
  nDefects: number;
  pressureX: number;
  pressureY: number;
  plyThickness: number;
  layupRotation: number;
  defects: DefectParams[];
  // Results (if run)
  results: PredictionResults | null;
  // Metadata
  notes: string;
  tags: string[];
}

/** Project file containing multiple snapshots */
export interface Project {
  version: number;
  name: string;
  created: number;
  modified: number;
  snapshots: AnalysisSnapshot[];
  activeSnapshotId: string | null;
}

const STORAGE_KEY = "rp3_project";
const HISTORY_KEY = "rp3_history";
const MAX_UNDO = 50;

/** Generate a unique ID */
function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

/** Create a new empty project */
export function createProject(name = "Untitled Project"): Project {
  return {
    version: 1,
    name,
    created: Date.now(),
    modified: Date.now(),
    snapshots: [],
    activeSnapshotId: null,
  };
}

/** Save project to localStorage */
export function saveProject(project: Project): void {
  try {
    const toSave = { ...project, modified: Date.now() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
  } catch (e) {
    console.error("Failed to save project:", e);
  }
}

/** Load project from localStorage */
export function loadProject(): Project | null {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return null;
    return JSON.parse(data) as Project;
  } catch {
    return null;
  }
}

/** Export project as JSON string (for file download) */
export function exportProjectJSON(project: Project): string {
  return JSON.stringify(project, null, 2);
}

/** Import project from JSON string */
export function importProjectJSON(json: string): Project | null {
  try {
    const proj = JSON.parse(json) as Project;
    if (!proj.version || !proj.snapshots) return null;
    return proj;
  } catch {
    return null;
  }
}

/** Create a snapshot from current app state */
export function createSnapshot(
  name: string,
  nDefects: number,
  pressureX: number,
  pressureY: number,
  plyThickness: number,
  layupRotation: number,
  defects: DefectParams[],
  results: PredictionResults | null,
  notes = "",
  tags: string[] = [],
): AnalysisSnapshot {
  return {
    id: uid(),
    name,
    timestamp: Date.now(),
    nDefects,
    pressureX,
    pressureY,
    plyThickness,
    layupRotation,
    defects: defects.map(d => ({ ...d })),
    results: results ? { ...results } : null,
    notes,
    tags,
  };
}

/** Add snapshot to project */
export function addSnapshot(project: Project, snapshot: AnalysisSnapshot): Project {
  return {
    ...project,
    modified: Date.now(),
    snapshots: [...project.snapshots, snapshot],
    activeSnapshotId: snapshot.id,
  };
}

/** Remove snapshot from project */
export function removeSnapshot(project: Project, snapshotId: string): Project {
  return {
    ...project,
    modified: Date.now(),
    snapshots: project.snapshots.filter(s => s.id !== snapshotId),
    activeSnapshotId: project.activeSnapshotId === snapshotId ? null : project.activeSnapshotId,
  };
}

/** Update snapshot in project */
export function updateSnapshot(project: Project, snapshotId: string, updates: Partial<AnalysisSnapshot>): Project {
  return {
    ...project,
    modified: Date.now(),
    snapshots: project.snapshots.map(s =>
      s.id === snapshotId ? { ...s, ...updates } : s
    ),
  };
}

// ─── Undo/Redo System ───

export interface UndoState {
  past: string[];     // JSON-serialized states
  future: string[];
}

export function createUndoState(): UndoState {
  return { past: [], future: [] };
}

export function pushUndoState(undo: UndoState, stateJSON: string): UndoState {
  const past = [...undo.past, stateJSON];
  if (past.length > MAX_UNDO) past.shift();
  return { past, future: [] };
}

export function undoState(undo: UndoState, currentJSON: string): { undo: UndoState; restored: string } | null {
  if (undo.past.length === 0) return null;
  const past = [...undo.past];
  const restored = past.pop()!;
  return {
    undo: { past, future: [...undo.future, currentJSON] },
    restored,
  };
}

export function redoState(undo: UndoState, currentJSON: string): { undo: UndoState; restored: string } | null {
  if (undo.future.length === 0) return null;
  const future = [...undo.future];
  const restored = future.pop()!;
  return {
    undo: { past: [...undo.past, currentJSON], future },
    restored,
  };
}

// ─── Analysis History ───

/** Lightweight history entry (auto-saved after each prediction) */
export interface HistoryEntry {
  id: string;
  timestamp: number;
  nDefects: number;
  pressureX: number;
  pressureY: number;
  maxMises: number | null;
  tsaiWuIndex: number | null;
  failedTsaiWu: boolean | null;
  failedHashin: boolean | null;
}

export function addHistoryEntry(
  nDefects: number,
  pressureX: number,
  pressureY: number,
  results: PredictionResults,
): void {
  try {
    const history = getHistory();
    history.push({
      id: uid(),
      timestamp: Date.now(),
      nDefects,
      pressureX,
      pressureY,
      maxMises: results.max_mises ?? null,
      tsaiWuIndex: results.tsai_wu_index ?? null,
      failedTsaiWu: results.failed_tsai_wu != null ? results.failed_tsai_wu === 1 : null,
      failedHashin: results.failed_hashin != null ? results.failed_hashin === 1 : null,
    });
    // Keep last 500 entries
    if (history.length > 500) history.splice(0, history.length - 500);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch { /* localStorage full or unavailable */ }
}

export function getHistory(): HistoryEntry[] {
  try {
    const data = localStorage.getItem(HISTORY_KEY);
    if (!data) return [];
    return JSON.parse(data) as HistoryEntry[];
  } catch {
    return [];
  }
}

export function clearHistory(): void {
  localStorage.removeItem(HISTORY_KEY);
}
