import { type ComponentType } from "react";
import { motion } from "motion/react";
import type { LaneEvent } from "./lib/battle-types";
import { formatMarkerTooltip } from "./lib/marker-labels";
import { mockupMarkerClasses } from "./lib/mockup-lane-partition";
import { cn } from "./lib/utils";
import { useBattleTimelineCoords } from "./useBattleTimelineCoords";
import { Icons } from "./battle-icons";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";

const eventIcon: Partial<Record<LaneEvent["kind"], ComponentType<{ className?: string }>>> = {
  research: Icons.Search,
  payload: Icons.Code2,
  useful: Icons.Lightbulb,
  stderr: Icons.Terminal,
  self_heal: Icons.Wrench,
  mutate: Icons.Dna,
  retry: Icons.RefreshCw,
  detected: Icons.Radar,
  blue_blast: Icons.ShieldX,
  handoff: Icons.GitBranch,
  killed: Icons.Skull,
  blocked: Icons.ShieldX,
  promoted: Icons.ShieldCheck,
  fastest_crash: Icons.Rocket,
  research_started: Icons.Search,
  research_receipt_materialized: Icons.FileJson,
  genome_selected: Icons.Dna,
  method_added: Icons.GitBranch,
  method_rejected: Icons.ShieldX,
  code_author_started: Icons.Code2,
  specimen_materialized: Icons.Code2,
  compile_failed: Icons.Terminal,
  repair_started: Icons.Wrench,
  repair_materialized: Icons.Wrench,
  compile_passed: Icons.ShieldCheck,
  target_contact_unproven: Icons.Radar,
  judge_pending: Icons.Shield,
  judge_exploit_success: Icons.Rocket,
  genome_promoted: Icons.ShieldCheck,
  branch_abandoned: Icons.ShieldX,
};

export function LaneEventMarker({
  event,
  laneId,
  laneName,
  index,
  allottedSeconds,
  onSelect,
}: {
  event: LaneEvent;
  laneId: string;
  laneName: string;
  index: number;
  allottedSeconds: number;
  onSelect: (id: string) => void;
}) {
  const designView = isBattleDesignView();
  const { leftPxFromLaneX } = useBattleTimelineCoords(allottedSeconds);
  const Icon = eventIcon[event.kind] ?? Icons.Lightbulb;
  const hero = isHeroMarker(event.kind);
  const tooltip = formatMarkerTooltip(event);
  const left = leftPxFromLaneX(event.x);

  if (designView) {
    return (
      <button
        type="button"
        data-qid={`battle:marker:${laneId}:${event.kind}`}
        data-qs-action="BATTLE_MARKER_SELECT"
        data-battle-marker-icon
        title={`${laneName}: ${tooltip}`}
        aria-label={`${laneName}: ${tooltip}`}
        className={cn(mockupMarkerClasses(event), "min-h-11 min-w-11 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40")}
        style={{ left }}
        onClick={(clickEvent) => {
          clickEvent.stopPropagation();
          onSelect(laneId);
        }}
      >
        <Icon className={cn(hero ? "h-4 w-4" : "h-3.5 w-3.5")} />
      </button>
    );
  }

  return (
    <div className="absolute top-1/2 z-20 -translate-x-1/2 -translate-y-1/2" style={{ left }}>
      {event.kind === "blue_blast" ? (
        <span className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 rounded-full border border-battle-blue/50 bg-battle-blue/15 animate-blueBlast" />
      ) : null}

      <motion.button
        type="button"
        data-qid={`battle:marker:${laneId}:${event.kind}`}
        data-qs-action="BATTLE_MARKER_SELECT"
        title={`${laneName}: ${tooltip}`}
        aria-label={`${laneName}: ${tooltip}`}
        onClick={(clickEvent) => {
          clickEvent.stopPropagation();
          onSelect(laneId);
        }}
        initial={false}
        animate={hero ? { scale: [1, 1.08, 1] } : undefined}
        transition={hero ? { duration: 1.2, repeat: Infinity } : undefined}
        data-battle-marker-icon
        className="relative grid h-11 min-h-11 w-11 min-w-11 place-items-center rounded-full bg-transparent transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-battle-cyan/40"
      >
        <span
          aria-hidden="true"
          className={cn(
            "grid place-items-center rounded-full border bg-battle-panel2 shadow-acrylic",
            hero ? "h-10 w-10" : "h-8 w-8",
            markerColor(event.kind)
          )}
        >
          <Icon className={hero ? "h-5 w-5" : "h-4 w-4"} />
        </span>
      </motion.button>
    </div>
  );
}

function isHeroMarker(kind: LaneEvent["kind"]) {
  return kind === "blue_blast" || kind === "blocked" || kind === "detected" || kind === "useful";
}

function markerColor(kind: LaneEvent["kind"]) {
  switch (kind) {
    case "useful":
      return "border-battle-yellow/70 text-battle-yellow shadow-yellowGlow";
    case "detected":
    case "blue_blast":
    case "blocked":
      return "border-battle-blue/80 text-battle-blue shadow-blueGlow";
    case "handoff":
      return "border-battle-purple/70 text-battle-purple shadow-purpleGlow";
    case "killed":
      return "border-battle-red/80 text-battle-red shadow-redGlow";
    case "promoted":
    case "fastest_crash":
      return "border-battle-green/80 text-battle-green shadow-greenGlow";
    case "mutate":
      return "border-battle-purple/60 text-battle-purple";
    case "self_heal":
    case "retry":
      return "border-battle-yellow/50 text-battle-yellow";
    default:
      return "border-white/20 text-slate-300";
  }
}
