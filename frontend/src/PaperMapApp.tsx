import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  type Edge,
  type Node,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { Empty, Header, ResourceButton } from "./shared";
import type { PaperMapEdge, PaperMapNode, Roadmap } from "./types";
import { compactTitle } from "./data";

const CORE_KINDS = new Set(["background", "motivation", "problem", "methodology", "experiment", "result", "contribution", "limitation"]);
const PRESENTATION_STEPS = [
  { kind: "background", label: "背景" },
  { kind: "motivation", label: "动机/缺口" },
  { kind: "problem", label: "问题" },
  { kind: "methodology", label: "方法" },
  { kind: "experiment", label: "实验" },
  { kind: "result", label: "结果" },
  { kind: "contribution", label: "贡献" },
  { kind: "limitation", label: "局限" },
];

function isPrimaryNode(node: PaperMapNode) {
  return node.role === "target" || node.role === "core" || node.kind === "target" || CORE_KINDS.has(String(node.kind || ""));
}

function visibleMapNodes(nodes: PaperMapNode[], showBranches: boolean) {
  return showBranches ? nodes : nodes.filter(isPrimaryNode);
}

function visibleMapEdges(edges: PaperMapEdge[] | undefined, visibleIds: Set<string>) {
  const sourceEdges = Array.isArray(edges) ? edges : [];
  return sourceEdges.filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to));
}

function evidenceCount(node?: PaperMapNode) {
  return Array.isArray(node?.evidence) ? node.evidence.length : 0;
}

function evidenceCoverageLabel(node?: PaperMapNode) {
  const count = evidenceCount(node);
  return count ? `证据覆盖：已绑定 ${count} 条` : "证据覆盖：待复核";
}

function evidenceCoverageNote(node?: PaperMapNode) {
  const count = evidenceCount(node);
  return count ? "原文证据已绑定，可直接点节点复核。" : "这个节点还没有直接证据，汇报前建议回到论文精读页或原文确认。";
}

function toFlowNodes(nodes: PaperMapNode[]): Node[] {
  return nodes.map((node, index) => ({
    id: node.id,
    type: "default",
    style: {
      width: Math.max(270, Number(node.layout?.width ?? 270)),
      padding: 0,
      border: 0,
      background: "transparent",
      boxShadow: "none",
    },
    position: {
      x: Number(node.layout?.x ?? (index % 6) * 260),
      y: Number(node.layout?.y ?? Math.floor(index / 6) * 180),
    },
    data: {
      label: (
        <div className={`map-node map-node-${node.role || node.kind || "node"}`}>
          <span title={node.kind_label || node.kind || "节点"}>{node.kind_label || node.kind || "节点"}</span>
          <strong title={node.label}>{compactTitle(node.label, 54)}</strong>
          <p title={node.plain_explanation}>{compactTitle(node.plain_explanation, 92)}</p>
          <small className={evidenceCount(node) ? "evidence-covered" : "evidence-missing"}>{evidenceCoverageLabel(node)}</small>
        </div>
      ),
    },
  }));
}

function toFlowEdges(edges: PaperMapEdge[] | undefined): Edge[] {
  const sourceEdges = Array.isArray(edges) ? edges : [];
  return sourceEdges.map((edge, index) => ({
    id: edge.id || `edge-${index}`,
    source: edge.from,
    target: edge.to,
    label: edge.localized_label || edge.label,
    markerEnd: { type: MarkerType.ArrowClosed },
    animated: edge.label === "supports",
  }));
}

const COMPACT_VIEWPORT_QUERY = "(max-width: 720px)";

function getCompactViewportMatch() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(COMPACT_VIEWPORT_QUERY).matches;
}

function useCompactViewport() {
  const [isCompact, setIsCompact] = useState(() => getCompactViewportMatch());

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(COMPACT_VIEWPORT_QUERY);
    const update = () => setIsCompact(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return isCompact;
}

export function PaperMapApp({ roadmap }: { roadmap: Roadmap }) {
  const paperMap = roadmap.paper_map ?? {};
  const rawNodes = paperMap.nodes ?? [];
  const rawEdges = paperMap.edges ?? [];
  const branchCount = rawNodes.filter((node) => !isPrimaryNode(node)).length;
  const [showBranches, setShowBranches] = useState(false);
  const visibleRawNodes = useMemo(() => visibleMapNodes(rawNodes, showBranches), [rawNodes, showBranches]);
  const visibleIds = useMemo(() => new Set(visibleRawNodes.map((node) => node.id)), [visibleRawNodes]);
  const visibleRawEdges = useMemo(() => visibleMapEdges(rawEdges, visibleIds), [rawEdges, visibleIds]);
  const [selectedId, setSelectedId] = useState(visibleRawNodes[0]?.id || rawNodes[0]?.id || "");
  const selected = rawNodes.find((node) => node.id === selectedId) || visibleRawNodes[0] || rawNodes[0];
  const initialNodes = useMemo(() => toFlowNodes(visibleRawNodes), [visibleRawNodes]);
  const initialEdges = useMemo(() => toFlowEdges(visibleRawEdges), [visibleRawEdges]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [isDragging, setIsDragging] = useState(false);
  const [isMoving, setIsMoving] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const compactViewport = useCompactViewport();
  const focusedMinZoom = compactViewport ? 0.72 : 0.58;
  const mapMinZoom = showBranches ? (compactViewport ? 0.38 : 0.3) : focusedMinZoom;
  const mapFitPadding = showBranches ? (compactViewport ? 0.08 : 0.16) : compactViewport ? 0.01 : 0.04;
  const presentationSteps = useMemo(() => buildPresentationSteps(rawNodes), [rawNodes]);
  const presentationText = useMemo(
    () => buildPresentationText(presentationSteps, paperMap.target?.title || roadmap.title || "论文"),
    [paperMap.target?.title, presentationSteps, roadmap.title],
  );
  const densityDescription = showBranches
    ? "显示资料、证据、公式和验收任务，用来做复查、实现和汇报准备。"
    : "默认只显示目标论文和核心因果链，先让用户在 3 分钟内看懂论文为什么这样做。";

  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges);
  }, [initialEdges, setEdges]);

  useEffect(() => {
    if (!selectedId || visibleIds.has(selectedId)) return;
    setSelectedId(visibleRawNodes[0]?.id || rawNodes[0]?.id || "");
  }, [rawNodes, selectedId, visibleIds, visibleRawNodes]);

  async function copyPresentationText() {
    if (!presentationText.trim()) return;
    try {
      if (!navigator.clipboard?.writeText) {
        setCopyState("failed");
        return;
      }
      await navigator.clipboard.writeText(presentationText);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  function downloadPresentationMarkdown() {
    if (!presentationText.trim()) return;
    try {
      const blob = new Blob([`${presentationText}\n`], { type: "text/markdown;charset=utf-8" });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = "paper_map_presentation.md";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <main className={`map-app ${isDragging ? "is-node-dragging" : ""} ${isMoving ? "is-canvas-moving" : ""}`}>
      <Header
        roadmap={roadmap}
        eyebrow="XMind 式论文逻辑图"
        title={paperMap.target?.title || roadmap.title || "论文逻辑图"}
        actions={
          <>
            <a className="primary-action" href="paper_lens.html">进入段落精读</a>
            <a className="pill-link" href="roadmap.html">返回学习路线</a>
          </>
        }
      />
      <section className="map-onboarding" aria-label="论文逻辑图读图方法">
        <article>
          <span>1</span>
          <div>
            <strong>先看主链</strong>
            <p>按背景、动机、问题、方法、实验、贡献、局限的顺序，先抓住论文为什么这样做。</p>
          </div>
        </article>
        <article>
          <span>2</span>
          <div>
            <strong>再点节点</strong>
            <p>点击任一节点，右侧会显示直白解释、前后关系、原文证据和可直接用于汇报的话术。</p>
          </div>
        </article>
        <article>
          <span>3</span>
          <div>
            <strong>最后展开资料</strong>
            <p>需要补背景、代码或验收任务时，再展开资料/任务分支，避免一开始被信息淹没。</p>
          </div>
        </article>
      </section>
      <details className="map-script-panel" data-presentation-script>
        <summary>
          <span>3 分钟汇报稿</span>
          <strong>按这条线讲：背景 → 动机 → 问题 → 方法 → 实验 → 贡献 → 局限</strong>
        </summary>
        <div className="map-script-actions">
          <button type="button" onClick={copyPresentationText} disabled={!presentationSteps.length}>
            复制汇报稿
          </button>
          <button type="button" onClick={downloadPresentationMarkdown} disabled={!presentationSteps.length}>
            下载汇报稿.md
          </button>
          <span aria-live="polite">
            {copyState === "copied" ? "已复制，可直接粘贴到 PPT 备注或文档。" : null}
            {copyState === "failed" ? "当前浏览器不允许自动复制，可手动选中下方讲稿。" : null}
            {copyState === "idle" ? "展开后可复制整段汇报稿。" : null}
          </span>
        </div>
        <div className="map-script-list">
          {presentationSteps.length ? (
            presentationSteps.map((step) => (
              <article key={step.kind}>
                <span>{step.label}</span>
                <p>{step.text}</p>
              </article>
            ))
          ) : (
            <Empty>当前论文逻辑图还没有足够节点生成汇报稿。可以先看主链节点和右侧汇报话术。</Empty>
          )}
        </div>
      </details>
      <section className="map-workspace">
        <div className="flow-shell" data-paper-map-canvas>
          <ReactFlow
            key={`${compactViewport ? "compact" : "wide"}-${showBranches ? "expanded" : "focus"}`}
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: mapFitPadding }}
            minZoom={mapMinZoom}
            maxZoom={1.8}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeDragStart={() => setIsDragging(true)}
            onNodeDragStop={() => setIsDragging(false)}
            onMoveStart={() => setIsMoving(true)}
            onMoveEnd={() => setIsMoving(false)}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable
          >
            <Background />
            <MiniMap pannable zoomable className="whiteboard-minimap" />
            <Controls showInteractive={false} />
            <Panel position="top-left" className="whiteboard-toolbar">
              <div className="density-control" data-paper-map-density>
                <span className="toolbar-label">阅读密度</span>
                <button
                  type="button"
                  className={`toolbar-button ${showBranches ? "" : "active"}`}
                  aria-pressed={!showBranches}
                  onClick={() => setShowBranches(false)}
                >
                  速览主链
                </button>
                <button
                  type="button"
                  className={`toolbar-button ${showBranches ? "active" : ""}`}
                  aria-pressed={showBranches}
                  data-paper-map-branch-toggle
                  disabled={!branchCount}
                  onClick={() => setShowBranches(true)}
                >
                  {branchCount ? `完整探索 (${branchCount})` : "完整探索"}
                </button>
                <small>{densityDescription}</small>
              </div>
              <div className="toolbar-hints">
                <span>拖拽节点</span>
                <span>滚轮缩放</span>
                <span>空白处平移</span>
              </div>
            </Panel>
          </ReactFlow>
        </div>
        <aside className="detail-rail">
          <p className="eyebrow">当前节点</p>
          <h2>{selected?.label || "选择一个节点"}</h2>
          <DetailBlock title="这部分讲什么" text={selected?.plain_explanation} />
          <DetailBlock title="为什么重要" text={selected?.why_it_matters} />
          <DetailBlock title="和前后节点怎么连" text={selected?.connection} />
          <DetailBlock title="汇报话术" text={selected?.talking_point} />
          <section className="detail-section evidence-coverage-card">
            <h3>{evidenceCoverageLabel(selected)}</h3>
            <p>{evidenceCoverageNote(selected)}</p>
          </section>
          <section className="detail-section">
            <h3>原文证据</h3>
            {(selected?.evidence ?? []).length ? (
              (selected?.evidence ?? []).slice(0, 3).map((item, index) => (
                <blockquote key={index}>
                  <strong>{item.source_title || item.resource_title || item.file_name || "证据"}</strong>
                  <p>{item.snippet || item.note || "证据不足，需要回到原文复核。"}</p>
                </blockquote>
              ))
            ) : (
              <Empty>当前节点还没有直接证据，建议回到原文或精读页复核。</Empty>
            )}
          </section>
          <details className="detail-section collapsible-section">
            <summary>推荐资料（按需展开）</summary>
            <div className="button-row">
              {(selected?.related_resources ?? []).length ? (
                (selected?.related_resources ?? []).map((resource, index) => (
                  <ResourceButton key={index} item={resource} label={resource.local_href ? "打开本地资料" : resource.label || "打开资料"} />
                ))
              ) : (
                <Empty>这个节点暂无单独资料；先看原文证据和论文精读页。</Empty>
              )}
            </div>
          </details>
        </aside>
      </section>
    </main>
  );
}

function buildPresentationSteps(nodes: PaperMapNode[]) {
  return PRESENTATION_STEPS.flatMap((step) => {
    const node = nodes.find((item) => String(item.kind || "") === step.kind && isPrimaryNode(item));
    if (!node) return [];
    const text = node.talking_point || node.plain_explanation || node.why_it_matters || node.label;
    if (!text) return [];
    return [{ kind: step.kind, label: step.label, text }];
  });
}

function buildPresentationText(steps: Array<{ label: string; text: string }>, title: string) {
  if (!steps.length) return "";
  return [`《${title}》3 分钟汇报稿`, ...steps.map((step, index) => `${index + 1}. ${step.label}：${step.text}`)].join("\n");
}

function DetailBlock({ title, text }: { title: string; text?: string }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      <p>{text || "暂无内容。"}</p>
    </section>
  );
}
