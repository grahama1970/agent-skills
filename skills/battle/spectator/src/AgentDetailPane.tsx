import { useMemo, useState } from "react";
import { Bot, Bug, Database, FileJson, Play, Search, ShieldX, Terminal } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import type { BattleEvent, BattleReceiptRef, BattleReplayRef, BlueFinisherState, Lane, ProofMode } from "./lib/battle-types";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import { MockupAgentDetailPane } from "./MockupAgentDetailPane";

type Props = { lane: Lane; lanes: Lane[]; events: BattleEvent[]; activeFinisher: BlueFinisherState | null; onSound?: (cue: string) => void };
type TraceField = "observation" | "hypothesis" | "action" | "result" | "learned" | "next_move";
const TRACE_FIELDS: Array<[TraceField, string]> = [["observation", "Observation"], ["hypothesis", "Hypothesis"], ["action", "Action"], ["result", "Result"], ["learned", "Learned"], ["next_move", "Next move"]];

export function AgentDetailPane({ lane, lanes, events, activeFinisher, onSound }: Props) {
  void lanes;
  if (isBattleDesignView()) return <MockupAgentDetailPane lane={lane} />;
  void activeFinisher;
  void onSound;
  useRegisterAction("battle:agent-pane:tab:summary", { action: "BATTLE_AGENT_PANE_TAB_SUMMARY", label: "Show Battle Agent Summary", description: "Show the Summary tab in the Battle agent detail pane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:turns", { action: "BATTLE_AGENT_PANE_TAB_TURNS", label: "Show Battle Agent Turns", description: "Show the public Battle event trace for the selected lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:logs", { action: "BATTLE_AGENT_PANE_TAB_LOGS", label: "Show Battle Agent Logs", description: "Show receipt-backed JSON events for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:skills", { action: "BATTLE_AGENT_PANE_TAB_SKILLS", label: "Show Battle Agent Skills", description: "Show emitted skills/tools for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:tab:receipts", { action: "BATTLE_AGENT_PANE_TAB_RECEIPTS", label: "Show Battle Agent Receipts", description: "Show proof artifacts for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });
  useRegisterAction("battle:agent-pane:proof:docker-replay", { action: "BATTLE_AGENT_PANE_DOCKER_REPLAY", label: "Show Docker Replay Proof", description: "Show the receipt-backed Docker/Judge replay proof for the selected Battle lane.", tags: ["battle", "agent-cockpit"] });

  const model = useMemo(() => buildModel(lane, events), [lane, events]);
  const replay = model.replay;

  return (
    <aside className="flex h-full min-h-0 w-full flex-col" data-qid={`battle:agent-pane:${lane.id}`} title={`Agent detail for ${lane.name}`}>
      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl p-0">
        <header className="border-b border-white/10 bg-gradient-to-r from-white/[.035] to-transparent p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div><div className="battle-label">Agent Detail</div><div className="mt-0.5 text-xs font-semibold text-slate-400">Selected agent cockpit</div></div>
            <ProofBadge mode={model.proofMode} />
          </div>
          <div className="flex items-start gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-xl border border-battle-red/45 bg-battle-red/12 text-battle-red shadow-redGlow"><Bug className="h-7 w-7" /></div>
            <div className="min-w-0 flex-1">
              <h2 className="mt-1 truncate text-lg font-black text-white">{lane.name}</h2>
              <div className="mt-1 truncate text-xs text-slate-400">Gen {lane.generation} · {lane.payloadId}</div>
              <div className="mt-1 flex items-center gap-1.5 truncate font-mono text-[10px] text-slate-600"><Bot className="h-3 w-3 shrink-0" /> {model.agentId}</div>
            </div>
          </div>
        </header>

        {replay ? <ReplayPanel replay={replay} /> : <NoReplayPanel />}

        <Tabs defaultValue="summary" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="grid w-full grid-cols-5 rounded-none border-b border-white/10 bg-black/20">
            <TabsTrigger data-qid="battle:agent-pane:tab:summary" data-qs-action="BATTLE_AGENT_PANE_TAB_SUMMARY" value="summary" title="Show Summary tab" className="min-h-11 px-1.5 text-[11px]">Summary</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:turns" data-qs-action="BATTLE_AGENT_PANE_TAB_TURNS" value="turns" title="Show Turns tab" className="min-h-11 px-1.5 text-[11px]">Turns</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:logs" data-qs-action="BATTLE_AGENT_PANE_TAB_LOGS" value="logs" title="Show Logs tab" className="min-h-11 px-1.5 text-[11px]">Logs</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:skills" data-qs-action="BATTLE_AGENT_PANE_TAB_SKILLS" value="skills" title="Show Skills tab" className="min-h-11 px-1.5 text-[11px]">Skills</TabsTrigger>
            <TabsTrigger data-qid="battle:agent-pane:tab:receipts" data-qs-action="BATTLE_AGENT_PANE_TAB_RECEIPTS" value="receipts" title="Show Receipts tab" className="min-h-11 px-1.5 text-[11px]">Receipts</TabsTrigger>
          </TabsList>
          <div className="min-h-0 flex-1 overflow-auto p-2.5">
            <TabsContent value="summary" className="mt-0 space-y-2"><CurrentTurn model={model} /><TraceCard trace={model.trace} /><OutputCard stdout={model.stdout} stderr={model.stderr} /><SkillsCard skills={model.skills} /></TabsContent>
            <TabsContent value="turns" className="mt-0 space-y-2">{model.turnEvents.length ? model.turnEvents.map((event) => <TurnEvent key={event.id} event={event} />) : <EmptyState label="No Battle turns emitted." />}</TabsContent>
            <TabsContent value="logs" className="mt-0 space-y-3">{model.relatedEvents.map((event) => <EventRow key={event.id} event={event} />)}<RawJson events={model.relatedEvents} /></TabsContent>
            <TabsContent value="skills" className="mt-0 space-y-2">{model.skills.length ? model.skills.map((skill) => <SkillRow key={`${skill.name}-${skill.receipt_id ?? "no-receipt"}`} skill={skill} />) : <EmptyState label="No skills/tools emitted for this lane." />}</TabsContent>
            <TabsContent value="receipts" className="mt-0 space-y-3"><ReceiptsCard receipts={model.receipts} /></TabsContent>
          </div>
        </Tabs>
      </Card>
    </aside>
  );
}

function ReplayPanel({ replay }: { replay: BattleReplayRef }) {
  const qid = `battle:agent-pane:replay:${replay.pair_id ?? replay.receipt_id}`;
  return (
    <section className="m-3 rounded-xl border border-battle-blue/40 bg-battle-blue/14 p-3 shadow-blueGlow">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0"><div className="battle-label text-battle-blue">Docker replay</div><div className="mt-1 text-lg font-black text-white">REPLAY IN DOCKER</div><div className="mt-1 truncate text-xs text-slate-400">{replay.can_execute_now ? "Executable replay endpoint available" : "Opens Judge replay receipt · not live execution"}</div></div>
        <ProofBadge mode={replay.proof_mode} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-400"><InfoLine label="red" value={replay.red_worker_id ?? "not emitted"} /><InfoLine label="blue" value={replay.blue_worker_id ?? "not emitted"} /></div>
      <Button data-qid={qid} data-qs-action="BATTLE_AGENT_PANE_DOCKER_REPLAY" title={replay.can_execute_now ? "Run Docker replay endpoint" : "Open receipt-backed Judge replay proof; this does not start live execution"} variant="green" className="mt-3 w-full min-h-11 justify-start text-left"><Play className="h-4 w-4" /> {replay.can_execute_now ? "RUN REPLAY IN DOCKER" : "OPEN REPLAY RECEIPT"}</Button>
    </section>
  );
}

function NoReplayPanel() {
  return <section className="m-3 rounded-xl border border-white/10 bg-white/[.025] p-3"><div className="battle-label">Docker replay</div><div className="mt-1 text-sm text-slate-500">No Judge replay receipt is attached to this selected exploit lane.</div></section>;
}

function CurrentTurn({ model }: { model: AgentPaneModel }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="text-xs font-black uppercase tracking-[.08em] text-battle-purple">Current loop · #{model.loopIndex}</div><div className="mt-1 text-sm leading-5 text-slate-300">{model.currentAction}</div><div className="mt-1 truncate font-mono text-xs text-slate-500">{model.turnId}</div></div><Badge variant="purple">{model.phase}</Badge></div></section>;
}

function TraceCard({ trace }: { trace: Record<TraceField, string | undefined> }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="battle-label">Public trace</div><div className="mt-2 grid gap-1.5">{TRACE_FIELDS.map(([key, label]) => <div key={key} className="grid grid-cols-[86px_1fr] gap-2 text-xs leading-5"><span className="battle-label">{label}</span><span className={trace[key] ? "text-slate-300" : "text-slate-600"}>{trace[key] || "not emitted"}</span></div>)}</div></section>;
}

function OutputCard({ stdout, stderr }: { stdout: string; stderr: string }) {
  return <section className="grid grid-cols-2 gap-2"><InfoPanel label="stdout latest" value={stdout} tone="text-slate-300" /><InfoPanel label="stderr latest" value={stderr} tone="text-battle-red" /></section>;
}

function SkillsCard({ skills }: { skills: AgentPaneSkill[] }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="mb-2 battle-label">Skills / tools used</div><div className="flex flex-wrap gap-2">{skills.length ? skills.map((skill) => <SkillChip key={`${skill.name}-${skill.receipt_id ?? "no-receipt"}`} skill={skill} />) : <span className="text-xs text-slate-600">not emitted</span>}</div></section>;
}

function ReceiptsCard({ receipts }: { receipts: BattleReceiptRef[] }) {
  return <section className="rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="mb-2 battle-label">Receipts / proof</div><div className="space-y-2">{receipts.length ? receipts.map((receipt) => <ReceiptRow key={`${receipt.receipt_id}-${receipt.receipt_type}-${receipt.pair_id ?? "lane"}`} receipt={receipt} />) : <div className="text-xs text-slate-600">not emitted</div>}</div></section>;
}

function TurnEvent({ event }: { event: BattleEvent }) {
  return <div className="rounded-xl border border-white/10 bg-white/[.025] p-3"><div className="flex items-start gap-3"><div className="mt-0.5 text-battle-blue"><Terminal className="h-4 w-4" /></div><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><div className="truncate font-black text-slate-100">{event.turn?.phase ?? event.event_type}</div><ProofBadge mode={event.proof_mode ?? "missing"} /></div><div className="mt-1 text-sm leading-5 text-slate-300">{event.turn?.current_action ?? event.summary}</div><div className="mt-2 text-xs text-battle-green">{event.public_trace?.learned || "not emitted"}</div></div></div></div>;
}

function EventRow({ event }: { event: BattleEvent }) {
  return <div className="grid grid-cols-[1fr_auto] gap-2 rounded-xl border border-white/10 bg-white/[.025] p-3 text-xs"><div className="min-w-0"><div className="truncate font-bold text-slate-100">{event.event_type}</div><div className="mt-1 truncate text-slate-400">{event.summary}</div></div><ProofBadge mode={event.proof_mode ?? "missing"} /></div>;
}

function RawJson({ events }: { events: BattleEvent[] }) {
  const [open, setOpen] = useState(false);
  return <section><div className="mb-2 flex items-center justify-between"><div className="battle-label">Raw JSON</div><Button data-qid="battle:agent-pane:logs:raw-toggle" data-qs-action="BATTLE_AGENT_PANE_LOGS_RAW_TOGGLE" title="Toggle raw receipt-backed event JSON" variant="ghost" onClick={() => setOpen((value) => !value)}>{open ? "Hide raw JSON" : "View raw JSON"}</Button></div>{open ? <pre className="max-h-64 overflow-auto rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-xs leading-6 text-slate-300">{events.map((event) => JSON.stringify(event)).join("\n") || "No related receipt-backed events."}</pre> : null}</section>;
}

function SkillRow({ skill }: { skill: AgentPaneSkill }) {
  return <div className="grid grid-cols-[1fr_74px_120px] items-center gap-2 rounded-xl border border-white/10 bg-white/[.025] px-3 py-2 text-sm"><div className="min-w-0"><div className="flex items-center gap-2 truncate font-bold text-slate-100"><SkillIcon name={skill.name} />{skill.name}</div><div className="truncate text-xs text-slate-500">{skill.summary || "not emitted"}</div></div><Badge variant={skill.kind === "tool" ? "blue" : "green"}>{skill.kind}</Badge><ProofBadge mode={skill.proof_mode} /></div>;
}

function SkillChip({ skill }: { skill: AgentPaneSkill }) {
  return <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-battle-green/25 bg-battle-green/10 px-2 py-1 text-xs font-bold text-battle-green" title={`${skill.kind} · ${proofLabel(skill.proof_mode)}`}><SkillIcon name={skill.name} /><span className="truncate">{skill.name}</span><span className="rounded border border-white/10 px-1 text-[9px] uppercase text-slate-400">{skill.kind}</span></span>;
}

function SkillIcon({ name }: { name: string }) {
  if (name.includes("docker") || name.includes("replay")) return <Play className="h-3.5 w-3.5 shrink-0" />;
  if (name.includes("search") || name.includes("scillm")) return <Search className="h-3.5 w-3.5 shrink-0" />;
  if (name.includes("memory") || name.includes("knowledge")) return <Database className="h-3.5 w-3.5 shrink-0" />;
  return <Bot className="h-3.5 w-3.5 shrink-0" />;
}

function ReceiptRow({ receipt }: { receipt: BattleReceiptRef }) {
  return <div className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-black/20 p-2"><div className="flex min-w-0 items-center gap-2 text-sm text-slate-200"><FileJson className="h-4 w-4 shrink-0 text-battle-blue" /><div className="min-w-0"><div className="truncate">{receipt.receipt_id}</div><div className="truncate text-xs text-slate-500">{receipt.receipt_type} · {receipt.summary || "receipt-backed artifact"}</div></div></div><ProofBadge mode={receipt.proof_mode} /></div>;
}

function InfoPanel({ label, value, tone }: { label: string; value: string; tone: string }) {
  return <section className="min-w-0 rounded-lg border border-white/10 bg-white/[.025] p-2.5"><div className="battle-label">{label}</div><div className={`mt-2 break-words font-mono text-xs leading-5 ${tone}`}>{value}</div></section>;
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded border border-white/10 bg-black/20 px-2 py-1"><span className="battle-label mr-1">{label}</span><span className="font-mono">{value}</span></div>;
}

function EmptyState({ label }: { label: string }) {
  return <div className="rounded-xl border border-white/10 bg-white/[.025] p-3 text-sm text-slate-500">{label}</div>;
}

function ProofBadge({ mode }: { mode: ProofMode }) {
  const label = proofLabel(mode);
  const variant = mode === "receipt_backed_fixture" ? "green" : mode === "live" ? "green" : mode === "fixture" ? "blue" : mode === "pending" ? "purple" : "red";
  return <Badge variant={variant} title={label}>{label}</Badge>;
}

function proofLabel(mode: ProofMode) {
  if (mode === "receipt_backed_fixture") return "RECEIPT-BACKED FIXTURE";
  if (mode === "live") return "LIVE PROOF";
  if (mode === "fixture") return "FIXTURE TRACE";
  if (mode === "mocked") return "MOCKED SKILL";
  if (mode === "pending") return "PROOF PENDING";
  return "MISSING PROOF";
}

type AgentPaneSkill = {
  name: string;
  kind: "skill" | "tool" | "unregistered";
  status: "running" | "ok" | "failed" | "mocked" | "pending";
  timestamp?: string;
  summary?: string;
  receipt_id?: string;
  proof_mode: ProofMode;
};

type AgentPaneModel = {
  laneName: string;
  agentId: string;
  turnId: string;
  loopIndex: number;
  phase: string;
  status: string;
  currentAction: string;
  trace: Record<TraceField, string | undefined>;
  stdout: string;
  stderr: string;
  skills: AgentPaneSkill[];
  receipts: BattleReceiptRef[];
  relatedEvents: BattleEvent[];
  turnEvents: BattleEvent[];
  proofMode: ProofMode;
  replay?: BattleReplayRef | null;
};

function buildModel(lane: Lane, events: BattleEvent[]): AgentPaneModel {
  const relatedEvents = events.filter((event) => isRelatedEvent(event, lane));
  const primary = relatedEvents.find((event) => event.event_type === "blue.blocked_red") ?? relatedEvents.find((event) => event.event_type === "judge.verdict") ?? relatedEvents.find((event) => event.turn) ?? relatedEvents[0];
  const proofMode = lane.proofMode ?? primary?.proof_mode ?? "missing";
  const latestTurn = [...relatedEvents].reverse().find((event) => event.turn) ?? primary;
  const traceSource = [...relatedEvents].reverse().find((event) => event.public_trace)?.public_trace;
  const skills = uniqueSkills(relatedEvents.flatMap((event) => event.skills ?? []));
  const receipts = uniqueReceipts([...relatedEvents.flatMap((event) => event.receipts ?? []), ...(lane.receipts ?? []).map((receiptId) => ({ receipt_id: receiptId, receipt_type: "lane_receipt", summary: "Lane receipt reference.", proof_mode: proofMode }))]);
  const replay = lane.replay ?? relatedEvents.find((event) => event.replay)?.replay ?? null;
  return {
    laneName: lane.name,
    agentId: primary?.tau_subagent_id || primary?.actor_id || "receipt-backed-worker",
    turnId: latestTurn?.tau_turn_id || replay?.pair_id || "judge replay",
    loopIndex: latestTurn?.turn?.loop_index ?? 0,
    phase: latestTurn?.turn?.phase || primary?.event_type || "not emitted",
    status: lane.terminal === "blocked" ? "BLOCKED BY BLUE / BLUE_SUCCESS" : "RECEIPT-BACKED LANE",
    currentAction: latestTurn?.turn?.current_action || primary?.summary || "not emitted",
    trace: { observation: traceSource?.observation, hypothesis: traceSource?.hypothesis, action: traceSource?.action, result: traceSource?.result, learned: traceSource?.learned, next_move: traceSource?.next_move },
    stdout: latestNonEmpty([primary?.output?.stdout_excerpt, ...(lane.stdout ?? [])]) || "not emitted",
    stderr: latestNonEmpty([primary?.output?.stderr_excerpt, ...(lane.stderr ?? [])]) || "not emitted",
    skills,
    receipts,
    relatedEvents,
    turnEvents: relatedEvents.filter((event) => event.turn),
    proofMode,
    replay
  };
}

function isRelatedEvent(event: BattleEvent, lane: Lane) {
  return event.actor_id === lane.id || event.red_lane_id === lane.id || event.payload_id === lane.payloadId || event.target_actor_ids?.includes(lane.id) || event.target_actor_ids?.includes(lane.payloadId) || event.parent_id === lane.id || event.team === "judge";
}

function uniqueSkills(skills: AgentPaneSkill[]) {
  const seen = new Set<string>();
  return skills.filter((skill) => {
    const key = `${skill.name}-${skill.receipt_id ?? "no-receipt"}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueReceipts(receipts: BattleReceiptRef[]) {
  const byId = new Map<string, BattleReceiptRef>();
  for (const receipt of receipts) byId.set(`${receipt.receipt_id}-${receipt.receipt_type}-${receipt.pair_id ?? ""}`, receipt);
  return Array.from(byId.values());
}

function latestNonEmpty(values: Array<string | undefined>) {
  return values.filter((value): value is string => Boolean(value && value.trim() && value !== "not emitted")).at(-1);
}
