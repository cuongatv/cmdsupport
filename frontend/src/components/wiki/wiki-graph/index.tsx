"use client";

import React from "react";
import { useRouter } from "next/navigation";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  forceX,
  forceY,
} from "d3-force";
import { wikiTypeColor, wikiTypeGroupLabel, wikiTypeIcon } from "../wiki-type-badge";
import { GraphNode, GraphLink, NodeInput } from "./types";
import { convexHull, hullToPath, scopeColor, nodeRadius } from "./utils";

type Props = {
  nodes: NodeInput[];
  edges: { from: string; to: string }[];
  centerSlug?: string;
  mini?: boolean;
  height?: number;
  onNodeClick?: (slug: string) => void;
};

const EDGE_COLOR = "rgba(95,118,118,0.35)";
const EDGE_HIGHLIGHT = "#006B68";
const LABEL_COLOR = "#0F2A2A";

export function WikiGraph({
  nodes: rawNodes,
  edges: rawEdges,
  centerSlug,
  mini = false,
  height,
  onNodeClick,
}: Props) {
  const router = useRouter();
  const svgRef = React.useRef<SVGSVGElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = React.useState({ w: 800, h: height ?? 400 });
  const [simNodes, setSimNodes] = React.useState<GraphNode[]>([]);
  const [simLinks, setSimLinks] = React.useState<GraphLink[]>([]);
  const [hoveredSlug, setHoveredSlug] = React.useState<string | null>(null);
  const [tooltip, setTooltip] = React.useState<{
    x: number;
    y: number;
    title: string;
    type: string;
    degree: number;
    scopeType?: string;
    scopeName?: string | null;
  } | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const simulationRef = React.useRef<any>(null);

  // Zoom & pan state
  const [zoom, setZoom] = React.useState(1);
  const [pan, setPan] = React.useState({ x: 0, y: 0 });
  const [settled, setSettled] = React.useState(false);
  const isPanningRef = React.useRef(false);
  const panStartRef = React.useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // Measure container
  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const { width, height: h } = entries[0].contentRect;
      setDimensions({ w: width, h: height ?? h });
    });
    obs.observe(el);
    setDimensions({ w: el.clientWidth, h: height ?? el.clientHeight });
    return () => obs.disconnect();
  }, [height]);

  // Persistent refs for simulation nodes/links (used in progressive/incremental mode)
  const nodesRef = React.useRef<GraphNode[]>([]);
  const linksRef = React.useRef<GraphLink[]>([]);
  const knownSlugsRef = React.useRef<Set<string>>(new Set());
  const prevRawNodesLenRef = React.useRef(0);

  // Build / update simulation
  React.useEffect(() => {
    if (rawNodes.length === 0) return;

    const degreeMap = new Map<string, number>();
    for (const e of rawEdges) {
      degreeMap.set(e.from, (degreeMap.get(e.from) ?? 0) + 1);
      degreeMap.set(e.to, (degreeMap.get(e.to) ?? 0) + 1);
    }

    // Detect if this is a full data reset (new page / mini mode) vs incremental batch
    const isFullReset = mini || rawNodes.length <= prevRawNodesLenRef.current;
    if (isFullReset) {
      // Full rebuild — clear refs
      nodesRef.current = [];
      linksRef.current = [];
      knownSlugsRef.current.clear();
    }
    prevRawNodesLenRef.current = rawNodes.length;

    // Identify new nodes not already in the simulation
    const newInputs = rawNodes.filter((n) => !knownSlugsRef.current.has(n.slug));
    if (newInputs.length === 0 && simulationRef.current) {
      // Only dimension change — update forceX/Y targets and reheat slightly
      const fx = simulationRef.current.force("x") as ReturnType<typeof forceX> | undefined;
      const fy = simulationRef.current.force("y") as ReturnType<typeof forceY> | undefined;
      if (fx) fx.x(dimensions.w / 2);
      if (fy) fy.y(dimensions.h / 2);
      simulationRef.current.alpha(0.1).restart();
      return;
    }

    // Compute centroid of existing nodes (fallback to center)
    const existing = nodesRef.current.filter((n) => n.x !== undefined);
    const cx = existing.length > 0
      ? existing.reduce((s, n) => s + n.x!, 0) / existing.length
      : dimensions.w / 2;
    const cy = existing.length > 0
      ? existing.reduce((s, n) => s + n.y!, 0) / existing.length
      : dimensions.h / 2;

    // Create new GraphNode objects, positioned near neighbors or centroid
    const nodeBySlug = new Map(nodesRef.current.map((n) => [n.slug, n]));
    for (const n of newInputs) {
      let spawnX = cx + (Math.random() - 0.5) * 60;
      let spawnY = cy + (Math.random() - 0.5) * 60;

      // Find a connected neighbor that already exists to spawn near it
      for (const e of rawEdges) {
        if (e.from === n.slug && nodeBySlug.has(e.to)) {
          const neighbor = nodeBySlug.get(e.to)!;
          if (neighbor.x !== undefined) {
            spawnX = neighbor.x + (Math.random() - 0.5) * 40;
            spawnY = neighbor.y! + (Math.random() - 0.5) * 40;
            break;
          }
        }
        if (e.to === n.slug && nodeBySlug.has(e.from)) {
          const neighbor = nodeBySlug.get(e.from)!;
          if (neighbor.x !== undefined) {
            spawnX = neighbor.x + (Math.random() - 0.5) * 40;
            spawnY = neighbor.y! + (Math.random() - 0.5) * 40;
            break;
          }
        }
      }

      const node: GraphNode = {
        slug: n.slug,
        title: n.title,
        page_type: n.page_type,
        scope_type: n.scope_type,
        scope_name: n.scope_name,
        degree: degreeMap.get(n.slug) ?? 0,
        x: spawnX,
        y: spawnY,
        fx: n.slug === centerSlug ? dimensions.w / 2 : undefined,
        fy: n.slug === centerSlug ? dimensions.h / 2 : undefined,
      };
      nodesRef.current.push(node);
      nodeBySlug.set(n.slug, node);
      knownSlugsRef.current.add(n.slug);
    }

    // Update degree for all
    for (const n of nodesRef.current) {
      n.degree = degreeMap.get(n.slug) ?? 0;
    }

    // Rebuild links from ALL edges, only where both endpoints exist
    linksRef.current = rawEdges
      .map((e) => ({ ...e, source: nodeBySlug.get(e.from)!, target: nodeBySlug.get(e.to)! }))
      .filter((l) => l.source && l.target);

    const nodes = nodesRef.current;
    const links = linksRef.current;

    // --- Detect connected components via BFS to separate clusters ---
    const slugToComponent = new Map<string, number>();
    let componentId = 0;
    const adjacency = new Map<string, Set<string>>();
    for (const n of nodes) adjacency.set(n.slug, new Set());
    for (const l of links) {
      const s = typeof l.source === "string" ? l.source : (l.source as GraphNode).slug;
      const t = typeof l.target === "string" ? l.target : (l.target as GraphNode).slug;
      adjacency.get(s)?.add(t);
      adjacency.get(t)?.add(s);
    }
    for (const n of nodes) {
      if (slugToComponent.has(n.slug)) continue;
      const queue = [n.slug];
      while (queue.length > 0) {
        const cur = queue.pop()!;
        if (slugToComponent.has(cur)) continue;
        slugToComponent.set(cur, componentId);
        for (const neighbor of adjacency.get(cur) ?? []) {
          if (!slugToComponent.has(neighbor)) queue.push(neighbor);
        }
      }
      componentId++;
    }

    // Compute per-component target X positions (spread across canvas)
    const numComponents = componentId;
    const componentTargetX = new Map<number, number>();
    for (let i = 0; i < numComponents; i++) {
      const margin = dimensions.w * 0.15;
      componentTargetX.set(
        i,
        numComponents <= 1
          ? dimensions.w / 2
          : margin + ((dimensions.w - 2 * margin) * i) / (numComponents - 1)
      );
    }
    // Assign per-node target
    for (const n of nodes) {
      (n as GraphNode & { _targetX?: number })._targetX = componentTargetX.get(slugToComponent.get(n.slug) ?? 0) ?? dimensions.w / 2;
    }

    // Stop previous simulation if any
    if (simulationRef.current) {
      simulationRef.current.stop();
    }

    const sim = forceSimulation<GraphNode>(nodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id((d) => (d as GraphNode).slug)
          .distance(mini ? 40 : 80)
          .strength(0.4)
      )
      .force("charge", forceManyBody().strength(mini ? -60 : -250))
      // Per-cluster X target so disconnected clusters separate
      .force("x", forceX<GraphNode>((d: GraphNode & { _targetX?: number }) => d._targetX ?? dimensions.w / 2).strength(0.05))
      .force("y", forceY<GraphNode>(dimensions.h / 2).strength(0.03))
      .force("collide", forceCollide<GraphNode>((d) => nodeRadius(d.degree ?? 0, mini) + 6))
      .alphaDecay(0.05)
      .alphaMin(0.008)
      .velocityDecay(0.5)
      .alpha(isFullReset ? 1 : 0.3);

    sim.on("tick", () => {
      setSimNodes([...nodes]);
      setSimLinks([...links]);
    });

    sim.on("end", () => {
      setSettled(true);
    });

    // Reset settled state on full reset
    if (isFullReset) setSettled(false);

    simulationRef.current = sim;
  }, [rawNodes, rawEdges, centerSlug, dimensions.w, dimensions.h, mini]);

  // Cleanup on unmount
  React.useEffect(() => {
    return () => {
      simulationRef.current?.stop();
      nodesRef.current = [];
      linksRef.current = [];
      knownSlugsRef.current.clear();
    };
  }, []);

  // Neighbors of hovered node
  const neighborSlugs = React.useMemo(() => {
    if (!hoveredSlug) return null;
    const set = new Set<string>([hoveredSlug]);
    for (const l of simLinks) {
      const src = typeof l.source === "object" ? (l.source as GraphNode).slug : String(l.source);
      const tgt = typeof l.target === "object" ? (l.target as GraphNode).slug : String(l.target);
      if (src === hoveredSlug) set.add(tgt);
      if (tgt === hoveredSlug) set.add(src);
    }
    return set;
  }, [hoveredSlug, simLinks]);

  // Type counts for legend
  const typeCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    for (const n of rawNodes) {
      counts[n.page_type] = (counts[n.page_type] ?? 0) + 1;
    }
    return counts;
  }, [rawNodes]);

  // Workspace scope hulls
  const scopeHulls = React.useMemo(() => {
    if (mini) return [];
    const groups: Record<string, { nodes: GraphNode[]; scopeName: string }> = {};
    for (const n of simNodes) {
      if (n.scope_type !== "project" || n.x === undefined || n.y === undefined) continue;
      const key = n.scope_name || "Workspace";
      if (!groups[key]) groups[key] = { nodes: [], scopeName: key };
      groups[key].nodes.push(n);
    }
    return Object.entries(groups)
      .filter(([, g]) => g.nodes.length >= 1)
      .map(([key, g], idx) => {
        const points: [number, number][] = g.nodes.map((n) => [n.x!, n.y!]);
        const hull = convexHull(points);
        const padding = 30;
        const path = hullToPath(hull, padding);
        const cx = points.reduce((s, p) => s + p[0], 0) / points.length;
        // Find topmost point for label
        const topY = Math.min(...points.map((p) => p[1])) - padding - 6;
        return { key, path, cx, labelY: topY, color: scopeColor(idx), scopeName: g.scopeName };
      });
  }, [simNodes, mini]);

  // Scope counts for legend
  const scopeCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    for (const n of rawNodes) {
      const label = n.scope_type === "project" ? (n.scope_name || "Không gian nghiệp vụ") : "Toàn hệ thống";
      counts[label] = (counts[label] ?? 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [rawNodes]);

  const handleNodeClick = (slug: string) => {
    if (onNodeClick) {
      onNodeClick(slug);
    } else {
      router.push(`/admin/wiki/${slug}`);
    }
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full overflow-hidden ${mini ? "rounded-xl border border-border" : ""}`}
      style={{ height: height ?? "100%", background: "var(--color-background, #FDFFFF)" }}
    >
      <svg
        ref={svgRef}
        width={dimensions.w}
        height={dimensions.h}
        style={{ display: "block", cursor: isPanningRef.current ? "grabbing" : "grab" }}
        onWheel={(e) => {
          if (mini) return;
          e.preventDefault();
          const rect = svgRef.current?.getBoundingClientRect();
          if (!rect) return;
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          const factor = e.deltaY > 0 ? 0.9 : 1.1;
          const newZoom = Math.max(0.2, Math.min(5, zoom * factor));
          // Zoom toward cursor
          setPan((prev) => ({
            x: mx - (mx - prev.x) * (newZoom / zoom),
            y: my - (my - prev.y) * (newZoom / zoom),
          }));
          setZoom(newZoom);
        }}
        onMouseDown={(e) => {
          if (mini || e.button !== 0) return;
          isPanningRef.current = true;
          panStartRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
        }}
        onMouseMove={(e) => {
          if (!isPanningRef.current) return;
          setPan({
            x: panStartRef.current.panX + (e.clientX - panStartRef.current.x),
            y: panStartRef.current.panY + (e.clientY - panStartRef.current.y),
          });
        }}
        onMouseUp={() => { isPanningRef.current = false; }}
        onMouseLeave={() => { isPanningRef.current = false; }}
      >
        <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
        {/* Scope hull blobs — fade in after nodes settle */}
        {!mini && settled && scopeHulls.map((hull) => (
          <g key={`hull-${hull.key}`}>
            <path
              d={hull.path}
              fill={`${hull.color}0a`}
              stroke={hull.color}
              strokeWidth={1}
              strokeDasharray="6,4"
              opacity={0.6}
              style={{ transition: "d 300ms ease, opacity 600ms ease" }}
            />
            <text
              x={hull.cx}
              y={hull.labelY}
              textAnchor="middle"
              fill={hull.color}
              fontSize={10}
              fontWeight={600}
              opacity={0.7}
              style={{ pointerEvents: "none", userSelect: "none", transition: "opacity 600ms ease" }}
            >
              {hull.scopeName}
            </text>
          </g>
        ))}

        {/* Edges */}
        <g>
          {simLinks.map((link, i) => {
            const src = link.source as GraphNode;
            const tgt = link.target as GraphNode;
            if (!src?.x || !tgt?.x) return null;

            const isHighlighted =
              hoveredSlug &&
              (src.slug === hoveredSlug || tgt.slug === hoveredSlug);

            return (
              <line
                key={i}
                x1={src.x}
                y1={src.y}
                x2={tgt.x}
                y2={tgt.y}
                stroke={isHighlighted ? EDGE_HIGHLIGHT : EDGE_COLOR}
                strokeWidth={isHighlighted ? 2.5 : 1.2}
                opacity={hoveredSlug ? (isHighlighted ? 0.9 : 0.1) : 0.5}
                style={{ transition: "opacity 200ms ease, stroke-width 200ms ease" }}
              />
            );
          })}
        </g>

        {/* Nodes */}
        <g>
          {simNodes.map((node) => {
            if (node.x === undefined || node.y === undefined) return null;
            const r = nodeRadius(node.degree ?? 0, mini);
            const color = wikiTypeColor(node.page_type);
            const isDimmed = hoveredSlug && !neighborSlugs?.has(node.slug);
            const isHovered = hoveredSlug === node.slug;
            const isCenter = node.slug === centerSlug;

            return (
              <g
                key={node.slug}
                transform={`translate(${node.x},${node.y})`}
                style={{ cursor: "pointer" }}
                onClick={() => handleNodeClick(node.slug)}
                onMouseEnter={(e) => {
                  setHoveredSlug(node.slug);
                  const rect = svgRef.current?.getBoundingClientRect();
                  if (rect) {
                    setTooltip({
                      x: e.clientX - rect.left,
                      y: e.clientY - rect.top - 16,
                      title: node.title,
                      type: node.page_type,
                      degree: node.degree ?? 0,
                      scopeType: node.scope_type,
                      scopeName: node.scope_name,
                    });
                  }
                }}
                onMouseLeave={() => {
                  setHoveredSlug(null);
                  setTooltip(null);
                }}
              >
                {/* Glow ring on hover */}
                {isHovered && (
                  <circle
                    r={r * 1.8}
                    fill={color}
                    opacity={0.12}
                    style={{ transition: "r 200ms ease" }}
                  />
                )}

                {/* Solid background to fully occlude edges behind */}
                <circle
                  r={isHovered ? r * 1.3 + 1 : r + 1}
                  fill="var(--color-background, #FDFFFF)"
                  opacity={isDimmed ? 0 : 1}
                  style={{ transition: "r 200ms ease" }}
                />

                <circle
                  r={isHovered ? r * 1.3 : r}
                  fill={color}
                  opacity={isDimmed ? 0.15 : 1}
                  stroke={isCenter ? "#0F2A2A" : isHovered ? color : "rgba(255,255,255,0.8)"}
                  strokeWidth={isCenter ? 2.5 : isHovered ? 2 : 1}
                  style={{ transition: "r 200ms ease, opacity 200ms ease" }}
                />
                {!mini && !isDimmed && (
                  <text
                    x={r + 5}
                    y={4}
                    fill={LABEL_COLOR}
                    fontSize={isHovered ? 12 : 11}
                    fontWeight={isHovered ? 600 : 400}
                    opacity={isHovered ? 1 : 0.6}
                    style={{
                      pointerEvents: "none",
                      userSelect: "none",
                      transition: "opacity 200ms ease, font-size 200ms ease",
                    }}
                  >
                    {node.title.length > 24
                      ? node.title.slice(0, 22) + "…"
                      : node.title}
                  </text>
                )}
              </g>
            );
          })}
        </g>
        </g>
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="pointer-events-none z-50 px-3 py-2 rounded-lg text-xs shadow-lg"
          style={{
            position: "absolute",
            left: Math.min(tooltip.x + 12, dimensions.w - 200),
            top: Math.max(tooltip.y - 8, 8),
            background: "var(--color-card, #fff)",
            color: "var(--color-foreground, #0F2A2A)",
            border: "1px solid var(--color-border, rgba(15,42,42,0.10))",
            maxWidth: 220,
          }}
        >
          <p className="font-medium text-sm mb-0.5 truncate">{tooltip.title}</p>
          <div className="flex items-center gap-2 text-muted-foreground">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: wikiTypeColor(tooltip.type) }}
            />
            <span className="capitalize">{tooltip.type}</span>
            <span className="ml-auto">{tooltip.degree} liên kết</span>
          </div>
          {tooltip.scopeType && (
            <div className="flex items-center gap-1.5 mt-1 pt-1 border-t border-border/50 text-muted-foreground">
              <span className="material-symbols-outlined" style={{ fontSize: 11 }}>
                {tooltip.scopeType === "project" ? "folder_special" : "public"}
              </span>
              <span className="truncate">
                {tooltip.scopeType === "project" ? (tooltip.scopeName || "Không gian nghiệp vụ") : "Toàn hệ thống"}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      {!mini && (
        <div className="absolute bottom-3 left-3 rounded-xl border border-border bg-card/90 backdrop-blur-sm px-3 py-2.5 text-xs shadow-sm max-w-[240px]">
          <div className="mb-1.5 font-semibold text-foreground text-xs">Loại nút</div>
          <div className="flex flex-col gap-1">
            {Object.entries(typeCounts)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count]) => (
                <div
                  key={type}
                  className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-accent/30 transition-colors"
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{
                      background: wikiTypeColor(type),
                      boxShadow: `0 0 4px ${wikiTypeColor(type)}40`,
                    }}
                  />
                  <span className="material-symbols-outlined" style={{ fontSize: 11, color: wikiTypeColor(type) }}>
                    {wikiTypeIcon(type)}
                  </span>
                  <span className="text-muted-foreground">{wikiTypeGroupLabel(type)}</span>
                  <span className="text-muted-foreground/60 ml-auto tabular-nums">{count}</span>
                </div>
              ))}
          </div>
          {/* Scope legend */}
          {scopeCounts.length > 0 && (
            <>
              <div className="mt-2 pt-2 border-t border-border/50 mb-1.5 font-semibold text-foreground text-xs">Phạm vi</div>
              <div className="flex flex-col gap-1">
                {scopeCounts.map(([scope, count]) => (
                  <div
                    key={scope}
                    className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-accent/30 transition-colors"
                  >
                    <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 12 }}>
                       {scope === "Toàn hệ thống" ? "public" : "folder_special"}
                    </span>
                    <span className="text-muted-foreground truncate">{scope}</span>
                    <span className="text-muted-foreground/60 ml-auto tabular-nums">{count}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Zoom controls */}
      {!mini && (
        <div className="absolute bottom-3 right-3 flex flex-col items-center gap-1 rounded-xl border border-border bg-card/90 backdrop-blur-sm shadow-sm p-1">
          <button
            onClick={() => setZoom((z) => Math.min(5, z * 1.2))}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-accent/50 transition-colors text-muted-foreground hover:text-foreground"
            title="Phóng to"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
          </button>
          <span className="text-[9px] text-muted-foreground/60 tabular-nums font-medium select-none">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom((z) => Math.max(0.2, z / 1.2))}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-accent/50 transition-colors text-muted-foreground hover:text-foreground"
            title="Thu nhỏ"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>remove</span>
          </button>
          <div className="w-5 border-t border-border/50" />
          <button
            onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-accent/50 transition-colors text-muted-foreground hover:text-foreground"
            title="Đặt lại"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>fit_screen</span>
          </button>
        </div>
      )}
    </div>
  );
}

export { WikiGraphMini } from "./wiki-graph-mini";
