import { useEffect, useMemo, useState } from "react";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { sankey, sankeyLinkHorizontal } from "d3-sankey";
import {
  Activity,
  Braces,
  Bug,
  CirclePlay,
  FileJson,
  History,
  LoaderCircle,
  Network,
  RotateCcw,
  Scale,
  Shield,
  Swords,
  TriangleAlert
} from "lucide-react";

import { loadBattleArtifacts } from "./artifacts";
import { BattleChatSidebar } from "./BattleChatSidebar";
import type {
  BattleGraphLink,
  BattleGraphNode,
  DetailKey,
  JudgeCommand,
  LoadedBattleArtifacts,
  Team
} from "./types";
import { useRegisterAction } from "./useRegisterAction";

type LoadState =
  | { status: "loading" }
  | { status: "loaded"; data: LoadedBattleArtifacts }
  | { status: "blocked"; error: string };

const GRAPH_WIDTH = 920;
const GRAPH_HEIGHT = 390;
const SANKEY_WIDTH = 640;
const SANKEY_HEIGHT = 280;

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["pass", "blue_success"].includes(normalized)) return "statusPass";
  if (["fail", "red_success", "fake_defense"].includes(normalized)) return "statusFail";
  if (["blocked", "insufficient_evidence"].includes(normalized)) return "statusWarn";
  return "statusNeutral";
}

function groupClass(group: Team): string {
  return `node-${group}`;
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function commandLabel(command: JudgeCommand): string {
  return command.command.slice(-2).join(" ");
}

function buildGraph(data: LoadedBattleArtifacts): {
  nodes: BattleGraphNode[];
  links: BattleGraphLink[];
} {
  const nodes: BattleGraphNode[] = [
    {
      id: "arena",
      label: "Arena",
      group: "arena",
      status: data.run.upstream_arena_status,
      detailKey: "arena"
    },
    {
      id: "visibility",
      label: "Public Boundary",
      group: "arena",
      status: data.visibility.status,
      detailKey: "visibility"
    },
    {
      id: "tau",
      label: "Tau Harness",
      group: "scoreboard",
      status: data.tau.status,
      detailKey: "tau"
    },
    {
      id: "red",
      label: "Red Exploit",
      group: "red",
      status: data.red.result.status,
      detailKey: "red"
    },
    {
      id: "blue",
      label: "Blue Patch",
      group: "blue",
      status: data.blue.result.status,
      detailKey: "blue"
    },
    {
      id: "judge",
      label: "Docker Judge",
      group: "judge",
      status: data.judge.status,
      detailKey: "judge"
    },
    {
      id: "scoreboard",
      label: "Scoreboard",
      group: "scoreboard",
      status: data.scoreboard.status,
      detailKey: "scoreboard"
    }
  ];

  const links: BattleGraphLink[] = [
    { id: "arena-visibility", source: "arena", target: "visibility", label: "public bundle", value: 2 },
    { id: "visibility-tau", source: "visibility", target: "tau", label: "handoff context", value: 2 },
    { id: "tau-red", source: "tau", target: "red", label: "red receipt", value: 1 },
    { id: "tau-blue", source: "tau", target: "blue", label: "blue receipt", value: 1 },
    { id: "red-judge", source: "red", target: "judge", label: "exploit replay", value: 1 },
    { id: "blue-judge", source: "blue", target: "judge", label: "patch replay", value: 1 },
    { id: "judge-scoreboard", source: "judge", target: "scoreboard", label: "verdict", value: 2 }
  ];

  return { nodes, links };
}

function layoutGraph(nodes: BattleGraphNode[], links: BattleGraphLink[]): BattleGraphNode[] {
  const laidOut = nodes.map((node) => ({ ...node }));
  const xTargets: Record<string, number> = {
    arena: 95,
    visibility: 245,
    tau: 395,
    red: 560,
    blue: 560,
    judge: 735,
    scoreboard: 850
  };
  const yTargets: Record<string, number> = {
    arena: 195,
    visibility: 195,
    tau: 195,
    red: 120,
    blue: 270,
    judge: 195,
    scoreboard: 195
  };

  const simLinks = links.map((link) => ({ ...link }));
  const simulation = forceSimulation(laidOut)
    .force(
      "link",
      forceLink<BattleGraphNode, BattleGraphLink>(simLinks)
        .id((node) => node.id)
        .distance(120)
        .strength(0.42)
    )
    .force("charge", forceManyBody().strength(-350))
    .force("collide", forceCollide<BattleGraphNode>().radius(54))
    .force("x", forceX<BattleGraphNode>((node) => xTargets[node.id] ?? GRAPH_WIDTH / 2).strength(0.42))
    .force("y", forceY<BattleGraphNode>((node) => yTargets[node.id] ?? GRAPH_HEIGHT / 2).strength(0.5))
    .stop();

  for (let i = 0; i < 180; i += 1) {
    simulation.tick();
  }

  return laidOut.map((node) => ({
    ...node,
    x: Math.max(58, Math.min(GRAPH_WIDTH - 58, node.x ?? GRAPH_WIDTH / 2)),
    y: Math.max(62, Math.min(GRAPH_HEIGHT - 62, node.y ?? GRAPH_HEIGHT / 2))
  }));
}

function SummaryMetric({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string;
  tone?: "neutral" | "red" | "blue" | "pass";
}) {
  return (
    <article className={`metricTile ${tone}`}>
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ArenaLeftPane({
  data,
  onReplay
}: {
  data: LoadedBattleArtifacts;
  onReplay: () => void;
}) {
  const challenges = [
    {
      qid: "battle:challenge:arena-tau-public-only-002",
      label: "Tau public-only executable",
      status: data.scoreboard.verdict,
      href: "/?artifactBase=/artifacts/arena-tau-public-only-002"
    },
    {
      qid: "battle:challenge:battle-003-arena-context",
      label: "Arena context rung",
      status: "prior",
      href: "/?artifactBase=/artifacts/battle-003-arena-context"
    },
    {
      qid: "battle:challenge:battle-v1-operational",
      label: "Battle v1 operational",
      status: "prior",
      href: "/?artifactBase=/artifacts/battle-v1-operational"
    },
    {
      qid: "battle:challenge:battle-001",
      label: "Seed fixture",
      status: "prior",
      href: "/?artifactBase=/artifacts/battle-001"
    }
  ];

  useRegisterAction("battle:challenge:arena-tau-public-only-002", {
    app: "battle-monitor",
    action: "BATTLE_OPEN_CURRENT_ARENA_CHALLENGE",
    label: "Open current Arena challenge",
    description: "Open the current Tau public-only Arena challenge artifact set"
  });
  useRegisterAction("battle:challenge:battle-003-arena-context", {
    app: "battle-monitor",
    action: "BATTLE_OPEN_ARENA_CONTEXT_CHALLENGE",
    label: "Open Arena context rung",
    description: "Navigate to the prior Arena context artifact set"
  });
  useRegisterAction("battle:challenge:battle-v1-operational", {
    app: "battle-monitor",
    action: "BATTLE_OPEN_V1_OPERATIONAL_CHALLENGE",
    label: "Open Battle v1 operational",
    description: "Navigate to the prior Battle v1 operational artifact set"
  });
  useRegisterAction("battle:challenge:battle-001", {
    app: "battle-monitor",
    action: "BATTLE_OPEN_SEED_FIXTURE_CHALLENGE",
    label: "Open seed fixture",
    description: "Navigate to the original Battle seed fixture artifact set"
  });
  useRegisterAction("battle:rail:replay", {
    app: "battle-monitor",
    action: "BATTLE_REPLAY_FROM_RAIL",
    label: "Replay current round",
    description: "Scroll to the replay control for the current Arena round"
  });

  return (
    <aside className="arenaRail" data-qid="battle:arena:left-pane">
      <section className="railSection">
        <div className="railHeader">
          <Bug size={18} />
          <div>
            <div className="eyebrow">Arena Challenge</div>
            <h2>{data.scenario.scenario_id}</h2>
          </div>
        </div>
        <p>{data.scenario.title}</p>
        <dl className="railKv">
          <div>
            <dt>Entry</dt>
            <dd>{data.scenario.public_entrypoint}</dd>
          </div>
          <div>
            <dt>Target</dt>
            <dd>{data.scenario.target_language}</dd>
          </div>
          <div>
            <dt>Difficulty</dt>
            <dd>{data.scenario.difficulty}</dd>
          </div>
        </dl>
        <button
          type="button"
          className="railReplayButton"
          data-qid="battle:rail:replay"
          data-qs-action="BATTLE_REPLAY_FROM_RAIL"
          title="Replay current Arena round"
          onClick={onReplay}
        >
          <CirclePlay size={17} />
          <span>Replay current round</span>
        </button>
      </section>

      <section className="railSection">
        <div className="eyebrow">Playing Field</div>
        <ul className="railList">
          <li>Red and Blue received the same public bundle.</li>
          <li>Blue did not receive Red’s exploit before patching.</li>
          <li>Red did not receive Blue’s patch before the Judge replay.</li>
          <li>Arena/Judge retained the private answer key.</li>
        </ul>
      </section>

      <section className="railSection">
        <div className="eyebrow">Hidden Exploit Slots</div>
        <div className="hiddenSlotList">
          {data.ledger.vulnerabilities.map((item) => (
            <article key={item.id}>
              <strong>{item.id}</strong>
              <span>{item.difficulty} · weight {item.weight}</span>
              <code>{item.status}</code>
            </article>
          ))}
        </div>
      </section>

      <section className="railSection">
        <div className="railHeader compact">
          <History size={17} />
          <div className="eyebrow">Past Arena Challenges</div>
        </div>
        <div className="challengeList">
          {challenges.map((challenge) => (
            <button
              key={challenge.qid}
              type="button"
              data-qid={challenge.qid}
              data-qs-action={challenge.qid.replaceAll(":", "_").toUpperCase()}
              title={`Open ${challenge.label}`}
              onClick={() => {
                window.location.href = challenge.href;
              }}
            >
              <span>{challenge.label}</span>
              <code>{challenge.status}</code>
            </button>
          ))}
        </div>
      </section>
    </aside>
  );
}

function ForceGraph({
  data,
  selected,
  onSelect
}: {
  data: LoadedBattleArtifacts;
  selected: DetailKey;
  onSelect: (key: DetailKey) => void;
}) {
  const { nodes, links } = useMemo(() => buildGraph(data), [data]);
  const laidOut = useMemo(() => layoutGraph(nodes, links), [nodes, links]);
  const nodeMap = useMemo(() => new Map(laidOut.map((node) => [node.id, node])), [laidOut]);

  return (
    <section className="panel graphPanel" data-qid="battle:graph:panel">
      <div className="panelHeader">
        <div>
          <div className="eyebrow">Force Graph</div>
          <h2>Arena round handoff map</h2>
        </div>
        <Network size={20} />
      </div>

      <svg
        className="forceGraph"
        viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
        role="img"
        aria-labelledby="battle-force-title"
        data-qid="battle:graph:force"
      >
        <title id="battle-force-title">Battle Arena to Tau to Judge to Scoreboard graph</title>
        <g className="graphLinks">
          {links.map((link) => {
            const source = nodeMap.get(link.source);
            const target = nodeMap.get(link.target);
            if (!source || !target) return null;
            return (
              <g key={link.id}>
                <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} />
                <text x={((source.x ?? 0) + (target.x ?? 0)) / 2} y={((source.y ?? 0) + (target.y ?? 0)) / 2 - 8}>
                  {link.label}
                </text>
              </g>
            );
          })}
        </g>
        <g className="graphNodes">
          {laidOut.map((node) => (
            <GraphNodeElement
              key={node.id}
              node={node}
              selected={selected === node.detailKey}
              onSelect={onSelect}
            />
          ))}
        </g>
      </svg>

      <table className="srTable">
        <caption>Graph node details</caption>
        <tbody>
          {laidOut.map((node) => (
            <tr key={node.id}>
              <th>{node.label}</th>
              <td>{node.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function GraphNodeElement({
  node,
  selected,
  onSelect
}: {
  node: BattleGraphNode;
  selected: boolean;
  onSelect: (key: DetailKey) => void;
}) {
  const action = `BATTLE_SELECT_${node.id.toUpperCase()}`;
  useRegisterAction(`battle:graph:node:${node.id}`, {
    app: "battle-monitor",
    action,
    label: `Inspect ${node.label}`,
    description: `Open drill-down details for ${node.label}`
  });

  return (
    <g
      className={`graphNode ${groupClass(node.group)} ${selected ? "selected" : ""}`}
      transform={`translate(${node.x}, ${node.y})`}
      data-qid={`battle:graph:node:${node.id}`}
      data-qs-action={action}
      {...({ title: `Inspect ${node.label}` } as Record<string, string>)}
      aria-label={`Inspect ${node.label}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(node.detailKey)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(node.detailKey);
        }
      }}
    >
      <title>{`Inspect ${node.label}`}</title>
      <circle r="38" />
      <text className="nodeLabel" y="-3">
        {node.label}
      </text>
      <text className={`nodeStatus ${statusClass(node.status)}`} y="16">
        {node.status}
      </text>
    </g>
  );
}

function ExploitSankey({ data }: { data: LoadedBattleArtifacts }) {
  const chart = useMemo(() => {
    const graph: {
      nodes: Array<{ nodeId: number; name: string }>;
      links: Array<{ source: number; target: number; value: number }>;
    } = {
      nodes: [
        { nodeId: 0, name: "Vulnerable target" },
        { nodeId: 1, name: "Red exploit confirmed" },
        { nodeId: 2, name: "Blue patch" },
        { nodeId: 3, name: "Judge blocked replay" },
        { nodeId: 4, name: "Scoreboard BLUE_SUCCESS" }
      ],
      links: [
        { source: 0, target: 1, value: data.judge.exploit_confirmed_before_patch ? 2 : 0.2 },
        { source: 1, target: 2, value: data.blue.result.status === "PASS" ? 2 : 0.2 },
        { source: 2, target: 3, value: data.judge.exploit_blocked_after_patch ? 2 : 0.2 },
        { source: 3, target: 4, value: data.scoreboard.verdict === "BLUE_SUCCESS" ? 2 : 0.2 }
      ]
    };

    return sankey<{ nodeId: number; name: string }, { source: number; target: number; value: number }>()
      .nodeId((node) => node.nodeId)
      .nodeWidth(16)
      .nodePadding(24)
      .extent([
        [10, 16],
        [SANKEY_WIDTH - 16, SANKEY_HEIGHT - 18]
      ])(graph);
  }, [data]);

  return (
    <section className="panel" data-qid="battle:sankey:panel">
      <div className="panelHeader">
        <div>
          <div className="eyebrow">Exploit Evolution</div>
          <h2>Replay path to verdict</h2>
        </div>
        <Activity size={20} />
      </div>

      <svg
        className="sankeyChart"
        viewBox={`0 0 ${SANKEY_WIDTH} ${SANKEY_HEIGHT}`}
        role="img"
        aria-labelledby="battle-sankey-title"
        data-qid="battle:sankey:chart"
      >
        <title id="battle-sankey-title">Successful exploit evolution into blocked replay and score</title>
        <g className="sankeyLinks">
          {chart.links.map((link, index) => (
            <path key={index} d={sankeyLinkHorizontal()(link) ?? ""} style={{ strokeWidth: Math.max(1, link.width ?? 1) }} />
          ))}
        </g>
        <g>
          {chart.nodes.map((node, index) => (
            <g key={node.name} className="sankeyNode">
              <rect x={node.x0} y={node.y0} width={(node.x1 ?? 0) - (node.x0 ?? 0)} height={(node.y1 ?? 0) - (node.y0 ?? 0)} />
              <text x={(node.x0 ?? 0) + 24} y={((node.y0 ?? 0) + (node.y1 ?? 0)) / 2}>
                {index + 1}. {node.name}
              </text>
            </g>
          ))}
        </g>
      </svg>

      <ol className="sankeyLegend">
        <li>Vulnerable target accepted the duplicate-claim token.</li>
        <li>Red materialized an executable exploit through Tau.</li>
        <li>Blue materialized a replacement `app.py` through Tau.</li>
        <li>Judge replayed Red against the patched target and blocked it.</li>
      </ol>
    </section>
  );
}

function DetailPanel({ data, selected }: { data: LoadedBattleArtifacts; selected: DetailKey }) {
  const payloads: Record<DetailKey, unknown> = {
    run: data.run,
    arena: {
      scenario: data.scenario,
      hidden_ledger_summary: data.ledger.vulnerabilities
    },
    visibility: data.visibility,
    red: data.red,
    blue: data.blue,
    judge: data.judge,
    scoreboard: data.scoreboard,
    tau: data.tau
  };

  return (
    <section className="panel detailPanel" data-qid="battle:detail:panel">
      <div className="panelHeader">
        <div>
          <div className="eyebrow">Drill Down</div>
          <h2>{selected}</h2>
        </div>
        <FileJson size={20} />
      </div>
      <pre data-qid="battle:detail:json">{prettyJson(payloads[selected])}</pre>
    </section>
  );
}

function ReplayControl({ data, replayNonce }: { data: LoadedBattleArtifacts; replayNonce: number }) {
  const [step, setStep] = useState(0);
  const replaySteps = [
    {
      label: "Original replay",
      value: data.judge.exploit_confirmed_before_patch ? "Exploit confirmed before patch" : "Exploit missed original target",
      command: commandLabel(data.judge.commands_run[0])
    },
    {
      label: "Patched replay",
      value: data.judge.exploit_blocked_after_patch ? "Exploit blocked after patch" : "Exploit still works after patch",
      command: commandLabel(data.judge.commands_run[1])
    },
    {
      label: "Functionality",
      value: data.judge.functionality_preserved ? "Normal behavior preserved" : "Regression detected",
      command: "verify_token / make_token smoke"
    },
    {
      label: "Score",
      value: `${data.scoreboard.verdict}: red ${data.scoreboard.red_score}, blue ${data.scoreboard.blue_score}`,
      command: "scoreboard consumption"
    }
  ];
  const current = replaySteps[step];

  useEffect(() => {
    setStep(0);
  }, [replayNonce]);

  useRegisterAction("battle:replay:play", {
    app: "battle-monitor",
    action: "BATTLE_REPLAY_ADVANCE",
    label: "Replay",
    description: "Advance the Arena round replay one receipt-backed step"
  });
  useRegisterAction("battle:replay:reset", {
    app: "battle-monitor",
    action: "BATTLE_REPLAY_RESET",
    label: "Reset replay",
    description: "Reset the Arena round replay to the first Judge replay step"
  });

  return (
    <section className="panel replayPanel" data-qid="battle:replay:panel">
      <div className="panelHeader">
        <div>
          <div className="eyebrow">Replay</div>
          <h2>Round recap controls</h2>
        </div>
        <CirclePlay size={20} />
      </div>

      <div className="replayStage" data-qid="battle:replay:stage">
        <span className="eyebrow">Step {step + 1} of {replaySteps.length}</span>
        <strong>{current.label}</strong>
        <p>{current.value}</p>
        <code>{current.command}</code>
      </div>

      <div className="replayButtons">
        <button
          type="button"
          data-qid="battle:replay:play"
          data-qs-action="BATTLE_REPLAY_ADVANCE"
          title="Advance replay"
          onClick={() => setStep((currentStep) => Math.min(replaySteps.length - 1, currentStep + 1))}
        >
          <CirclePlay size={16} />
          <span>Replay</span>
        </button>
        <button
          type="button"
          data-qid="battle:replay:reset"
          data-qs-action="BATTLE_REPLAY_RESET"
          title="Reset replay"
          onClick={() => setStep(0)}
        >
          <RotateCcw size={16} />
          <span>Reset</span>
        </button>
      </div>
    </section>
  );
}

function LoadingView() {
  return (
    <main className="centerShell" data-qid="battle:loading:shell">
      <section className="statePanel">
        <LoaderCircle size={28} className="spin" />
        <div>
          <div className="eyebrow">Battle Monitor</div>
          <h1>Loading Arena receipts</h1>
        </div>
      </section>
    </main>
  );
}

function BlockedView({ error }: { error: string }) {
  return (
    <main className="centerShell" data-qid="battle:blocked:shell">
      <section className="statePanel blockedPanel">
        <TriangleAlert size={30} />
        <div>
          <div className="eyebrow">Battle Monitor Blocked</div>
          <h1>BATTLE MONITOR BLOCKED</h1>
          <p>Missing required generated artifact.</p>
          <p>Do not claim UI acceptance.</p>
          <pre>{error}</pre>
        </div>
      </section>
    </main>
  );
}

function LoadedView({ data }: { data: LoadedBattleArtifacts }) {
  const [selected, setSelected] = useState<DetailKey>("scoreboard");
  const [replayNonce, setReplayNonce] = useState(0);

  return (
    <main className="monitorShell" data-qid="battle:arena:shell">
      <ArenaLeftPane
        data={data}
        onReplay={() => {
          setReplayNonce((current) => current + 1);
          document.querySelector('[data-qid="battle:replay:panel"]')?.scrollIntoView({
            behavior: "smooth",
            block: "center"
          });
        }}
      />
      <div className="appShell">
        <header className="hero" data-qid="battle:arena:hero">
          <div>
            <div className="eyebrow">Battle Arena Recap</div>
            <h1>{data.scenario.title}</h1>
            <p>
              Public-only Tau handoff round for {data.scenario.public_entrypoint}. Red and Blue received the same public bundle; Arena and Judge retained the private answer key.
            </p>
          </div>

          <div className="heroStatus">
            <Scale size={22} />
            <span className="eyebrow">Verdict</span>
            <strong className={statusClass(data.scoreboard.verdict)}>{data.scoreboard.verdict}</strong>
            <code>{data.run.battle_id}</code>
          </div>
        </header>

        <section className="metricGrid" data-qid="battle:metrics:grid">
          <SummaryMetric label="Red score" value={data.scoreboard.red_score.toFixed(1)} tone="red" />
          <SummaryMetric label="Blue score" value={data.scoreboard.blue_score.toFixed(1)} tone="blue" />
          <SummaryMetric label="Visibility" value={data.visibility.private_input_leaks.length === 0 ? "No leaks" : "Leaks"} tone="pass" />
          <SummaryMetric label="Vulns" value={String(data.scoreboard.per_vulnerability.length)} />
          <SummaryMetric label="Mode" value={data.scoreboard.mode.replaceAll("_", " ")} />
        </section>

        <section className="roundGrid">
          <article className="panel">
            <div className="panelHeader">
              <div>
                <div className="eyebrow">Entry Point</div>
                <h2>{data.scenario.public_entrypoint}</h2>
              </div>
              <Bug size={20} />
            </div>
            <dl className="kv">
              <div>
                <dt>Target</dt>
                <dd>{data.scenario.target_language}</dd>
              </div>
              <div>
                <dt>Contract</dt>
                <dd>{data.scenario.public_contract.method} {data.scenario.public_contract.input}</dd>
              </div>
              <div>
                <dt>Stop</dt>
                <dd>{data.scenario.stop_condition}</dd>
              </div>
            </dl>
          </article>

          <article className="panel">
            <div className="panelHeader">
              <div>
                <div className="eyebrow">Team Artifacts</div>
                <h2>Executable submissions</h2>
              </div>
              <Braces size={20} />
            </div>
            <div className="artifactRows">
              <div>
                <Swords size={16} />
                <span>Red</span>
                <code>{data.red.result.materialized_artifact.artifact_type}</code>
              </div>
              <div>
                <Shield size={16} />
                <span>Blue</span>
                <code>{data.blue.result.materialized_artifact.artifact_type}</code>
              </div>
            </div>
          </article>
        </section>

        <ForceGraph data={data} selected={selected} onSelect={setSelected} />

        <section className="analysisGrid">
          <ExploitSankey data={data} />
          <ReplayControl data={data} replayNonce={replayNonce} />
        </section>

        <section className="analysisGrid">
          <DetailPanel data={data} selected={selected} />
          <section className="panel" data-qid="battle:vulnerabilities:panel">
            <div className="panelHeader">
              <div>
                <div className="eyebrow">Private Ledger Summary</div>
                <h2>Difficulty-weighted outcomes</h2>
              </div>
              <FileJson size={20} />
            </div>
            <div className="vulnerabilityList">
              {data.scoreboard.per_vulnerability.map((item) => (
                <article key={item.id}>
                  <strong>{item.id}</strong>
                  <span>{item.difficulty} / weight {item.weight}</span>
                  <code>{item.outcome}</code>
                </article>
              ))}
            </div>
          </section>
        </section>
      </div>
      <BattleChatSidebar data={data} />
    </main>
  );
}

export function App() {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;

    loadBattleArtifacts()
      .then((data) => {
        if (active) {
          setLoadState({ status: "loaded", data });
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setLoadState({
            status: "blocked",
            error: error instanceof Error ? error.message : String(error)
          });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  if (loadState.status === "loading") {
    return <LoadingView />;
  }

  if (loadState.status === "blocked") {
    return <BlockedView error={loadState.error} />;
  }

  return <LoadedView data={loadState.data} />;
}
