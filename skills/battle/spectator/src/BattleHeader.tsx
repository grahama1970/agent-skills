import { cn } from "./lib/utils";
import { formatReceiptScore } from "./lib/format-receipt-score";
import { Button } from "./ui/button";
import type { BattleEvent } from "./lib/battle-types";
import { activeBattleFixture } from "./lib/battle-data";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";
import {
  mockupArenaLabel,
  mockupDifficultyLabel,
  mockupHeaderClock,
  mockupLiveEvents,
  mockupScoreboard,
} from "./lib/mockup-design-fixture";
import { Icons } from "./battle-icons";
// Retro angular scorecard (accepted design) embedded verbatim in an isolated iframe.
import scorecardHtml from "./battle-scorecard.html?raw";
import { useRegisterAction } from "./hooks/useRegisterAction";
import { BattleHungerGamesDeathAnnouncement } from "./BattleHungerGamesDeathAnnouncement";
import type { HungerGamesDeathCard } from "./lib/battle-hunger-games-notifications";

type Props = {
  receiptFixture?: import("./lib/battle-types").BattleNormalizedUxFixture | null;
  events: BattleEvent[];
  onTestSound: (cue: string) => void;
  onSelectActor: (id: string) => void;
  onOpenJsonl: () => void;
  deathAnnouncement?: HungerGamesDeathCard | null;
  onDismissDeathAnnouncement?: () => void;
};

export function BattleHeader({ receiptFixture, events, onSelectActor, onOpenJsonl, deathAnnouncement = null, onDismissDeathAnnouncement }: Props) {
  useRegisterAction("battle:events:rail", { action: "BATTLE_EVENTS_OPEN", label: "Open Battle Receipt Events", description: "Open the receipt-backed Battle event stream popover", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:events:item", { action: "BATTLE_EVENT_SELECT", label: "Select Battle Event Actor", description: "Select the lane associated with a receipt-backed Battle event", tags: ["battle", "receipt-backed"] });
  useRegisterAction("battle:events:view-all", { action: "BATTLE_EVENTS_VIEW_ALL", label: "View All Battle Receipts", description: "Open the full receipt-backed Battle event list", tags: ["battle", "receipt-backed"] });

  const designView = isBattleDesignView();
  const fixture = activeBattleFixture(receiptFixture);
  const scenario = fixture.scenario;
  const scoreboard = fixture.scoreboard;
  const clock = fixture.battle_clock;
  const endpoint = scenario?.public_entrypoint ?? "/api/import-zip";
  const cwe = scenario?.cwe ?? "CWE-22";
  const family = scenario?.hidden_vulnerability_family ?? "Zip Slip path traversal";
  const battleTitle = fixture.spectator_shell?.battle_title ?? `${fixture.battle_id?.toUpperCase() ?? "BATTLE-004"} · POST ${endpoint}`;
  const arenaLabel = designView ? mockupArenaLabel() : "ZIP_SLIP_ARB";
  const difficultyLabel = designView ? mockupDifficultyLabel() : "JUDGE";
  const adaptiveQualification = fixture.adaptive_lineage?.qualification.status;
  const objectiveLabel = adaptiveQualification
    ? `QUALIFICATION: Adaptive Lineage ${adaptiveQualification}`
    : "TARGET: Fastest Proven Crash";
  // Numeric scores per the accepted mockup (RED 8.4 / BLUE 7.2). Render only when the
  // receipt scoreboard is populated; hide gracefully (clean nameplate, no "—") when null.
  const redScore =
    typeof scoreboard?.red_score === "number" && Number.isFinite(scoreboard.red_score)
      ? formatReceiptScore(scoreboard.red_score)
      : null;
  const blueScore =
    typeof scoreboard?.blue_score === "number" && Number.isFinite(scoreboard.blue_score)
      ? formatReceiptScore(scoreboard.blue_score)
      : null;

  // Embed the accepted adaptive-lineage scorecard verbatim, binding its score data
  // attributes to real receipt data (em dash when the fixture carries no numeric
  // score — never faked; the embedded script syncs the SVG text from these).
  const scorecardDoc = scorecardHtml
    .replace('data-red-score="8.4"', `data-red-score="${redScore ?? "—"}"`)
    .replace('data-blue-score="7.2"', `data-blue-score="${blueScore ?? "—"}"`);

  function selectEvent(event: BattleEvent) {
    const candidate =
      event.actor_id.startsWith("payload")
        ? event.actor_id
        : event.red_lane_id ?? event.payload_id ?? event.target_actor_ids?.find((id) => id.startsWith("payload"));
    if (candidate) onSelectActor(candidate);
  }

  if (designView) {
    return (
      <header className="topbar">
        <div className="headerBlock">
          <div className="title">
            <h1>BATTLE-004 · POST {endpoint}</h1>
            <p>
              {cwe} Zip Slip <span className="dim">·</span> autonomous exploit agents evolve under pressure <span className="dim">·</span> fastest proven crash wins
            </p>
          </div>
          <div className="metaInline">
            <span><b>Arena</b> {arenaLabel}</span>
            <span><b>Objective</b> Prevent archive path traversal</span>
            <span><b>Target</b> POST {endpoint}</span>
            <span><b>Difficulty</b> {difficultyLabel}</span>
            <span className="roundClock"><b>Round Time</b> {mockupHeaderClock().elapsed} / {mockupHeaderClock().allotted}</span>
          </div>
        </div>

        <div className="score battle-score-block">
          <div className="scoreSide red" data-testid="score-red">
            <div className="scoreLabel">RED TEAM</div>
            <div className="scoreValueRow">
              <div className="scoreIcon"><Icons.Bug aria-hidden="true" /></div>
              <div className="scoreNum">{mockupScoreboard().red}</div>
            </div>
          </div>
          <div className="vs">VS</div>
          <div className="scoreSide blue">
            <div className="scoreLabel">BLUE TEAM</div>
            <div className="scoreValueRow">
              <div className="scoreNum">{mockupScoreboard().blue}</div>
              <div className="scoreIcon"><Icons.Shield aria-hidden="true" /></div>
            </div>
          </div>
        </div>

        <div className="liveEvents battle-live-events">
          <div className="liveEventsHead"><span className="dot red" aria-hidden="true" /> LIVE EVENTS</div>
          {mockupLiveEvents.map((event) => (
            <button
              key={event.id}
              type="button"
              data-qid={`battle:events:item:${event.id}`}
              data-qs-action="BATTLE_EVENT_SELECT"
              title={`Select live event ${event.highlight}`}
              className="liveEventRow battle-live-event-row w-full text-left transition-colors hover:bg-white/[.03] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
              onClick={() => event.laneId && onSelectActor(event.laneId)}
            >
              <span className="leTime">{event.time}</span>
              <span className="leIconSlot" style={{ color: event.iconTone === "green" ? "#3cf07a" : event.iconTone === "blue" ? "#5aadff" : "#ff4d5c" }}>
                <MockLiveIcon icon={event.icon} />
              </span>
              <span className="leText">
                {event.prefix}
                <b className={event.highlightTone}>{event.highlight}</b>
              </span>
            </button>
          ))}
        </div>
      </header>
    );
  }

  return (
    <header className="battle-receipt-header relative min-h-0 overflow-hidden border-b border-white/10 bg-[#0d1117] px-4 py-2" data-qid="battle:header:receipt">
      <div className="battle-title-group flex min-w-0 flex-col gap-3 self-stretch">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="shrink-0 rounded-lg border border-battle-red/30 bg-battle-red/10 p-1.5 text-battle-red shadow-redGlow">
            <Icons.Swords className="h-4 w-4" />
          </div>
          <div className="battle-headers min-w-0">
            <h1 className="battle-title">
              <span className="battle-id">{(fixture.battle_id ?? "battle-004").toUpperCase()}</span>
              <span className="divider">/</span>
              <span className="battle-target">{`POST ${endpoint}`}</span>
            </h1>
            <h2 className="battle-subtitle">
              <span className="data-point highlight">{cwe}</span>
              <span className="divider">/</span>
              <span className="data-point">{family}</span>
              <span className="divider">/</span>
              <span className="data-point objective">{objectiveLabel}</span>
            </h2>
          </div>
        </div>
      </div>

      <iframe
        className="battle-scorecard-frame pointer-events-none"
        data-qid="battle:header:score"
        title="Red Team versus Blue Team scorecard"
        scrolling="no"
        srcDoc={scorecardDoc}
      />

      {/* RIGHT — left-aligned terminal event ticker (container hugs right, text reads L→R) */}
      <div className="battle-column-right">
        <div className="live-events-head">
          <span className="live-dot" aria-hidden="true" /> LIVE EVENTS
          <Button data-qid="battle:events:view-all" data-qs-action="BATTLE_EVENTS_VIEW_ALL" variant="ghost" size="icon" className="ml-auto h-6 w-6 shrink-0" title="View all receipt-backed events" onClick={onOpenJsonl}>
            <Icons.FileJson className="h-3.5 w-3.5" />
          </Button>
        </div>
        <BattleHungerGamesDeathAnnouncement card={deathAnnouncement} onDismiss={onDismissDeathAnnouncement ?? (() => undefined)} />
        <div className="live-events-feed">
          {events.slice(-3).map((event, index) => (
            <button key={`${event.id}:${index}`} type="button" data-qid={`battle:events:item:${event.id}`} data-qs-action="BATTLE_EVENT_SELECT" title={`Select receipt event ${event.id}`} onClick={() => selectEvent(event)} className="event-row">
              <span className="event-time">{new Date(event.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}</span>
              <span className="event-icon" aria-hidden="true">
                <span className={`status-led led-${event.team === "red" ? "red" : event.team === "blue" ? "blue" : "neutral"}`} />
              </span>
              <span className={`event-msg type-${eventLevel(event)}`}><ReceiptLiveEventText event={event} /></span>
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

function Fact({ label, value, title, tone }: { label: string; value: string; title?: string; tone?: "highlight" | "time" }) {
  const toneClass = tone === "highlight" ? " highlight-tag" : tone === "time" ? " time-tag" : "";
  return (
    <span className={`battle-tag${toneClass}`} title={title ?? `${label}: ${value}`}>{value}</span>
  );
}

function eventLevel(event: BattleEvent): "info" | "warn" | "critical" {
  const t = event.event_type;
  if (t === "replay.killed" || t === "judge.verdict") return "critical";
  if (event.team === "blue" || (typeof t === "string" && t.startsWith("blue"))) return "info";
  if (event.team === "red") return "warn";
  return "info";
}

function EventIcon({ event }: { event: BattleEvent }) {
  if (event.event_type === "replay.killed") return <Icons.Skull className="h-4 w-4 text-battle-red" />;
  if (event.event_type === "replay.blocked") return <Icons.ShieldCheck className="h-4 w-4 text-battle-green" />;
  if (event.event_type === "replay.blue_blast") return <Icons.Crosshair className="h-4 w-4 text-battle-blue" />;
  if (event.event_type === "judge.verdict") return <Icons.ShieldCheck className="h-4 w-4 text-battle-green" />;
  if (event.event_type === "blue.blocked_red") return <Icons.ShieldX className="h-4 w-4 text-battle-blue" />;
  if (event.event_type === "blue.patch_deployed") return <Icons.Shield className="h-4 w-4 text-battle-blue" />;
  if (event.team === "red") return <Icons.Bug className="h-4 w-4 text-battle-red" />;
  if (event.event_type === "tau.handoff_created") return <Icons.GitBranch className="h-4 w-4 text-battle-purple" />;
  return <Icons.Activity className="h-4 w-4 text-battle-yellow" />;
}

function ReceiptLiveEventText({ event }: { event: BattleEvent }) {
  const prefix = event.ui.notification_prefix;
  const highlight = event.ui.notification_highlight;
  const tone = event.ui.notification_highlight_tone ?? (event.team === "blue" ? "blue" : event.team === "red" ? "red" : "green");
  if (prefix && highlight) {
    return (
      <span className="min-w-0 truncate">
        {prefix}
        <b className={tone}>{highlight}</b>
      </span>
    );
  }
  return <span className="min-w-0 truncate">{event.ui.notification ?? event.summary}</span>;
}


function MockLiveIcon({ icon }: { icon: "rocket" | "shield" | "shield-check" | "bug" }) {
  if (icon === "rocket") return <Icons.Rocket className="leIconSvg" />;
  if (icon === "shield-check") return <Icons.ShieldCheck className="leIconSvg" />;
  if (icon === "shield") return <Icons.Shield className="leIconSvg" />;
  return <Icons.Bug className="leIconSvg" />;
}

function formatSeconds(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--:--";
  const total = Math.max(0, Math.floor(value));
  const min = Math.floor(total / 60).toString().padStart(2, "0");
  const sec = (total % 60).toString().padStart(2, "0");
  return `${min}:${sec}`;
}
