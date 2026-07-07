import type { LaneEvent } from "./lib/battle-types";
import { phaseLabelText, phaseLabelTitle } from "./lib/marker-labels";
import { mockupAboveTokenClass, mockupBottomPhaseClass } from "./lib/mockup-lane-partition";
import { cn } from "./lib/utils";
import { useBattleTimelineCoords } from "./useBattleTimelineCoords";
import { isBattleDesignView } from "./lib/battle-mockup-lanes";

export function LaneEventLabel({
  event,
  band,
  allottedSeconds,
}: {
  event: LaneEvent;
  band: "top" | "above" | "below";
  allottedSeconds: number;
}) {
  const designView = isBattleDesignView();
  const { leftPxFromLaneX } = useBattleTimelineCoords(allottedSeconds);
  const text = phaseLabelText(event);
  if (!text) return null;

  if (designView) {
    if (band === "above") {
      return (
        <span
          data-battle-marker-label
          data-label-band={band}
          title={phaseLabelTitle(event)}
          className={cn("token labelOnly above", mockupAboveTokenClass(event.kind))}
          style={{ left: leftPxFromLaneX(event.x) }}
        >
          {text}
        </span>
      );
    }

    const bottomTone = band === "below" ? mockupBottomPhaseClass(text) : "";
    return (
      <span
        data-battle-marker-label
        data-label-band={band}
        title={phaseLabelTitle(event)}
        className={cn("phaseLabel", band, bottomTone)}
        style={{ left: leftPxFromLaneX(event.x) }}
      >
        {text}
      </span>
    );
  }

  const legacyBand = band === "top" ? "above" : band;
  return (
    <span
      data-battle-marker-label
      data-label-band={legacyBand}
      title={phaseLabelTitle(event)}
      className={cn(
        "battle-phase-label",
        legacyBand === "above" ? "battle-phase-label-top" : "battle-phase-label-bottom",
        toneClass(event.kind)
      )}
      style={{ left: leftPxFromLaneX(event.x) }}
    >
      {text}
    </span>
  );
}

function toneClass(kind: LaneEvent["kind"]) {
  if (kind === "useful") return "battle-phase-label-yellow";
  if (kind === "payload") return "battle-phase-label-red";
  if (kind === "research") return "battle-phase-label-muted";
  return "battle-phase-label-muted";
}
