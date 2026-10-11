import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type { PaperMapEdge, PaperMapNode } from "../types";

const coreKinds = new Set(["target", "background", "motivation", "problem", "method", "methodology", "experiment", "result", "contribution", "limitation", "claim"]);
export function isPrimaryNode(node: PaperMapNode) { return node.role === "target" || node.role === "core" || coreKinds.has(node.kind || "claim"); }
export function compactCoreLabel(node: PaperMapNode) {
  return node.role === "core" && Array.from(node.label || "").reduce((n, c) => n + (c.charCodeAt(0) > 255 ? 2 : 1), 0) > 44;
}
export type PaperNodeData = { raw: PaperMapNode; primary: boolean; [key: string]: unknown };
export type FlowPaperNode = Node<PaperNodeData>;

export function createMapNodes(raw: PaperMapNode[], positions: Record<string, { x: number; y: number }> = {}): FlowPaperNode[] {
  let coreIndex = 0;
  let branchIndex = 0;
  function rowOffsets(items: PaperMapNode[], columns: number) {
    const heights: number[] = [];
    items.forEach((node, i) => {
      const units = compactCoreLabel(node) ? 18 : Array.from(node.label || "").reduce((n, char) => n + (char.charCodeAt(0) > 255 ? 2 : 1), 0);
      const height = 92 + Math.max(1, Math.ceil(units / 18)) * 28;
      const row = Math.floor(i / columns);
      heights[row] = Math.max(heights[row] || 0, height);
    });
    return heights.map((_, row) => heights.slice(0, row).reduce((sum, h) => sum + h + 46, 0));
  }
  const coreRows = rowOffsets(raw.filter(isPrimaryNode), 3);
  const branchRows = rowOffsets(raw.filter(n => !isPrimaryNode(n)), 2);
  return raw.map(node => {
    const primary = isPrimaryNode(node);
    const index = primary ? coreIndex++ : branchIndex++;
    const nextRow = Math.floor(index / 3);
    const column = nextRow % 2 ? 2 - index % 3 : index % 3;
    return { id: node.id, type: "paper", position: positions[node.id] || {
      x: primary ? column * 240 : 790 + index % 2 * 240,
      y: primary ? coreRows[nextRow] : branchRows[Math.floor(index / 2)],
    }, data: { raw: node, primary }, style: { width: 210 }, selected: false };
  });
}

export function reconcileMapNodes(previous: FlowPaperNode[], raw: PaperMapNode[], positions: Record<string, { x: number; y: number }> = {}): FlowPaperNode[] {
  const existing = new Map(previous.map(node => [node.id, node]));
  return createMapNodes(raw, positions).map(next => {
    const old = existing.get(next.id);
    return old ? { ...old, data: { ...old.data, ...next.data } } : next;
  });
}

export function branchOwners(nodes: FlowPaperNode[], edges: PaperMapEdge[]): Map<string, string[]> {
  const primary = new Set(nodes.filter(n => n.data.primary).map(n => n.id));
  const owners = new Map<string, string[]>();
  for (const parent of primary) {
    const queue = edges.filter(e => e.from === parent && !primary.has(e.to)).map(e => e.to);
    const visited = new Set<string>();
    while (queue.length) {
      const id = queue.shift()!;
      if (visited.has(id) || primary.has(id)) continue;
      visited.add(id);
      owners.set(id, [...(owners.get(id) || []), parent]);
      edges.filter(e => e.from === id && !primary.has(e.to)).forEach(e => queue.push(e.to));
    }
  }
  // Older maps occasionally orient resource edges toward their parent.
  edges.forEach(e => { if (primary.has(e.to) && !primary.has(e.from) && !owners.has(e.from)) owners.set(e.from, [e.to]); });
  return owners;
}
export function setBranchExpanded(expanded: string[], parent: string, open: boolean): string[] {
  return open ? [...new Set([...expanded, parent])] : expanded.filter(id => id !== parent);
}
export function projectMap(nodes: FlowPaperNode[], rawEdges: PaperMapEdge[], expanded: string[], selected: string) {
  const owners = branchOwners(nodes, rawEdges);
  const neighborhood = new Set([selected]);
  rawEdges.forEach(e => { if (e.from === selected) neighborhood.add(e.to); if (e.to === selected) neighborhood.add(e.from); });
  const hidden = new Set(nodes.filter(n => !n.data.primary && !(owners.get(n.id) || []).some(id => expanded.includes(id))).map(n => n.id));
  const ids = new Set(nodes.map(n => n.id));
  const positions = new Map(nodes.map(n => [n.id, n.position]));
  const edges: Edge[] = rawEdges.filter(e => ids.has(e.from) && ids.has(e.to)).map((e, i) => {
    const from = positions.get(e.from)!;
    const to = positions.get(e.to)!;
    const vertical = Math.abs(to.x - from.x) < 100 && Math.abs(to.y - from.y) > 120;
    const sourceSide = vertical ? to.y > from.y ? 'bottom' : 'top' : to.x > from.x ? 'right' : 'left';
    const targetSide = vertical ? to.y > from.y ? 'top' : 'bottom' : to.x > from.x ? 'left' : 'right';
    return {
    id: e.id || `${e.from}-${e.to}-${i}`, source: e.from, target: e.to, hidden: hidden.has(e.from) || hidden.has(e.to),
    sourceHandle: `out-${sourceSide}`, targetHandle: `in-${targetSide}`, type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed }, animated: false,
    className: e.from === selected || e.to === selected ? "edge-focused" : "",
    style: { stroke: e.from === selected || e.to === selected ? "#187C78" : "#B8C1CB", strokeWidth: e.from === selected || e.to === selected ? 2 : 1.2 },
  }; });
  return { nodes: nodes.map(n => ({ ...n, hidden: hidden.has(n.id), selected: n.id === selected,
    className: neighborhood.has(n.id) ? "node-neighbor" : "" })), edges, owners };
}
