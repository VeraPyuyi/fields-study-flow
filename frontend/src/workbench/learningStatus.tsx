import type { LearningStep, ResearchContext } from "../types";
import type { Language } from "./messages";
import { domainLabel } from "./domainLabels";
import { useWorkbench } from "./WorkbenchProvider";

export function learningStepLabel(step: LearningStep, context: ResearchContext, language: Language, outcome?: string) {
  const title = step.title.trim();
  const statement = context.claims.find(c => step.claim_ids.includes(c.id) && title.length >= 80 && (c.statement.trim().startsWith(title) || title === c.statement.trim()));
  if (!statement) return title;
  const kind = domainLabel(statement.kind, language);
  if (language === "en") return `${outcome === "present" ? "Explain" : outcome === "extend" ? "Extend" : "Understand"} ${kind.toLowerCase()}`;
  return `${outcome === "present" ? "讲清" : outcome === "extend" ? "接手" : "理解"}${kind}`;
}

export function learningIssues(step: LearningStep, context: ResearchContext) {
  const steps = new Map(context.learning_steps.map(s => [s.id, s]));
  const missing = !!step.missing_prerequisite_ids?.length || step.prerequisite_ids.some(id => !steps.has(id));
  const visited = new Set<string>();
  const queue = [...step.prerequisite_ids];
  let cycle = !!step.prerequisite_cycle || !!step.blocked_by_cycle;
  while (queue.length) {
    const id = queue.pop()!;
    if (id === step.id) { cycle = true; break; }
    if (visited.has(id)) continue;
    visited.add(id);
    queue.push(...(steps.get(id)?.prerequisite_ids || []));
  }
  return { material: step.status === "needs_material", missing, cycle, review: step.prerequisite_review_required && !cycle && !missing };
}
export function LearningIssues({ step }: { step: LearningStep }) {
  const { context, t } = useWorkbench();
  const issues = learningIssues(step, context);
  return <span className="learning-issues">
    {issues.material && <small className="warning">{t("missing")}</small>}
    {issues.missing && <small className="warning">{t("missingPrerequisites")}</small>}
    {issues.cycle && <small className="warning">{t("prerequisiteCycle")}</small>}
    {issues.review && <small className="warning">{t("prerequisiteReview")}</small>}
  </span>;
}
