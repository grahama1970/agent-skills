import type { BattleEvent, BlueFinisherState, Lane } from "./lib/battle-types";
import { AgentDetailPane } from "./AgentDetailPane";

type Props = {
	laneId: string;
	lanes: Lane[];
	events: BattleEvent[];
	activeFinisher?: BlueFinisherState | null;
	onSound?: (cue: string) => void;
	onClose: () => void;
};

export function AgentCockpit({ laneId, lanes, events, activeFinisher = null, onSound, onClose }: Props) {
	const lane = lanes.find((item) => item.id === laneId) ?? null;
	if (!lane) {
		return (
			<div className="p-4 text-slate-500">
				No agent selected.
				<button type="button" className="ml-2 text-slate-400 underline" onClick={onClose}>
					Close
				</button>
			</div>
		);
	}

	return (
		<div className="flex h-full min-h-0 flex-col">
			<div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
				<h2 className="text-lg font-bold text-white">Agent Cockpit</h2>
				<button type="button" className="text-slate-500 hover:text-white" onClick={onClose} aria-label="Close agent cockpit">
					X
				</button>
			</div>
			<div className="min-h-0 flex-1 overflow-hidden">
				<AgentDetailPane lane={lane} lanes={lanes} events={events} activeFinisher={activeFinisher} onSound={onSound} />
			</div>
		</div>
	);
}

export default AgentCockpit;
