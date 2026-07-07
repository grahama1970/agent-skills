import type { Lane } from "./battle-types";

export const MOCKUP_CLOCK_START_MINUTES = 10 * 60 + 4;
export const MOCKUP_CLOCK_SPAN_MINUTES = 10;

/** HTML mockup fmtClock(t) — wall clock from mockup T (0–30). */
export function mockupFmtClock(t: number, tMax = 30) {
  const wallSec = (t / tMax) * 12;
  const total = 4 + wallSec;
  const min = 10 + Math.floor(total / 60);
  const sec = total % 60;
  const whole = Math.floor(sec);
  const frac = Math.round((sec - whole) * 100);
  const base = `${min}:${whole.toString().padStart(2, "0")}`;
  return frac ? `${base}.${frac.toString().padStart(2, "0")}` : base;
}

export function mockupClockFromTrackPct(trackPct: number) {
  const elapsed = (trackPct / 100) * MOCKUP_CLOCK_SPAN_MINUTES;
  const totalMinutes = MOCKUP_CLOCK_START_MINUTES + elapsed;
  const hour = Math.floor(totalMinutes / 60);
  const minute = Math.floor(totalMinutes % 60);
  return `${hour}:${minute.toString().padStart(2, "0")}`;
}

export function mockupClockFromMockupT(t: number, tMax = 30) {
  return mockupClockFromTrackPct((t / tMax) * 100);
}

export function mockupAllottedSeconds() {
  return MOCKUP_CLOCK_SPAN_MINUTES * 60;
}

export function mockupPlayheadSeconds() {
  return mockupAllottedSeconds();
}

export function mockupTimelineTicks() {
  return [0, 20, 40, 60, 80, 100].map((x) => ({ x, label: mockupClockFromTrackPct(x) }));
}

export function mockupDefaultSelectedLaneId() {
  return "payload-857-A";
}


export function mockupBlueStripStats() {
  return { interventions: 4, blocks: 2 };
}

export function mockupArenaLabel() {
  return "ZIP_SLIP_LAB";
}

export function mockupDifficultyLabel() {
  return "HIGH";
}

export function mockupHeaderClock() {
  return { elapsed: "10:14", allotted: "20:00" };
}

export function mockupScoreboard() {
  return { red: "8.4", blue: "7.2" };
}

export type MockupLeaderboardEntry = {
  rank: number;
  laneId: string;
  name: string;
  generation: number;
  time: string;
  status: "fastest_crash" | "promoted" | "blocked";
};

export const mockupRaceLeaders: MockupLeaderboardEntry[] = [
  { rank: 1, laneId: "payload-857-A", name: "Replay Fork", generation: 2, time: "10:14.32", status: "fastest_crash" },
  { rank: 2, laneId: "payload-912-D", name: "Boundary Fray D", generation: 2, time: "10:12.18", status: "promoted" },
  { rank: 3, laneId: "payload-912-B", name: "Boundary Fray B", generation: 2, time: "10:11.02", status: "blocked" },
];

export const mockupAgentStatus = [
  { label: "Running", value: 7, tone: "blue" as const },
  { label: "Blocked", value: 5, tone: "blue" as const },
  { label: "Killed", value: 3, tone: "red" as const },
  { label: "Useful", value: 2, tone: "yellow" as const },
  { label: "Promoted", value: 1, tone: "green" as const },
  { label: "Fastest crash", value: 1, tone: "green" as const },
];

export type MockupLiveEvent = {
  id: string;
  laneId?: string;
  time: string;
  icon: "rocket" | "shield" | "shield-check" | "bug";
  iconTone: "green" | "blue" | "red" | "purple";
  prefix: string;
  highlight: string;
  highlightTone: "green" | "blue" | "red";
};

export const mockupLiveEvents: MockupLiveEvent[] = [
  {
    id: "mock-live-1",
    laneId: "payload-857-A",
    time: "10:14:32",
    icon: "rocket",
    iconTone: "green",
    prefix: "Replay Fork reaches ",
    highlight: "FASTEST CRASH",
    highlightTone: "green",
  },
  {
    id: "mock-live-2",
    laneId: "payload-912-D",
    time: "10:14:18",
    icon: "shield",
    iconTone: "green",
    prefix: "Boundary Fray D promoted to ",
    highlight: "SURVIVOR",
    highlightTone: "green",
  },
  {
    id: "mock-live-3",
    time: "10:13:55",
    icon: "shield",
    iconTone: "blue",
    prefix: "Blue deployed ",
    highlight: "CanonGuard patch",
    highlightTone: "blue",
  },
];

type MockupAgentDetail = {
  badge: string;
  status: string;
  statusClock: string;
  loop: { stage: string; attempts: string; lastUpdate: string };
  inherited: { parent: string; handoff: string; inheritedAt: string };
  mutation: string;
  receipt: { id: string; status: string; crash: string; time: string };
};

const MOCKUP_AGENT_DETAILS: Record<string, MockupAgentDetail> = {
  "payload-857-A": {
    badge: "FASTEST CRASH",
    status: "RUNNING",
    statusClock: mockupFmtClock(23.1),
    loop: { stage: "TRIGGER", attempts: "1", lastUpdate: mockupFmtClock(23.1) },
    inherited: { parent: "Archive Escape (Gen 1)", handoff: "ZIP_SLIP_CONFIRMED", inheritedAt: mockupFmtClock(21) },
    mutation:
      "Trimmed path normalization bypass inherited from Archive Escape after ZIP_SLIP_CONFIRMED handoff.",
    receipt: {
      id: "payload-857-A-replay",
      status: "FASTEST_CRASH_CONFIRMED",
      crash: "SIGSEGV @ validate_path()",
      time: `${mockupFmtClock(23.1)}.118`,
    },
  },
};

export function mockupAgentDetail(lane: Lane): MockupAgentDetail {
  return (
    MOCKUP_AGENT_DETAILS[lane.id] ?? {
      badge: (lane.terminal ?? lane.runnerState ?? "ACTIVE").replace(/_/g, " ").toUpperCase(),
      status: "RUNNING",
      statusClock: "10:14:32",
      loop: { stage: "OBSERVE", attempts: "1", lastUpdate: "10:14:32" },
      inherited: {
        parent: lane.parentId ? `${lane.parentId} (parent)` : "Root lane",
        handoff: lane.inheritedContext?.[0] ?? "HANDOFF",
        inheritedAt: mockupClockFromTrackPct(lane.xStart ?? 0) + ":18",
      },
      mutation: lane.mutationRationale ?? "Receipt-backed mutation rationale not emitted for this lane.",
      receipt: {
        id: `${lane.id}-replay`,
        status: (lane.terminal ?? "ACTIVE").replace(/_/g, " ").toUpperCase(),
        crash: lane.runnerVerb ?? "Pending",
        time: mockupClockFromTrackPct(lane.xEnd ?? 80) + ".000",
      },
    }
  );
}

export type MockupOverviewMark = {
  id: string;
  leftPct: number;
  tone: "crash" | "promoted" | "blocked";
  title: string;
};

export function mockupOverviewMarks(): MockupOverviewMark[] {
  return [
    { id: "payload-857-A:crash", leftPct: 77, tone: "crash", title: "Replay Fork · fastest crash" },
    { id: "payload-912-D:promoted", leftPct: 88, tone: "promoted", title: "Boundary Fray D · promoted" },
  ];
}
