import { useWorkbench } from "./WorkbenchProvider";
import { emptyRecord, type RecordStatus } from "./useStudyState";

export function StudyRecordEditor({ id }: { id: string }) {
  const { study, t } = useWorkbench();
  const record = study.state.records[id] || emptyRecord();
  return <section className="record-editor">
    {record.stale && <div className="status-note warning"><p>{t("stale")}</p><button type="button" onClick={() => study.updateRecord(id, { stale: false })}>{t("rechecked")}</button></div>}
    <label>{t("answer")}<textarea value={record.answer} rows={6} onChange={e => study.updateRecord(id, { answer: e.target.value })} /></label>
    <label>{t("note")}<textarea value={record.notes} rows={4} onChange={e => study.updateRecord(id, { notes: e.target.value })} /></label>
    <label>{t("status")}<select value={record.status} onChange={e => study.updateRecord(id, { status: e.target.value as RecordStatus })}>
      {(["not_started", "in_progress", "answered", "self_checked", "reviewed", "skipped"] as const).map(s => <option key={s} value={s}>{t(s)}</option>)}
    </select></label>
    {record.status === "reviewed" && <label>{t("reviewSource")}<input value={record.review_source || ""} onChange={e => study.updateRecord(id, { review_source: e.target.value })} /></label>}
    {record.status === "skipped" && <label>{t("skipReason")}<textarea value={record.skip_reason} onChange={e => study.updateRecord(id, { skip_reason: e.target.value })} /></label>}
  </section>;
}
