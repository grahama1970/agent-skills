import type { BattleLiveTransportContractViewModel } from "./lib/battle-live-transport-contract-types";
import type { BattleLiveSseClientState } from "./lib/battle-live-sse-client";
import type { BattleTransportViewModel } from "./lib/battle-transport-types";
import type { BattleLiveTransportMode } from "./lib/battle-transport-registry";

type Props = {
	mode: BattleLiveTransportMode;
	model: BattleTransportViewModel | null;
	contractModel?: BattleLiveTransportContractViewModel | null;
	sseClient?: BattleLiveSseClientState | null;
	onReturnToLive: () => void;
	onRecover?: () => void;
};

function isLiveAdapterConnected(sseClient: BattleLiveSseClientState | null | undefined): boolean {
	if (!sseClient) return false;
	if (sseClient.live !== "local_http_sse_adapter") return false;
	return ["connecting", "open", "ended", "gap_recovery", "error"].includes(sseClient.status);
}

export function BattleLiveTransportBanner({
	mode,
	model,
	contractModel = null,
	sseClient = null,
	onReturnToLive,
	onRecover,
}: Props) {
	if (mode === "contract" && contractModel && isLiveAdapterConnected(sseClient)) {
		return (
			<section className="battle-live-transport-banner" data-qid="battle:live:banner" aria-label="Battle live SSE transport">
				<div className="flex flex-wrap items-center gap-2">
					<span
						className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100"
						data-qid="battle:live:banner:mode"
					>
						LIVE SSE ADAPTER
					</span>
					<span
						className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100"
						data-qid="battle:live:banner:live-source"
					>
						LIVE: LOCAL HTTP SSE
					</span>
					<span
						className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100"
						data-qid="battle:live:banner:mocked"
					>
						MOCKED: NO
					</span>
					<span
						className="rounded border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-violet-100"
						data-qid="battle:live:banner:sse-connected"
					>
						{sseClient?.transportMode === "event_source" ? "EVENTSOURCE OPEN" : "SSE CONNECTED"}
					</span>
					<span
						className="rounded border border-sky-400/30 bg-sky-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-sky-100"
						data-qid="battle:live:banner:transport-mode"
					>
						{sseClient?.transportMode === "event_source"
							? "TRANSPORT: EVENTSOURCE"
							: sseClient?.transportMode === "fetch_last_event_id"
								? "TRANSPORT: FETCH RESUME"
								: "TRANSPORT: UNKNOWN"}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:status">
						status {model?.status ?? sseClient?.status ?? "connecting"}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:seq">
						seq {model?.appliedSeq ?? sseClient?.lastSeq ?? 0}/{model?.lastSeq ?? "?"}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:sse-client">
						sse client {sseClient?.status ?? "idle"}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:genetic-count">
						genetic types {contractModel.geneticEventCount}
					</span>
					{model && !model.followLive ? (
						<button
							type="button"
							className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-amber-100"
							data-qid="battle:live:return-to-live"
							onClick={onReturnToLive}
						>
							Return to live
						</button>
					) : (
						<span className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80" data-qid="battle:live:following">
							Following live cursor
						</span>
					)}
					{(model?.status === "gap_recovery" || sseClient?.status === "gap_recovery") && onRecover ? (
						<button
							type="button"
							className="rounded border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-rose-100"
							data-qid="battle:live:recover-snapshot"
							onClick={onRecover}
						>
							Reload snapshot
						</button>
					) : null}
				</div>
				<div className="mt-2 grid gap-1 text-[11px] text-slate-300 md:grid-cols-3">
					<div data-qid="battle:live:battle-id">battle_id: {contractModel.battleId}</div>
					<div data-qid="battle:live:run-id">run_id: {model?.runId ?? contractModel.runId}</div>
					<div data-qid="battle:live:sse-endpoint">sse: {contractModel.sseEndpoint}</div>
					<div data-qid="battle:live:snapshot-endpoint">snapshot: {contractModel.snapshotEndpoint}</div>
					<div data-qid="battle:live:base-url">base: {sseClient?.baseUrl ?? "n/a"}</div>
					<div data-qid="battle:live:source">live_source: local_http_sse_adapter</div>
				</div>
				<div className="mt-2 grid gap-2 md:grid-cols-2" data-qid="battle:live:claim-boundary">
					<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2" data-qid="battle:live:claim-may">
						<div className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80">May claim</div>
						<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
							<li>local http sse adapter executed</li>
							<li>ordered battle.live_event.v1 stream applied</li>
							<li>snapshot bootstrap + Last-Event-ID resume supported</li>
						</ul>
					</div>
					<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-2" data-qid="battle:live:claim-must-not">
						<div className="text-[10px] font-black uppercase tracking-[0.1em] text-rose-300/80">Must not claim</div>
						<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
							{contractModel.mustNotClaim
								.filter((item) => !["sse_endpoint_implemented", "live_stream_executed"].includes(item))
								.map((item) => (
									<li key={item}>{item.replace(/_/g, " ")}</li>
								))}
							<li>production deployment</li>
							<li>websocket endpoint implemented</li>
						</ul>
					</div>
				</div>
				<div className="mt-2 flex flex-wrap gap-1" data-qid="battle:live:genetic-types">
					{contractModel.geneticEventTypes.map((item) => (
						<span key={item} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-300" data-qid={`battle:live:genetic:${item}`}>
							{item}
						</span>
					))}
				</div>
				{model?.error || sseClient?.error ? (
					<div className="mt-2 rounded border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100" data-qid="battle:live:error">
						{model?.error ?? sseClient?.error}
					</div>
				) : null}
			</section>
		);
	}

	if (mode === "contract" && contractModel) {
		return (
			<section className="battle-live-transport-banner" data-qid="battle:live:banner" aria-label="Battle live transport contract">
				<div className="flex flex-wrap items-center gap-2">
					<span
						className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100"
						data-qid="battle:live:banner:mode"
					>
						SSE CONTRACT
					</span>
					<span
						className="rounded border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-amber-100"
						data-qid="battle:live:banner:contract-only"
					>
						LIVE: CONTRACT ONLY
					</span>
					<span
						className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100"
						data-qid="battle:live:banner:mocked"
					>
						MOCKED: NO
					</span>
					<span
						className="rounded border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-rose-100"
						data-qid="battle:live:banner:no-endpoint"
					>
						SSE ENDPOINT NOT EXECUTED
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:status">
						status {contractModel.status}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:transport">
						{contractModel.transportKind}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:sse-client">
						sse client {sseClient?.status ?? "idle"}
					</span>
					<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:genetic-count">
						genetic types {contractModel.geneticEventCount}
					</span>
				</div>
				<div className="mt-2 grid gap-1 text-[11px] text-slate-300 md:grid-cols-3">
					<div data-qid="battle:live:battle-id">battle_id: {contractModel.battleId}</div>
					<div data-qid="battle:live:run-id">run_id: {contractModel.runId}</div>
					<div data-qid="battle:live:sse-endpoint">sse: {contractModel.sseEndpoint}</div>
					<div data-qid="battle:live:snapshot-endpoint">snapshot: {contractModel.snapshotEndpoint}</div>
					<div data-qid="battle:live:reconnect">reconnect: {contractModel.reconnectHeader}</div>
					<div data-qid="battle:live:gap">gap: {contractModel.gapResponse}</div>
				</div>
				<div className="mt-2 grid gap-2 md:grid-cols-2" data-qid="battle:live:claim-boundary">
					<div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2" data-qid="battle:live:claim-may">
						<div className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80">May claim</div>
						<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
							{contractModel.mayClaim.map((item) => (
								<li key={item}>{item.replace(/_/g, " ")}</li>
							))}
						</ul>
					</div>
					<div className="rounded-lg border border-rose-400/20 bg-rose-400/5 p-2" data-qid="battle:live:claim-must-not">
						<div className="text-[10px] font-black uppercase tracking-[0.1em] text-rose-300/80">Must not claim</div>
						<ul className="mt-1 space-y-0.5 text-[11px] text-slate-200">
							{contractModel.mustNotClaim.map((item) => (
								<li key={item}>{item.replace(/_/g, " ")}</li>
							))}
						</ul>
					</div>
				</div>
				<div className="mt-2 flex flex-wrap gap-1" data-qid="battle:live:genetic-types">
					{contractModel.geneticEventTypes.map((item) => (
						<span key={item} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-300" data-qid={`battle:live:genetic:${item}`}>
							{item}
						</span>
					))}
				</div>
				{sseClient?.error ? (
					<div className="mt-2 rounded border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100" data-qid="battle:live:contract-note">
						{sseClient.error}
					</div>
				) : null}
			</section>
		);
	}

	if (!model) return null;

	return (
		<section className="battle-live-transport-banner" data-qid="battle:live:banner" aria-label="Battle live transport">
			<div className="flex flex-wrap items-center gap-2">
				<span
					className="rounded border border-cyan-400/30 bg-cyan-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-cyan-100"
					data-qid="battle:live:banner:mode"
				>
					FILE-BACKED STREAM
				</span>
				<span
					className="rounded border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-violet-100"
					data-qid="battle:live:banner:phase"
				>
					{model.phase.replace(/_/g, " ").toUpperCase()}
				</span>
				<span
					className="rounded border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.12em] text-emerald-100"
					data-qid="battle:live:banner:mocked"
				>
					MOCKED: {model.mocked ? "YES" : "NO"}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:status">
					status {model.status}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400" data-qid="battle:live:seq">
					seq {model.appliedSeq}/{model.lastSeq}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:transport">
					{model.transport}
				</span>
				<span className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500" data-qid="battle:live:event-count">
					events {model.eventCount}
				</span>
				{!model.followLive ? (
					<button
						type="button"
						className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-amber-100"
						data-qid="battle:live:return-to-live"
						onClick={onReturnToLive}
					>
						Return to live
					</button>
				) : (
					<span className="text-[10px] font-black uppercase tracking-[0.1em] text-emerald-300/80" data-qid="battle:live:following">
						Following live cursor
					</span>
				)}
				{model.status === "gap_recovery" && onRecover ? (
					<button
						type="button"
						className="rounded border border-rose-400/40 bg-rose-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.1em] text-rose-100"
						data-qid="battle:live:recover-snapshot"
						onClick={onRecover}
					>
						Reload snapshot
					</button>
				) : null}
			</div>
			<div className="mt-2 grid gap-1 text-[11px] text-slate-300 md:grid-cols-3">
				<div data-qid="battle:live:battle-id">battle_id: {model.battleId}</div>
				<div data-qid="battle:live:run-id">run_id: {model.runId}</div>
				<div data-qid="battle:live:source">live_source: {model.liveSource}</div>
				<div data-qid="battle:live:cursor">cursor_seconds: {model.cursorSeconds.toFixed(3)}</div>
				<div data-qid="battle:live:live-seconds">live_seconds: {model.liveSeconds.toFixed(3)}</div>
				<div data-qid="battle:live:authority">authority: normalized fixture + stream events</div>
			</div>
			{model.error ? (
				<div className="mt-2 rounded border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100" data-qid="battle:live:error">
					{model.error}
				</div>
			) : null}
		</section>
	);
}
