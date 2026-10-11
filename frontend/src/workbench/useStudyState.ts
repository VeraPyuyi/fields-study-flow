import { useCallback, useEffect, useRef, useState } from "react";
import type { PaperLensSegment, ResearchContext, StudyTask } from "../types";
import { fingerprint, recordDependencies, recordSourceIds } from "./adapter";

export type RecordStatus = "not_started" | "in_progress" | "answered" | "self_checked" | "reviewed" | "skipped";
export type StudyRecord = { answer: string; notes: string; status: RecordStatus; source_ids: string[];
  stale: boolean; skip_reason: string; review_source?: string };
export type GraphState = { positions: Record<string, { x: number; y: number }>; expanded: string[];
  viewport?: { x: number; y: number; zoom: number }; selected?: string };
export type Selection = { claimId?: string; anchorId?: string; stepId?: string; segmentId?: string; taskId?: string };
export type StudyState = {
  schema_version: 1; bundle_id: string; snapshot_id: string; source_fingerprints: Record<string, string>;
  records: Record<string, StudyRecord>; graph: GraphState; selection: Selection;
  semantic_fingerprint?: string; record_signatures?: Record<string, string>;
};
const statuses: RecordStatus[] = ["not_started", "in_progress", "answered", "self_checked", "reviewed", "skipped"];
const session = new Map<string, string>();
export const emptyRecord = (): StudyRecord => ({ answer: "", notes: "", status: "not_started", source_ids: [], stale: false, skip_reason: "" });
function semanticFingerprint(context: ResearchContext, segments: PaperLensSegment[], tasks: StudyTask[]) {
  return fingerprint({ claims: context.claims, anchors: context.anchors, steps: context.learning_steps, segments, tasks });
}
function recordSignature(context: ResearchContext, id: string, segments: PaperLensSegment[], tasks: StudyTask[]) {
  const dependencies = recordDependencies(context, id, segments, tasks);
  return fingerprint({ ...dependencies, claims: [...dependencies.claims].sort((a, b) => a.id.localeCompare(b.id)),
    anchors: [...dependencies.anchors].sort((a, b) => a.id.localeCompare(b.id)), sourceIds: [...dependencies.sourceIds].sort() });
}
export function createStudyState(context: ResearchContext, segments: PaperLensSegment[] = [], tasks: StudyTask[] = []): StudyState {
  return { schema_version: 1, bundle_id: context.bundle_id, snapshot_id: context.snapshot_id,
    source_fingerprints: Object.fromEntries(context.sources.map(s => [s.id, s.fingerprint])), records: {},
    graph: { positions: {}, expanded: [] }, selection: {}, semantic_fingerprint: semanticFingerprint(context, segments, tasks), record_signatures: {} };
}
export function serializeStudyState(state: StudyState): string { return JSON.stringify(state, null, 2); }
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const strings = (v: unknown): string[] => Array.isArray(v) ? v.filter((s): s is string => typeof s === "string") : [];
const safeKey = (key: string) => !["__proto__", "constructor", "prototype"].includes(key);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function importStudyState(text: string, context: ResearchContext, segments: PaperLensSegment[] = [], tasks: StudyTask[] = []): StudyState {
  if (text.length > 10_000_000) throw new Error("Study file too large");
  const parsed: unknown = JSON.parse(text);
  if (!object(parsed) || parsed.schema_version !== 1 || typeof parsed.bundle_id !== "string" || !object(parsed.records)) throw new Error("Invalid study state");
  const state = createStudyState(context, segments, tasks);
  const fingerprints = object(parsed.source_fingerprints) ? parsed.source_fingerprints : {};
  const signatures = object(parsed.record_signatures) ? parsed.record_signatures : {};
  const semanticsChanged = parsed.semantic_fingerprint !== state.semantic_fingerprint;
  const fingerprintsChanged = fingerprint(fingerprints) !== fingerprint(state.source_fingerprints);
  const unknownSnapshotChange = parsed.snapshot_id !== context.snapshot_id && !fingerprintsChanged && !semanticsChanged;
  for (const [id, value] of Object.entries(parsed.records)) {
    if (!safeKey(id) || !object(value)) continue;
    const sourceIds = [...new Set([...strings(value.source_ids), ...recordSourceIds(context, id, segments, tasks)])];
    const signature = recordSignature(context, id, segments, tasks);
    const semanticStale = typeof signatures[id] === "string" ? signatures[id] !== signature
      : semanticsChanged || (parsed.semantic_fingerprint === undefined && parsed.snapshot_id !== context.snapshot_id);
    state.record_signatures![id] = signature;
    const status = statuses.includes(value.status as RecordStatus) ? value.status as RecordStatus : "not_started";
    state.records[id] = { answer: typeof value.answer === "string" ? value.answer : "", notes: typeof value.notes === "string" ? value.notes : "",
      status, source_ids: sourceIds, skip_reason: typeof value.skip_reason === "string" ? value.skip_reason : "",
      review_source: typeof value.review_source === "string" ? value.review_source : undefined,
      stale: value.stale === true || semanticStale || unknownSnapshotChange || parsed.bundle_id !== context.bundle_id || sourceIds.some(s => !state.source_fingerprints[s] || fingerprints[s] !== state.source_fingerprints[s]) };
  }
  if (parsed.bundle_id === context.bundle_id && object(parsed.graph)) {
    const positions = object(parsed.graph.positions) ? parsed.graph.positions : {};
    for (const [id, point] of Object.entries(positions)) {
      if (safeKey(id) && object(point) && finite(point.x) && finite(point.y)) state.graph.positions[id] = { x: point.x, y: point.y };
    }
    state.graph.expanded = strings(parsed.graph.expanded);
    if (typeof parsed.graph.selected === "string") state.graph.selected = parsed.graph.selected;
    const v = parsed.graph.viewport;
    if (object(v) && finite(v.x) && finite(v.y) && finite(v.zoom) && v.zoom >= 0.65 && v.zoom <= 2) state.graph.viewport = { x: v.x, y: v.y, zoom: v.zoom };
    if (object(parsed.selection)) {
      for (const key of ["claimId", "anchorId", "stepId", "segmentId", "taskId"] as const) {
        if (typeof parsed.selection[key] === "string") state.selection[key] = parsed.selection[key];
      }
    }
  }
  return state;
}

export function useStudyState(context: ResearchContext, segments: PaperLensSegment[] = [], tasks: StudyTask[] = []) {
  const key = `fields-study-flow:study:v1:${context.bundle_id}`;
  const [loaded] = useState(() => {
    try {
      const value = localStorage.getItem(key);
      return { state: value ? importStudyState(value, context, segments, tasks) : createStudyState(context, segments, tasks), temporary: false };
    } catch {
      let state = createStudyState(context, segments, tasks);
      try { const value = session.get(key); if (value) state = importStudyState(value, context, segments, tasks); } catch { /* Corrupt records do not block reading. */ }
      return { state, temporary: true };
    }
  });
  const [state, setState] = useState(loaded.state);
  const [temporary, setTemporary] = useState(loaded.temporary);
  const [importRevision, setImportRevision] = useState(0);
  const revision = fingerprint([context.bundle_id, context.snapshot_id, semanticFingerprint(context, segments, tasks), context.sources.map(s => [s.id, s.fingerprint])]);
  const previousRevision = useRef(revision);
  useEffect(() => {
    if (previousRevision.current === revision) return;
    previousRevision.current = revision;
    setState(previous => importStudyState(serializeStudyState(previous), context, segments, tasks));
  }, [revision, context, segments, tasks]);
  useEffect(() => {
    const text = serializeStudyState(state);
    session.set(key, text);
    try { localStorage.setItem(key, text); } catch { setTemporary(true); }
  }, [key, state]);
  const updateRecord = useCallback((id: string, patch: Partial<StudyRecord>) => {
    if (!safeKey(id)) return;
    setState(previous => {
      const record = { ...emptyRecord(), ...previous.records[id], ...patch };
      const sourceIds = recordSourceIds(context, id, segments, tasks);
      record.source_ids = patch.stale === false ? sourceIds : [...new Set([...record.source_ids, ...sourceIds])];
      const signature = patch.stale === false || !previous.record_signatures?.[id] ? recordSignature(context, id, segments, tasks) : previous.record_signatures[id];
      return { ...previous, records: { ...previous.records, [id]: record }, record_signatures: { ...previous.record_signatures, [id]: signature } };
    });
  }, [context, segments, tasks]);
  const updateGraph = useCallback((patch: Partial<GraphState>) => setState(s => ({ ...s, graph: { ...s.graph, ...patch } })), []);
  const select = useCallback((selection: Selection) => setState(s => ({ ...s, selection: { ...s.selection, ...selection } })), []);
  return { state, temporary, importRevision, updateRecord, updateGraph, select,
    exportState: () => serializeStudyState(state),
    importState: (text: string) => { const next = importStudyState(text, context, segments, tasks); setState(next); setImportRevision(v => v + 1); } };
}
