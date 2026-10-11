import { memo, useEffect } from "react";
import { Handle, Position, useUpdateNodeInternals, type NodeProps } from "@xyflow/react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { compactCoreLabel, type FlowPaperNode } from "./mapState";
import { useWorkbench } from "./WorkbenchProvider";
import { claimForNode } from "./adapter";
import { domainLabel } from "./domainLabels";

export const PaperNode = memo(function PaperNode({ id, data, selected }: NodeProps<FlowPaperNode>) {
  const { context, study, t, language } = useWorkbench();
  const updateInternals = useUpdateNodeInternals();
  useEffect(() => {
    const frame = requestAnimationFrame(() => updateInternals(id));
    return () => cancelAnimationFrame(frame);
  }, [id, data.raw.label, language, updateInternals]);
  const claim = claimForNode(context, data.raw);
  const expanded = study.state.graph.expanded.includes(id);
  const branchCount = Number(data.branchCount || 0);
  const evidenceStatus = claim?.evidence_status || data.raw.evidence_status;
  const status = evidenceStatus === "located" ? "located" : evidenceStatus === "partial" ? "partial" : evidenceStatus === "stale" ? "source_stale" : "missing";
  return <div className={`map-node map-node-${data.raw.kind || "claim"} ${selected ? "selected" : ""}`}>
    {([['left', Position.Left], ['right', Position.Right], ['top', Position.Top], ['bottom', Position.Bottom]] as const).map(([side, position]) => <span key={side}>
      <Handle id={`in-${side}`} type="target" position={position} />
      <Handle id={`out-${side}`} type="source" position={position} />
    </span>)}
    <div className="node-kind">{domainLabel(data.raw.kind || "claim", language)}</div>
    <div className="node-title" title={data.raw.label}>{compactCoreLabel(data.raw) ? domainLabel(data.raw.kind || "claim", language) : data.raw.label || t("claim")}</div>
    <div className="node-footer"><span className={`node-status status-${status}`} title={t(status)}>{t(status)}</span>
      {!!branchCount && <button type="button" className="icon-button nodrag nopan" title={t(expanded ? "collapse" : "expand")} aria-label={`${t(expanded ? "collapse" : "expand")} ${data.raw.label || id}`} aria-expanded={expanded}
        onClick={e => { e.stopPropagation(); const toggle = data.onToggle as ((id: string) => void) | undefined; toggle?.(id); }}>{expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>}
    </div>
  </div>;
});
