import { useMemo, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";

import type { LoadedBattleArtifacts } from "./artifacts";

type GraphKind = "team" | "receipt" | "signal";

interface GraphNode {
  id: string;
  label: string;
  kind: GraphKind;
  status: string;
  detail: string;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string;
  target: string;
  label: string;
}

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["pass", "blue_success"].includes(normalized)) return "statusPass";
  if (["fail", "red_success", "fake_defense"].includes(normalized)) return "statusFail";
  if (["blocked", "insufficient_evidence"].includes(normalized)) return "statusWarn";
  return "statusNeutral";
}

function receiptStatus(receipt: unknown): string {
  if (receipt && typeof receipt === "object" && "status" in receipt) {
    return String((receipt as { status?: unknown }).status ?? "UNKNOWN");
  }
  return "UNKNOWN";
}

function objectField(value: unknown, field: string): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || !(field in value)) {
    return null;
  }
  const child = (value as Record<string, unknown>)[field];
  return child && typeof child === "object" ? (child as Record<string, unknown>) : null;
}

function stringField(value: Record<string, unknown> | null, field: string, fallback = "UNKNOWN"): string {
  const raw = value?.[field];
  return raw === undefined || raw === null ? fallback : String(raw);
}

function numberField(value: Record<string, unknown> | null, field: string): number {
  const raw = value?.[field];
  return typeof raw === "number" ? raw : 0;
}

function buildGraph(data: LoadedBattleArtifacts): { nodes: GraphNode[]; links: GraphLink[] } {
  const { monitorIndex, receipts, scoreboard } = data;
  const nodes = new Map<string, GraphNode>();
  const links: GraphLink[] = [];
  const contextReceipt = receipts.context;

  nodes.set("scorekeeper", {
    id: "scorekeeper",
    label: scoreboard.verdict,
    kind: "signal",
    status: scoreboard.status,
    detail: `winner=${scoreboard.winner ?? "unknown"} tdsr=${scoreboard.tdsr}`
  });

  for (const player of monitorIndex.players) {
    const nodeId = `team:${player.team}`;
    nodes.set(nodeId, {
      id: nodeId,
      label: player.persona,
      kind: "team",
      status: receiptStatus(receipts[player.team]),
      detail: `${player.team} / ${player.role} / ${player.receipt}`
    });
    links.push({ source: nodeId, target: "scorekeeper", label: player.role });
  }

  for (const [name, path] of Object.entries(scoreboard.receipts ?? {})) {
    if (!path) continue;
    const nodeId = `receipt:${name}`;
    nodes.set(nodeId, {
      id: nodeId,
      label: path,
      kind: "receipt",
      status: receiptStatus(receipts[name]),
      detail: `${name} receipt loaded from ${path}`
    });
    const teamNode = `team:${name === "tau" || name === "context" ? "blue" : name}`;
    links.push({
      source: nodes.has(teamNode) ? teamNode : "scorekeeper",
      target: nodeId,
      label: "evidence"
    });
    links.push({ source: nodeId, target: "scorekeeper", label: "scores" });
  }

  if (scoreboard.race) {
    nodes.set("signal:race", {
      id: "signal:race",
      label: "patch before exploit",
      kind: "signal",
      status: scoreboard.race.patch_before_exploit ? "PASS" : "FAIL",
      detail: `blue=${scoreboard.race.blue_finished_at_seconds}s red=${scoreboard.race.red_finished_at_seconds}s`
    });
    links.push({ source: "team:blue", target: "signal:race", label: "finished" });
    links.push({ source: "signal:race", target: "scorekeeper", label: "decided" });
  }

  if (scoreboard.context?.enabled) {
    nodes.set("signal:memory", {
      id: "signal:memory",
      label: "memory upsert",
      kind: "signal",
      status: scoreboard.context.memory_store_status ?? "UNKNOWN",
      detail: scoreboard.context.receipt ?? "context receipt"
    });
    links.push({ source: "receipt:context", target: "signal:memory", label: "stored" });
    links.push({ source: "signal:memory", target: "scorekeeper", label: "context" });
  }

  const scan = objectField(contextReceipt, "scan");
  if (scan) {
    const families = scan["families"];
    const familyText = Array.isArray(families) ? families.join(", ") : "unknown";
    nodes.set("signal:scan", {
      id: "signal:scan",
      label: "Docker fast scan",
      kind: "signal",
      status: stringField(scan, "status"),
      detail: `${numberField(scan, "finding_count")} findings / ${familyText}`
    });
    links.push({ source: "receipt:context", target: "signal:scan", label: "scanned" });
    links.push({ source: "signal:scan", target: "signal:brave", label: "seeded" });
  }

  const brave = objectField(contextReceipt, "brave");
  if (brave) {
    nodes.set("signal:brave", {
      id: "signal:brave",
      label: "Brave research",
      kind: "signal",
      status: stringField(brave, "status"),
      detail: `${numberField(brave, "query_count")} queries / ${numberField(brave, "result_count")} results`
    });
    links.push({ source: "receipt:context", target: "signal:brave", label: "researched" });
    links.push({ source: "signal:brave", target: "signal:warm-pond", label: "seeded" });
  }

  const warmPond = objectField(contextReceipt, "warm_pond_candidates");
  if (warmPond) {
    nodes.set("signal:warm-pond", {
      id: "signal:warm-pond",
      label: "warm pond",
      kind: "signal",
      status: stringField(warmPond, "status"),
      detail: `${numberField(warmPond, "exploit_candidate_count")} exploits / ${numberField(warmPond, "defense_candidate_count")} defenses / ${numberField(warmPond, "combination_count")} combinations`
    });
    links.push({ source: "receipt:context", target: "signal:warm-pond", label: "combined" });
    links.push({ source: "signal:warm-pond", target: "scorekeeper", label: "candidates" });
  }

  const warmPondExecution = objectField(contextReceipt, "warm_pond_execution_summary");
  if (warmPondExecution) {
    nodes.set("signal:warm-pond-execution", {
      id: "signal:warm-pond-execution",
      label: "executed attempts",
      kind: "signal",
      status: stringField(warmPondExecution, "status"),
      detail: `${numberField(warmPondExecution, "passed_attempt_count")} passed / ${numberField(warmPondExecution, "selected_attempt_count")} selected / ${numberField(warmPondExecution, "failed_attempt_count")} failed`
    });
    links.push({ source: "signal:warm-pond", target: "signal:warm-pond-execution", label: "executed" });
    links.push({ source: "signal:warm-pond-execution", target: "scorekeeper", label: "evidence" });
  }

  const filteredLinks = links.filter((link) => nodes.has(link.source) && nodes.has(link.target));
  return { nodes: [...nodes.values()], links: filteredLinks };
}

function positionGraph(nodes: GraphNode[], links: GraphLink[]): PositionedNode[] {
  const width = 720;
  const height = 360;
  const simulationNodes = nodes.map((node) => ({ ...node }));
  forceSimulation(simulationNodes)
    .force("charge", forceManyBody().strength(-340))
    .force("center", forceCenter(width / 2, height / 2))
    .force("collide", forceCollide().radius(48))
    .force(
      "link",
      forceLink<GraphNode, GraphLink>(links)
        .id((node) => node.id)
        .distance((link) => (link.label === "evidence" ? 92 : 120))
        .strength(0.68)
    )
    .stop()
    .tick(180);

  return simulationNodes.map((node) => ({
    ...node,
    x: Math.max(42, Math.min(width - 42, node.x ?? width / 2)),
    y: Math.max(42, Math.min(height - 42, node.y ?? height / 2))
  }));
}

function nodeRadius(kind: GraphKind): number {
  if (kind === "team") return 22;
  if (kind === "receipt") return 15;
  return 18;
}

export function BattleForceGraph({ data }: { data: LoadedBattleArtifacts }) {
  const graph = useMemo(() => buildGraph(data), [data]);
  const positionedNodes = useMemo(
    () => positionGraph(graph.nodes, graph.links),
    [graph.links, graph.nodes]
  );
  const nodeById = useMemo(() => {
    return new Map(positionedNodes.map((node) => [node.id, node]));
  }, [positionedNodes]);
  const [selectedId, setSelectedId] = useState(positionedNodes[0]?.id ?? "");
  const selected = nodeById.get(selectedId) ?? positionedNodes[0];

  return (
    <section className="card forceGraphCard" data-qid="battle:graph:shell">
      <div className="cardHeader">
        <div>
          <div className="eyebrow">Artifact Graph</div>
          <h2>Red, Blue, Arena, context, and scorekeeper evidence</h2>
        </div>
      </div>

      <div className="forceGraphLayout">
        <svg
          className="forceGraph"
          viewBox="0 0 720 360"
          role="img"
          aria-labelledby="battle-graph-title battle-graph-desc"
          data-qid="battle:graph:svg"
        >
          <title id="battle-graph-title">Battle evidence force graph</title>
          <desc id="battle-graph-desc">
            Force-directed graph of teams, receipts, context, memory, and scorekeeper evidence.
          </desc>
          <g className="graphLinks">
            {graph.links.map((link) => {
              const source = nodeById.get(String(link.source));
              const target = nodeById.get(String(link.target));
              if (!source || !target) return null;
              return (
                <line
                  key={`${source.id}-${target.id}-${link.label}`}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                />
              );
            })}
          </g>
          <g className="graphNodes">
            {positionedNodes.map((node) => (
              <g
                key={node.id}
                className={`graphNode ${node.kind} ${statusClass(node.status)} ${selected?.id === node.id ? "selected" : ""}`}
                transform={`translate(${node.x}, ${node.y})`}
                tabIndex={0}
                role="button"
                data-qid={`battle:graph:node:${node.id}`}
                data-qs-action="BATTLE_GRAPH_SELECT_NODE"
                aria-label={`Inspect ${node.label}: ${node.status}`}
                onClick={() => setSelectedId(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelectedId(node.id);
                  }
                }}
              >
                <title>{`${node.label}: ${node.status}`}</title>
                <circle r={nodeRadius(node.kind)} />
                <text y={nodeRadius(node.kind) + 14}>{node.label}</text>
              </g>
            ))}
          </g>
        </svg>

        <aside className="graphInspector" data-qid="battle:graph:inspector">
          {selected ? (
            <>
              <div className="eyebrow">{selected.kind}</div>
              <h3>{selected.label}</h3>
              <strong className={statusClass(selected.status)}>{selected.status}</strong>
              <p>{selected.detail}</p>
            </>
          ) : null}
        </aside>
      </div>

      <table className="srOnly">
        <caption>Battle graph nodes</caption>
        <thead>
          <tr>
            <th>Node</th>
            <th>Kind</th>
            <th>Status</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {positionedNodes.map((node) => (
            <tr key={node.id}>
              <td>{node.label}</td>
              <td>{node.kind}</td>
              <td>{node.status}</td>
              <td>{node.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
