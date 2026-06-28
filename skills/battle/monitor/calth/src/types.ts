export type Team = "red" | "blue" | "judge";
export type Stage = "prepare" | "red" | "blue" | "judge" | "score";

export interface CalthPlayer {
  team: Team;
  persona: string;
  role: string;
  receipt: string;
}

export interface CalthTimelineStage {
  stage: Stage;
  status: string;
}

export interface CalthMonitorIndex {
  schema: "battle.monitor_index.v1";
  battle_id: string;
  campaign: string;
  scenario: string;
  title: string;
  status: string;
  verdict: string;
  players: CalthPlayer[];
  timeline: CalthTimelineStage[];
  scoreboard: string;
  artifacts: string[];
}

export interface CalthScoreboard {
  schema: "battle.scoreboard.v1";
  battle_id: string;
  status: string;
  verdict: string;
  red_score: number;
  blue_score: number;
  tdsr: number;
  fdsr: number;
  asc: number;
  receipts: {
    red: string;
    blue: string;
    judge: string;
  };
}
