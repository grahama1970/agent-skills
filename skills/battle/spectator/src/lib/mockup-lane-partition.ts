import type { Lane, LaneEvent } from "./battle-types";
import { isIconEvent } from "./layout-lane-events";

export type MockupLaneBands = {
  top: LaneEvent[];
  above: LaneEvent[];
  icons: LaneEvent[];
  bottom: LaneEvent[];
};

export function partitionMockupLaneEvents(lane: Lane): MockupLaneBands {
  const top: LaneEvent[] = [];
  const above: LaneEvent[] = [];
  const icons: LaneEvent[] = [];
  const bottom: LaneEvent[] = [];

  for (const event of lane.events) {
    if (event.id.includes(":top:")) {
      top.push(event);
      continue;
    }
    if (event.id.includes(":bottom:")) {
      bottom.push(event);
      continue;
    }
    if (event.id.includes(":above:")) {
      above.push(event);
      continue;
    }
    if (event.id.includes(":icon:") || isIconEvent(event)) {
      icons.push(event);
      continue;
    }
  }

  return { top, above, icons, bottom };
}

export function mockupBottomPhaseClass(label: string): string {
  const token = label.toUpperCase();
  if (token.includes("BLOCK") || token.includes("PATCH") || token.includes("GATE") || token.includes("BLUE")) return "blue";
  if (token.includes("PROMOT") || token.includes("CRASH")) return "green";
  if (token.includes("SPAWN") || token.includes("RECEIPT")) return "yellow";
  return "";
}

export function mockupAboveTokenClass(kind: LaneEvent["kind"]): string {
  if (kind === "handoff") return "tokGreen";
  return "tokYellow";
}

export function mockupMarkerClasses(event: LaneEvent): string {
  const terminal = isIconEvent(event);
  const big = event.kind === "fastest_crash" || event.kind === "promoted";
  const tone =
    event.kind === "useful"
      ? "tokYellow"
      : event.kind === "blocked" || event.kind === "blue_blast" || event.kind === "detected"
        ? "tokBlue"
        : event.kind === "killed"
          ? "tokRed"
          : event.kind === "fastest_crash" || event.kind === "promoted"
            ? "tokGreen"
            : event.kind === "handoff"
              ? "tokPurple"
              : "tokYellow";

  return ["markerIcon", tone, terminal ? "terminal" : "", big ? "big" : ""].filter(Boolean).join(" ");
}
