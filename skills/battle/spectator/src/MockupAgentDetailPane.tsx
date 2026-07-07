import { Icons } from "./battle-icons";
import type { Lane } from "./lib/battle-types";
import { mockupAgentDetail } from "./lib/mockup-design-fixture";
import { useRegisterAction } from "./hooks/useRegisterAction";

type Props = { lane: Lane };

export function MockupAgentDetailPane({ lane }: Props) {
  useRegisterAction("battle:agent-pane:close", { action: "BATTLE_AGENT_PANE_CLOSE", label: "Close Battle Agent Pane", description: "Close the Battle agent detail pane.", tags: ["battle", "design"] });
  useRegisterAction("battle:agent-pane:docker-replay", { action: "BATTLE_AGENT_PANE_DOCKER_REPLAY", label: "Open Docker Replay", description: "Open Docker replay for the selected Battle lane.", tags: ["battle", "design"] });
  const detail = mockupAgentDetail(lane);
  const cockpit = lane.cockpit;
  const replay = lane.replay;
  const statusLabel = cockpit?.current_turn?.status?.toUpperCase() ?? detail.status;
  const loopStage = cockpit?.current_turn?.phase?.toUpperCase() ?? detail.loop.stage;
  const mutation = cockpit?.public_trace?.learned ?? lane.mutationRationale ?? detail.mutation;
  const receiptId = cockpit?.latest_receipt_id ?? detail.receipt.id;
  const receiptStatus = cockpit?.blue_outcome?.status?.toUpperCase() ?? detail.receipt.status;
  const showCrashBadge = lane.terminal === "fastest_crash" || detail.badge === "FASTEST CRASH";
  const showDocker = Boolean(replay?.cta?.visible ?? replay);

  return (
    <aside className="battle-mockup-agent-pane battle-mockup-panel right" data-qid={`battle:agent-pane:${lane.id}`} data-qs-action="BATTLE_LANE_SELECT" title={`Agent detail for ${lane.name}`}>
      <div className="detailHead">
        <div className="paneLabel">Agent Detail</div>
        <button type="button" className="detailClose min-h-11 min-w-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40" data-qid="battle:agent-pane:close" data-qs-action="BATTLE_AGENT_PANE_CLOSE" title="Close agent detail pane" aria-label="Close agent detail">×</button>
      </div>

      <div className="agentTitleRow">
        <div className="agentBug">
          <Icons.Bug className="h-4 w-4" />
        </div>
        <div>
          <h2 className="agentName">{lane.name}</h2>
          <div className="agentMeta">Gen {lane.generation}</div>
        </div>
      </div>

      <div className="agentPayload">{lane.payloadId}</div>

      <div className="agentHeroBadges">
        {showCrashBadge ? <span className="statusPill">{detail.badge}</span> : null}
      </div>

      {showDocker ? (
        <button type="button" className="dockerReplay dockerReplayTop min-h-11 w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40" data-qid={`battle:agent-pane:docker-replay:${lane.id}`} data-qs-action="BATTLE_AGENT_PANE_DOCKER_REPLAY" title="Open Docker replay for this Battle lane">
          <Icons.Box className="dockerReplayIcon" aria-hidden="true" />
          REPLAY IN DOCKER · Reproduce this run locally
        </button>
      ) : null}

      <div className="detailBody detailScroll">
        <div className="field">
          <label>Status</label>
          <div className="statusPill">
            <span className="dot" aria-hidden="true" />
            {statusLabel} · {detail.statusClock}
          </div>
        </div>

        <div className="field">
          <label>Current Loop</label>
          <div className="loopGrid">
            <div>
              <small>Stage</small>
              <strong>{loopStage}</strong>
            </div>
            <div>
              <small>Attempts</small>
              <strong>{detail.loop.attempts}</strong>
            </div>
            <div>
              <small>Last Update</small>
              <strong>{detail.loop.lastUpdate}</strong>
            </div>
          </div>
        </div>

        <div className="field">
          <label>Inherited Context</label>
          <div className="kvGrid">
            <div>
              <b>Parent</b>
              <span>{detail.inherited.parent}</span>
            </div>
            <div>
              <b>Handoff Reason</b>
              <span>{detail.inherited.handoff}</span>
            </div>
            <div>
              <b>Inherited At</b>
              <span>{detail.inherited.inheritedAt}</span>
            </div>
          </div>
        </div>

        <div className="field">
          <label>Mutation Rationale</label>
          <div className="mutBox">{mutation}</div>
        </div>

        <div className="field">
          <label>Latest Receipt</label>
          <div className="receiptBlock">
            <span className="copy" aria-hidden="true">⧉</span>
            {`${receiptId}\nStatus: ${receiptStatus}\nCrash: ${detail.receipt.crash}\nTime: ${detail.receipt.time}`}
          </div>
        </div>
      </div>
    </aside>
  );
}
