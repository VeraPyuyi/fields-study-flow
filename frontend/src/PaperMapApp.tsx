import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, ControlButton, Controls, ReactFlow, ReactFlowProvider, useNodesState, useReactFlow } from "@xyflow/react";
import { Maximize, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import type { Roadmap } from "./types";
import { WorkbenchProvider, useWorkbench } from "./workbench/WorkbenchProvider";
import { WorkbenchLayout, IconButton, useNarrowViewport } from "./workbench/WorkbenchLayout";
import { PaperNode } from "./workbench/PaperNode";
import { branchOwners, createMapNodes, projectMap, reconcileMapNodes, setBranchExpanded, type FlowPaperNode } from "./workbench/mapState";
import { anchorsForNode, claimForNode, graphData, nodeForClaim } from "./workbench/adapter";
import { ContextPanel, DetailBlock } from "./workbench/ContextPanel";
import { Empty } from "./shared";
import { bindParagraph } from "./workbench/paragraphBinding";

const nodeTypes = { paper: PaperNode };
export function PaperMapApp({ roadmap }: { roadmap: Roadmap }) {
  return <WorkbenchProvider roadmap={roadmap}><ReactFlowProvider><PaperMapWorkbench /></ReactFlowProvider></WorkbenchProvider>;
}
function PaperMapWorkbench() {
  const { roadmap, context, study, t, showContext } = useWorkbench();
  const raw = useMemo(() => graphData(roadmap, context), [roadmap, context]);
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowPaperNode>(createMapNodes(raw.nodes, study.state.graph.positions));
  const { fitView, setViewport, zoomIn, zoomOut } = useReactFlow();
  const initialized = useRef(false);
  const mobile = useNarrowViewport("(max-width: 767px)");
  const [selectedId, setSelectedId] = useState(() => {
    const id = readHash();
    return nodeForClaim(raw.nodes, context, id)?.id || study.state.graph.selected || raw.nodes[0]?.id || "";
  });
  const expanded = study.state.graph.expanded;
  useEffect(() => {
    setNodes(previous => reconcileMapNodes(previous, raw.nodes, study.state.graph.positions));
  }, [raw.nodes, setNodes]);
  useEffect(() => {
    if (!study.importRevision) return;
    setNodes(createMapNodes(raw.nodes, study.state.graph.positions));
    setSelectedId(study.state.graph.selected || nodeForClaim(raw.nodes, context, study.state.selection.claimId)?.id || raw.nodes[0]?.id || "");
    if (study.state.graph.viewport) void setViewport(study.state.graph.viewport);
    // Only an explicit import can replace coordinates; branch and viewport changes cannot.
  }, [study.importRevision, setNodes, setViewport]);
  const toggle = useCallback((id: string) => {
    const open = !study.state.graph.expanded.includes(id);
    study.updateGraph({ expanded: setBranchExpanded(study.state.graph.expanded, id, open) });
    if (!open && branchOwners(nodes, raw.edges).get(selectedId)?.includes(id)) {
      setSelectedId(id); const claim = claimForNode(context, raw.nodes.find(n => n.id === id));
      study.select({ claimId: claim?.id, stepId: undefined }); study.updateGraph({ selected: id });
    }
  }, [study.state.graph.expanded, study.updateGraph, study.select, nodes, raw, selectedId, context]);
  const projection = useMemo(() => projectMap(nodes, raw.edges, expanded, selectedId), [nodes, raw.edges, expanded, selectedId]);
  const viewNodes = useMemo(() => projection.nodes.map(n => ({ ...n, data: { ...n.data,
    branchCount: [...projection.owners.values()].filter(owners => owners.includes(n.id)).length, onToggle: toggle } })), [projection, toggle]);
  const selected = raw.nodes.find(n => n.id === selectedId) || raw.nodes[0];
  const claim = claimForNode(context, selected);
  const selectNode = useCallback((id: string, reveal = true) => {
    setSelectedId(id);
    const claim = claimForNode(context, raw.nodes.find(n => n.id === id));
    const step = context.learning_steps.find(s => s.claim_ids.includes(claim?.id || id));
    const segment = claim ? roadmap.paper_lens?.segments?.find(s => bindParagraph(context, s).claim?.id === claim.id) : undefined;
    study.select({ claimId: claim?.id || id, stepId: step?.id, anchorId: claim?.anchor_ids[0], segmentId: segment?.id, taskId: undefined });
    study.updateGraph({ selected: id });
    history.replaceState(null, "", `#${encodeURIComponent(id)}`);
    if (reveal) showContext();
  }, [context, raw.nodes, roadmap.paper_lens?.segments, study.select, study.updateGraph, showContext]);
  useEffect(() => {
    function onHash() { const node = nodeForClaim(raw.nodes, context, readHash()); if (node) selectNode(node.id, false); }
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [raw.nodes, selectNode]);
  useEffect(() => {
    const id = study.state.selection.claimId;
    const node = nodeForClaim(raw.nodes, context, id);
    if (node && node.id !== selectedId) {
      setSelectedId(node.id);
      const owners = projection.owners.get(node.id);
      if (owners) study.updateGraph({ expanded: [...new Set([...expanded, ...owners])] });
    }
  }, [study.state.selection.claimId, raw.nodes, context, selectedId, projection.owners, expanded, study.updateGraph]);
  function reset() {
    const resetNodes = createMapNodes(raw.nodes);
    setNodes(resetNodes);
    study.updateGraph({ positions: {}, viewport: undefined });
    requestAnimationFrame(() => void fitView({ padding: 0.06, minZoom: 0.65, maxZoom: 1, duration: 0 }));
  }
  return <WorkbenchLayout page="paper_map" context={<ContextPanel title={selected?.label} claimId={claim?.id} anchorIds={anchorsForNode(context, selected)} resources={selected?.related_resources}
    evidence={claim?.anchor_ids.length ? [] : selected?.evidence}>
    <DetailBlock title={t("explanation")} text={selected?.plain_explanation || claim?.statement} />
    <DetailBlock title={t("why")} text={selected?.why_it_matters} />
    <DetailBlock title={t("connection")} text={selected?.connection} />
    <DetailBlock title={t("talking")} text={selected?.talking_point} />
  </ContextPanel>}>
    <div className="graph-workspace">
      <div className="surface-toolbar"><h2>{t("graph")}</h2><div className="button-row">
        <IconButton label={t("fit")} onClick={() => void fitView({ padding: 0.06, minZoom: 0.65, maxZoom: 1, duration: 0 })}><Maximize size={17} /></IconButton>
        <IconButton label={t("reset")} onClick={reset}><RotateCcw size={17} /></IconButton>
      </div></div>
      <div className="flow-shell" data-paper-map-canvas>
        {nodes.length ? <ReactFlow nodes={viewNodes} edges={projection.edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
          fitView={!study.state.graph.viewport} defaultViewport={study.state.graph.viewport}
          fitViewOptions={{ padding: 0.06, minZoom: 0.65, maxZoom: 1 }} minZoom={0.65} maxZoom={2}
          onInit={instance => { if (initialized.current) return; initialized.current = true;
            if (study.state.graph.viewport) void instance.setViewport(study.state.graph.viewport); }}
          onNodeClick={(_, node) => selectNode(node.id)} onNodeDragStop={(_, node) => study.updateGraph({ positions: { ...study.state.graph.positions, [node.id]: node.position } })}
          onMoveEnd={(_, viewport) => study.updateGraph({ viewport })} nodesConnectable={false} nodesDraggable={!mobile}
          deleteKeyCode={null} zoomOnDoubleClick={false} proOptions={{ hideAttribution: true }}>
          <Background color="#DDE2E7" gap={22} /><Controls showInteractive={false} showZoom={false} showFitView={false}>
            <ControlButton title={t("zoomIn")} aria-label={t("zoomIn")} onClick={() => void zoomIn()}><ZoomIn size={17} /></ControlButton>
            <ControlButton title={t("zoomOut")} aria-label={t("zoomOut")} onClick={() => void zoomOut()}><ZoomOut size={17} /></ControlButton>
            <ControlButton title={t("fit")} aria-label={t("fit")} onClick={() => void fitView({ padding: 0.06, minZoom: 0.65, maxZoom: 1 })}><Maximize size={17} /></ControlButton>
          </Controls>
        </ReactFlow> : <Empty>{t("noNodes")}</Empty>}
      </div>
      {mobile && <nav className="mobile-node-list" aria-label={t("nodeList")}>{projection.nodes.filter(n => !n.hidden).map(n => <button type="button" key={n.id} aria-pressed={n.id === selectedId} onClick={() => selectNode(n.id)}>{n.data.raw.label || n.id}</button>)}</nav>}
    </div>
  </WorkbenchLayout>;
}
export function readHash() { try { return decodeURIComponent(location.hash.slice(1)); } catch { return ""; } }
