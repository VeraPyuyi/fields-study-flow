import { Circle, CircleCheck, Clock3 } from "lucide-react";
import { useWorkbench } from "./WorkbenchProvider";
import { LearningIssues, learningStepLabel } from "./learningStatus";

export function LearningRail() {
  const { context, study, t, showContext, language, roadmap } = useWorkbench();
  const selected = study.state.selection;
  return <nav className="learning-rail" aria-label={t("steps")}>
    <h2>{t("steps")}</h2>
    {!context.learning_steps.length && <p className="empty-state">{t("noSteps")}</p>}
    <ol>{context.learning_steps.map((step, i) => {
      const record = study.state.records[step.id];
      const active = selected.stepId === step.id || (!selected.stepId && !!selected.claimId && step.claim_ids.includes(selected.claimId));
      return <li key={step.id}><button className={`step-button ${active ? "active" : ""}`} type="button" aria-current={active ? "step" : undefined}
        onClick={() => { study.select({ stepId: step.id, claimId: step.claim_ids[0], anchorId: step.anchor_ids[0], segmentId: undefined, taskId: undefined }); showContext(); }}>
        <span className="step-index">{record?.status === "self_checked" || record?.status === "reviewed" ? <CircleCheck size={16} /> : <Circle size={16} />}{i + 1}</span>
        <span className="step-label">{learningStepLabel(step, context, language, roadmap.profile?.learning_outcome)}<LearningIssues step={step} /><small>{record?.stale ? t("stale") : record ? t(record.status) : t("not_started")}</small>
          <small><Clock3 size={12} />{step.estimated_minutes ? `${step.estimated_minutes} ${t("minutes")}` : t("estimate")}</small></span>
      </button></li>;
    })}</ol>
  </nav>;
}
