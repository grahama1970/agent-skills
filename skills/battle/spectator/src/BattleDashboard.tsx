import { useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { BattleEvent, BattleNormalizedUxFixture, Lane, LeaderboardEntry } from "./lib/battle-types";
import { AgentDetailPane } from "./AgentDetailPane";
import { SpectatorRail } from "./SpectatorRail";
import { useRegisterAction } from "./hooks/useRegisterAction";

export type BattleDashboardRaceData = {
	lanes: Lane[];
	events: BattleEvent[];
	fixture: BattleNormalizedUxFixture | null;
};

type Props = {
	raceData: BattleDashboardRaceData;
	leaderboard: LeaderboardEntry[];
	selectedLaneId: string;
	onSelectLane: (laneId: string) => void;
	children: ReactNode;
	onSound?: (cue: string) => void;
	isRightOpen?: boolean;
	onRightOpenChange?: (open: boolean) => void;
};

export default function BattleDashboard({
	raceData,
	leaderboard,
	selectedLaneId,
	onSelectLane,
	children,
	onSound,
	isRightOpen: isRightOpenProp,
	onRightOpenChange,
}: Props) {
	useRegisterAction("battle:dashboard:leaderboard-toggle", {
		action: "BATTLE_DASHBOARD_LEADERBOARD_TOGGLE",
		label: "Toggle Battle leaderboard",
		description: "Open or close the Battle race leaderboard panel.",
		tags: ["battle", "dashboard"],
	});
	useRegisterAction("battle:dashboard:agent-cockpit-toggle", {
		action: "BATTLE_DASHBOARD_AGENT_COCKPIT_TOGGLE",
		label: "Toggle Battle agent cockpit",
		description: "Open or close the Battle selected-agent cockpit panel.",
		tags: ["battle", "dashboard"],
	});
	const [isLeftOpen, setIsLeftOpen] = useState(false);
	const [isRightOpenInternal, setIsRightOpenInternal] = useState(false);
	const isRightOpen = isRightOpenProp ?? isRightOpenInternal;
	const setIsRightOpen = (open: boolean) => {
		if (onRightOpenChange) onRightOpenChange(open);
		else setIsRightOpenInternal(open);
	};
	const handleSelectLane = (laneId: string) => {
		onSelectLane(laneId);
		setIsRightOpen(true);
	};

	const cockpitLane = raceData.lanes.find((lane) => lane.id === selectedLaneId) ?? null;
	return (
		<div className="relative h-full min-h-0 w-full overflow-hidden bg-slate-950 font-mono text-slate-300">
			<div className="absolute inset-0 z-0">{children}</div>

			<button
				type="button"
				data-qid="battle:dashboard:leaderboard-toggle"
				data-qs-action="BATTLE_DASHBOARD_LEADERBOARD_TOGGLE"
				onClick={() => setIsLeftOpen(!isLeftOpen)}
				className={`pointer-events-auto absolute top-1/2 z-[60] flex h-16 w-6 -translate-y-1/2 items-center justify-center rounded-r-md border border-slate-600 bg-slate-800 shadow-lg transition-all duration-300 hover:bg-slate-700 hover:text-cyan-400 ${
					isLeftOpen ? "left-[320px]" : "left-0"
				}`}
				title="Toggle Global Stats"
				aria-expanded={isLeftOpen}
			>
				{isLeftOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
			</button>

			<aside
				className={`pointer-events-auto absolute top-0 left-0 z-50 h-full w-[320px] border-r border-slate-700 bg-slate-900/95 shadow-2xl backdrop-blur-sm transition-transform duration-300 ease-in-out ${
					isLeftOpen ? "translate-x-0" : "-translate-x-full"
				}`}
				aria-hidden={!isLeftOpen}
			>
				<div className="h-full overflow-y-auto p-4">
					<h2 className="mb-4 text-sm font-bold text-slate-500">RACE LEADERS</h2>
					<SpectatorRail
						receiptFixture={raceData.fixture}
						leaderboard={leaderboard}
						selectedId={selectedLaneId}
						onSelect={handleSelectLane}
					/>
				</div>
			</aside>

			<button
				type="button"
				data-qid="battle:dashboard:agent-cockpit-toggle"
				data-qs-action="BATTLE_DASHBOARD_AGENT_COCKPIT_TOGGLE"
				onClick={() => setIsRightOpen(!isRightOpen)}
				className={`pointer-events-auto absolute top-1/2 z-[60] flex h-16 w-6 -translate-y-1/2 items-center justify-center rounded-l-md border border-slate-600 bg-slate-800 shadow-lg transition-all duration-300 hover:bg-slate-700 hover:text-cyan-400 ${
					isRightOpen ? "right-[384px]" : "right-0"
				}`}
				title="Toggle Agent Cockpit"
				aria-expanded={isRightOpen}
			>
				{isRightOpen ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
			</button>

			<aside
				className={`pointer-events-auto absolute top-0 right-0 z-50 h-full w-96 border-l border-slate-700 bg-slate-900/95 shadow-2xl backdrop-blur-sm transition-transform duration-300 ease-in-out ${
					isRightOpen ? "translate-x-0" : "translate-x-full"
				}`}
				aria-hidden={!isRightOpen}
			>
				<div className="flex h-full min-h-0 flex-col overflow-hidden">
					<div className="border-b border-slate-700 px-4 py-3">
						<h2 className="text-sm font-bold text-slate-500">AGENT DETAIL</h2>
					</div>
					<div className="min-h-0 flex-1 overflow-y-auto p-4">
						{cockpitLane ? (
							<AgentDetailPane lane={cockpitLane} lanes={raceData.lanes} events={raceData.events} activeFinisher={null} onSound={onSound} />
						) : (
							<div className="text-sm text-slate-500">No agent selected.</div>
						)}
					</div>
				</div>
			</aside>
		</div>
	);
}
