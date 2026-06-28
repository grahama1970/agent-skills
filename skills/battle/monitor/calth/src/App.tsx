import { useEffect, useState } from "react";
import {
  Activity,
  Crosshair,
  FileJson,
  LoaderCircle,
  Scale,
  Shield,
  Swords,
  TerminalSquare,
  TriangleAlert
} from "lucide-react";

import { loadCalthArtifacts, type LoadedCalthArtifacts } from "./artifacts";
import { BattleChatSidebar } from "./BattleChatSidebar";
import type { CalthPlayer, CalthTimelineStage } from "./types";

type LoadState =
  | { status: "loading" }
  | { status: "loaded"; data: LoadedCalthArtifacts }
  | { status: "blocked"; error: string };

function statusClass(status: string): string {
  const normalized = status.toLowerCase();
  if (["pass", "blue_success"].includes(normalized)) return "statusPass";
  if (["fail", "red_success", "fake_defense"].includes(normalized)) return "statusFail";
  if (["blocked", "insufficient_evidence"].includes(normalized)) return "statusWarn";
  return "statusNeutral";
}

function TeamIcon({ team }: { team: CalthPlayer["team"] }) {
  if (team === "red") return <Swords size={18} />;
  if (team === "blue") return <Shield size={18} />;
  return <Scale size={18} />;
}

function PlayerCard({ player }: { player: CalthPlayer }) {
  return (
    <article className={`card playerCard ${player.team}`}>
      <div className="cardHeader">
        <div className="iconBadge">
          <TeamIcon team={player.team} />
        </div>
        <div>
          <div className="eyebrow">{player.team}</div>
          <h3>{player.persona}</h3>
        </div>
      </div>

      <dl className="kv">
        <div>
          <dt>Role</dt>
          <dd>{player.role}</dd>
        </div>
        <div>
          <dt>Receipt</dt>
          <dd className="mono">{player.receipt}</dd>
        </div>
      </dl>
    </article>
  );
}

function TimelineNode({ item }: { item: CalthTimelineStage }) {
  return (
    <div className="timelineNode">
      <div className={`timelineDot ${statusClass(item.status)}`} />
      <div className="timelineText">
        <span className="eyebrow">{item.stage}</span>
        <strong className={statusClass(item.status)}>{item.status}</strong>
      </div>
    </div>
  );
}

function ScoreCard({ data }: { data: LoadedCalthArtifacts }) {
  const { scoreboard } = data;

  return (
    <section className="card">
      <div className="cardHeader">
        <div className="iconBadge">
          <Activity size={18} />
        </div>
        <div>
          <div className="eyebrow">Scoreboard</div>
          <h2>Judge-derived result</h2>
        </div>
      </div>

      <div className="scoreGrid">
        <div>
          <span className="eyebrow">Red</span>
          <strong className="redText">{scoreboard.red_score.toFixed(1)}</strong>
        </div>
        <div>
          <span className="eyebrow">Blue</span>
          <strong className="blueText">{scoreboard.blue_score.toFixed(1)}</strong>
        </div>
        <div>
          <span className="eyebrow">TDSR</span>
          <strong>{Math.round(scoreboard.tdsr * 100)}%</strong>
        </div>
        <div>
          <span className="eyebrow">FDSR</span>
          <strong>{Math.round(scoreboard.fdsr * 100)}%</strong>
        </div>
        <div>
          <span className="eyebrow">ASC</span>
          <strong>{scoreboard.asc}</strong>
        </div>
      </div>

      <div className="verdictRow">
        <span>Verdict</span>
        <strong className={statusClass(scoreboard.verdict)}>{scoreboard.verdict}</strong>
      </div>
    </section>
  );
}

function EvidencePanel({ data }: { data: LoadedCalthArtifacts }) {
  return (
    <section className="card">
      <div className="cardHeader">
        <div className="iconBadge">
          <FileJson size={18} />
        </div>
        <div>
          <div className="eyebrow">Evidence</div>
          <h2>Receipt-backed artifacts</h2>
        </div>
      </div>

      <div className="sourceLine">
        <span>Source</span>
        <strong className="mono">{data.baseUrl}</strong>
      </div>

      <ul className="artifactList">
        {data.monitorIndex.artifacts.map((artifact) => (
          <li key={artifact}>
            <TerminalSquare size={14} />
            <span className="mono">{artifact}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function LoadingView() {
  return (
    <main className="centerShell">
      <section className="statePanel">
        <LoaderCircle size={28} className="spin" />
        <div>
          <div className="eyebrow">Battle Monitor</div>
          <h1>Loading generated artifacts</h1>
        </div>
      </section>
    </main>
  );
}

function BlockedView({ error }: { error: string }) {
  return (
    <main className="centerShell">
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

function LoadedView({ data }: { data: LoadedCalthArtifacts }) {
  const { monitorIndex } = data;

  return (
    <main className="monitorShell">
      <div className="appShell">
        <header className="hero">
          <div>
            <div className="eyebrow">Battle Monitor</div>
            <h1>{monitorIndex.title}</h1>
            <p>
              One-round Red to Blue to scorekeeper battle. The scoreboard is derived from
              scorekeeper receipts, not Blue self-certification.
            </p>
          </div>

          <div className="heroStatus">
            <Crosshair size={22} />
            <span className="eyebrow">Battle</span>
            <strong className="mono">{monitorIndex.battle_id}</strong>
            <strong className={statusClass(monitorIndex.status)}>{monitorIndex.status}</strong>
          </div>
        </header>

        <section className="summaryGrid">
          <article className="card">
            <div className="eyebrow">Campaign</div>
            <h2>{monitorIndex.campaign}</h2>
            <p className="muted">Scenario: {monitorIndex.scenario}</p>
          </article>

          <article className="card">
            <div className="eyebrow">Final verdict</div>
            <h2 className={statusClass(monitorIndex.verdict)}>{monitorIndex.verdict}</h2>
            <p className="muted">Exploit confirmed, patch applied, scorekeeper verified.</p>
          </article>
        </section>

        <section className="playersGrid">
          {monitorIndex.players.map((player) => (
            <PlayerCard key={`${player.team}-${player.persona}`} player={player} />
          ))}
        </section>

        <section className="card timelineCard">
          <div className="cardHeader">
            <div className="iconBadge">
              <Activity size={18} />
            </div>
            <div>
              <div className="eyebrow">Round timeline</div>
              <h2>Prepare to Red to Blue to Scorekeeper to Score</h2>
            </div>
          </div>

          <div className="timeline">
            {monitorIndex.timeline.map((item) => (
              <TimelineNode key={item.stage} item={item} />
            ))}
          </div>
        </section>

        <section className="lowerGrid">
          <ScoreCard data={data} />
          <EvidencePanel data={data} />
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

    loadCalthArtifacts()
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
