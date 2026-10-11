import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { adaptResearchContext } from "./adapter";
import { createStudyState, importStudyState, serializeStudyState, useStudyState } from "./useStudyState";

const context = adaptResearchContext({ title: "Paper", study_tasks: [{ id: "t", title: "Explain" }] });
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear(); });

describe("portable study records", () => {
  it("roundtrips answers, notes and self-checks without granting mastery", () => {
    const state = createStudyState(context);
    state.records.t = { answer: "My answer", notes: "My note", status: "self_checked", source_ids: [], stale: false, skip_reason: "" };
    const imported = importStudyState(serializeStudyState(state), context);
    expect(imported.records.t).toEqual(state.records.t);
    expect(serializeStudyState(imported)).not.toContain("mastered");
  });

  it("marks only answers dependent on changed source fingerprints stale", () => {
    const original = { ...context, sources: [
      { id: "s1", kind: "paper", title: "One", fingerprint: "a" },
      { id: "s2", kind: "code", title: "Two", fingerprint: "b" },
    ] };
    const state = createStudyState(original);
    state.records.one = { answer: "A", notes: "", status: "answered", source_ids: ["s1"], stale: false, skip_reason: "" };
    state.records.two = { answer: "B", notes: "", status: "answered", source_ids: ["s2"], stale: false, skip_reason: "" };
    const changed = { ...original, snapshot_id: "new", sources: original.sources.map(s => ({ ...s, fingerprint: s.id === "s1" ? "changed" : s.fingerprint })) };
    const imported = importStudyState(serializeStudyState(state), changed);
    expect(imported.records.one.stale).toBe(true);
    expect(imported.records.two.stale).toBe(false);
    expect(imported.records.one.answer).toBe("A");
  });

  it("rejects malformed imports without losing the current session", () => {
    expect(() => importStudyState('{"schema_version":90}', context)).toThrow();
    expect(() => importStudyState("not json", context)).toThrow();
  });

  it("allows editing and exporting when storage reads and writes fail", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    const { result } = renderHook(() => useStudyState(context));
    act(() => result.current.updateRecord("t", { answer: "Still retained", status: "answered" }));
    expect(result.current.temporary).toBe(true);
    expect(JSON.parse(result.current.exportState()).records.t.answer).toBe("Still retained");
  });

  it("records claim and paragraph dependencies through the hook and marks changed sources stale on reload", () => {
    const original = { ...context, sources: [
      { id: "s1", kind: "paper", title: "Changed", fingerprint: "before" },
      { id: "s2", kind: "paper", title: "Unchanged", fingerprint: "same" },
    ], anchors: [
      { id: "a1", source_id: "s1", snippet: "Short excerpt", locator: { page: 1 }, locator_status: "valid" },
      { id: "a2", source_id: "s2", snippet: "Other excerpt", locator: { page: 2 }, locator_status: "valid" },
    ], claims: [
      { id: "claim", kind: "methodology", statement: "Claim", anchor_ids: ["a1"], evidence_status: "located" },
      { id: "unaffected", kind: "result", statement: "Other claim", anchor_ids: ["a2"], evidence_status: "located" },
    ] };
    const segments = [{ id: "paragraph", anchor_ids: ["a1"], original_text: "A full paragraph longer than its anchor." }];
    const first = renderHook(() => useStudyState(original, segments));
    act(() => {
      first.result.current.updateRecord("claim", { answer: "Claim answer", status: "answered" });
      first.result.current.updateRecord("paragraph", { notes: "Paragraph note" });
      first.result.current.updateRecord("unaffected", { answer: "Other answer" });
    });
    expect(first.result.current.state.records.claim.source_ids).toEqual(["s1"]);
    expect(first.result.current.state.records.paragraph.source_ids).toEqual(["s1"]);
    const portable = first.result.current.exportState();
    first.unmount();
    const changed = { ...original, snapshot_id: "new", sources: original.sources.map(s => ({ ...s, fingerprint: s.id === "s1" ? "after" : s.fingerprint })) };
    const second = renderHook(() => useStudyState(changed, segments));
    expect(second.result.current.state.records.claim).toMatchObject({ stale: true, answer: "Claim answer" });
    expect(second.result.current.state.records.paragraph).toMatchObject({ stale: true, notes: "Paragraph note" });
    expect(second.result.current.state.records.unaffected.stale).toBe(false);
    act(() => second.result.current.importState(portable));
    expect(second.result.current.state.records.paragraph.stale).toBe(true);
  });
});
