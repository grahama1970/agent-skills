import { PauseCircle } from "lucide-react";
import type { BattleHumanInterjectionPanelItem, BattleNormalizedUxFixture } from "./lib/battle-types";
import { humanInterjectionOperatorStates, humanInterjectionPanelViewModel } from "./lib/battle-human-interjection";
import type { BattleLivePauseControlState } from "./lib/battle-live-control";
import { useRegisterAction } from "./hooks/useRegisterAction";

type Props = {
	fixture: BattleNormalizedUxFixture | null;
	liveControl?: BattleLivePauseControlState | null;
	onPauseAfterRound?: () => void | Promise<boolean>;
};

const STATE_LABELS: Record<string, string> = {
	pending: "Pending",
	accepted: "Accepted",
	applied: "Applied",
	rejected: "Rejected",
	unavailable: "Unavailable",
	missing_backend: "Missing Backend",
};

function stateTone(state: string): string {
	if (state === "applied") return "border-emerald-400/40 bg-emerald-500/10 text-emerald-100";
	if (state === "accepted" || state === "pending") return "border-cyan-400/40 bg-cyan-500/10 text-cyan-100";
	if (state === "rejected") return "border-rose-400/40 bg-rose-500/10 text-rose-100";
	return "border-amber-400/40 bg-amber-500/10 text-amber-100";
}

export function BattleHumanInterjectionPanel({ fixture, liveControl, onPauseAfterRound }: Props) {
	useRegisterAction("battle:human-interjection:pause-button", {
		action: "BATTLE_PAUSE_AFTER_ROUND_SUBMIT",
		label: "Pause Battle After Round",
		description: "Submit a receipt-backed pause_after_round request to the live Battle backend.",
		tags: ["battle", "live", "human-interjection"],
	});
	const model = humanInterjectionPanelViewModel(fixture);
	const stateValue = model.stateSet.join(" ");
	const fallbackState = model.stateSet[0] === "missing_backend" ? "unavailable" : model.stateSet[0];
	const backendStates: BattleHumanInterjectionPanelItem[] = model.states.length
		? model.states
		: [
				{
					state: fallbackState,
					status: model.status.toUpperCase(),
					label: model.reason ?? "pause_after_round backend receipts are unavailable.",
					request_id: null,
					reason_code: model.status,
					receipt_path: model.sourceProofReceipt,
					receipt_schema: null,
					backend_receipt: false,
					live: model.live === true,
					mocked: model.mocked === true,
				},
			];
	const hasPending = backendStates.some((item) => item.state === "pending" || item.request_id === liveControl?.requestId);
	const stateItems =
		liveControl?.status === "pending" && liveControl.requestId && !hasPending
			? [
					{
						state: "pending" as const,
						status: "PENDING",
						label: "pause_after_round request is being submitted to the backend.",
						request_id: liveControl.requestId,
						reason_code: "client_pending_submit",
						receipt_path: null,
						receipt_schema: null,
						backend_receipt: false,
						live: true,
						mocked: false,
					},
					...backendStates,
				]
			: backendStates;
	const visibleStates = humanInterjectionOperatorStates(stateItems, liveControl?.requestId ?? null);
	const canSubmit =
		Boolean(liveControl?.available && onPauseAfterRound) &&
		liveControl?.status !== "pending" &&
		liveControl?.status !== "accepted" &&
		liveControl?.status !== "applied";

	return (
		<section
			className="rounded-lg border border-cyan-300/15 bg-slate-950/88 px-3 py-2 shadow-lg"
			data-qid="battle:human-interjection:panel"
			data-state={stateValue}
			data-source-bound={String(model.sourceBound)}
			data-live={String(model.live)}
			data-mocked={String(model.mocked)}
			data-run-id={model.runId ?? ""}
			data-source-proof-receipt={model.sourceProofReceipt ?? ""}
			data-control-available={String(liveControl?.available ?? false)}
			data-control-status={liveControl?.status ?? "unavailable"}
			data-control-request-id={liveControl?.requestId ?? ""}
			aria-label="Battle pause after round receipt state"
		>
			<div className="flex flex-wrap items-center gap-2">
				<span className="battle-label">Pause After Round</span>
				<span
					className={`rounded border px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] ${model.sourceBound ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100" : "border-amber-400/40 bg-amber-500/10 text-amber-100"}`}
					data-qid="battle:human-interjection:source"
				>
					{model.sourceBound ? "Backend receipts" : "Fail closed"}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:human-interjection:run">
					run {model.runId ?? "n/a"}
				</span>
				{liveControl?.available ? (
					<button
						type="button"
						className="ml-auto inline-flex min-h-11 items-center gap-2 rounded border border-emerald-300/60 bg-emerald-500/18 px-3 text-[11px] font-black uppercase text-emerald-50 shadow-sm hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:border-slate-600 disabled:bg-slate-800 disabled:text-slate-400"
						data-qid="battle:human-interjection:pause-button"
						data-qs-action="BATTLE_PAUSE_AFTER_ROUND_SUBMIT"
						data-status={liveControl.status}
						data-request-id={liveControl.requestId ?? ""}
						disabled={!canSubmit}
						title="Submit pause_after_round to the live Battle backend"
						aria-label="Submit pause after round"
						onClick={() => {
							void onPauseAfterRound?.();
						}}
					>
						<PauseCircle className="h-4 w-4" aria-hidden="true" />
						Pause
					</button>
				) : null}
			</div>
			<div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-5" data-qid="battle:human-interjection:states">
				{visibleStates.map((item) => (
					<div
						key={`${item.state}:${item.request_id ?? item.status}`}
						className={`min-h-16 rounded border p-2 ${stateTone(item.state)}`}
						data-qid={`battle:human-interjection:state:${item.state}`}
						data-status={item.status}
						data-request-id={item.request_id ?? ""}
						data-reason-code={item.reason_code ?? ""}
						data-backend-receipt={String(item.backend_receipt)}
						data-receipt-path={item.receipt_path ?? ""}
					>
						<div className="text-[10px] font-black uppercase tracking-[0.1em]">{STATE_LABELS[item.state] ?? item.state}</div>
						<div className="mt-1 text-[11px] leading-snug text-slate-100">{item.label}</div>
					</div>
				))}
			</div>
		</section>
	);
}
