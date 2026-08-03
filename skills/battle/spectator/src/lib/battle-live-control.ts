import type { BattleHumanInterjectionPanelItem, BattleHumanInterjectionPanelSource } from "./battle-types";
import { absoluteLiveTransportUrl } from "./battle-live-sse-runtime";

export type BattleLivePauseControlStatus =
	| "unavailable"
	| "idle"
	| "pending"
	| "accepted"
	| "applied"
	| "rejected"
	| "error";

export type BattleLivePauseControlState = {
	available: boolean;
	status: BattleLivePauseControlStatus;
	reason: string | null;
	baseUrl: string | null;
	endpoint: string | null;
	runId: string | null;
	requestId: string | null;
	lastReceiptStatus: string | null;
};

export type BattleLivePauseSubmission =
	| {
			ok: true;
			status: "ACCEPTED" | "DUPLICATE_ACCEPTED" | string;
			requestId: string;
			panel: BattleHumanInterjectionPanelSource | null;
	  }
	| {
			ok: false;
			status: string;
			requestId: string;
			reason: string;
			panel: BattleHumanInterjectionPanelSource | null;
	  };

const REQUEST_STORAGE_PREFIX = "battle.pause_after_round.request_id:";

export function deriveBattleLivePauseControl(args: {
	panel: BattleHumanInterjectionPanelSource | null | undefined;
	baseUrl: string | null | undefined;
	requestId?: string | null;
	localPending?: boolean;
	error?: string | null;
}): BattleLivePauseControlState {
	const control = args.panel?.control;
	const available = Boolean(args.baseUrl && args.panel?.source === "backend_receipts" && args.panel.live === true && args.panel.mocked === false && control?.enabled);
	if (!available) {
		return {
			available: false,
			status: "unavailable",
			reason: "pause_after_round control is available only on a live backend route.",
			baseUrl: args.baseUrl ?? null,
			endpoint: control?.endpoint ?? null,
			runId: args.panel?.run_id ?? control?.run_id ?? null,
			requestId: args.requestId ?? null,
			lastReceiptStatus: null,
		};
	}
	const latest = latestState(args.panel?.states ?? []);
	if (args.localPending && latest?.state !== "applied" && latest?.state !== "rejected") {
		return {
			available: true,
			status: "pending",
			reason: null,
			baseUrl: args.baseUrl ?? null,
			endpoint: control?.endpoint ?? null,
			runId: control?.run_id ?? args.panel?.run_id ?? null,
			requestId: args.requestId ?? latest?.request_id ?? null,
			lastReceiptStatus: latest?.status ?? null,
		};
	}
	return {
		available: true,
		status: (latest?.state as BattleLivePauseControlStatus | undefined) ?? (args.error ? "error" : "idle"),
		reason: args.error ?? latest?.reason_code ?? null,
		baseUrl: args.baseUrl ?? null,
		endpoint: control?.endpoint ?? null,
		runId: control?.run_id ?? args.panel?.run_id ?? null,
		requestId: args.requestId ?? latest?.request_id ?? null,
		lastReceiptStatus: latest?.status ?? null,
	};
}

export function stablePauseRequestId(runId: string): string {
	const key = `${REQUEST_STORAGE_PREFIX}${runId}`;
	const existing = typeof window !== "undefined" ? window.sessionStorage.getItem(key) : null;
	if (existing) return existing;
	const generated = `pixi-pause-${runId.replace(/[^A-Za-z0-9_.-]/g, "-")}-${randomSuffix()}`;
	if (typeof window !== "undefined") window.sessionStorage.setItem(key, generated);
	return generated;
}

export async function submitBattleLivePauseAfterRound(args: {
	baseUrl: string;
	endpoint: string;
	runId: string;
	requestId: string;
	authToken: string;
	boundary?: "round_running";
}): Promise<BattleLivePauseSubmission> {
	const response = await fetch(absoluteLiveTransportUrl(args.baseUrl, args.endpoint), {
		method: "POST",
		headers: {
			Accept: "application/json",
			Authorization: `Bearer ${args.authToken}`,
			"Content-Type": "application/json",
		},
		body: JSON.stringify({
			action: "pause_after_round",
			run_id: args.runId,
			request_id: args.requestId,
			boundary: args.boundary ?? "round_running",
		}),
	});
	const body = (await response.json().catch(() => null)) as Record<string, unknown> | null;
	const panel = (body?.panel ?? null) as BattleHumanInterjectionPanelSource | null;
	const status = String(body?.status ?? response.status);
	if (!response.ok || !status.includes("ACCEPT")) {
		return {
			ok: false,
			status,
			requestId: args.requestId,
			reason: String(body?.reason ?? status),
			panel,
		};
	}
	return {
		ok: true,
		status,
		requestId: args.requestId,
		panel,
	};
}

export function liveControlAuthToken(hash = typeof window !== "undefined" ? window.location.hash : ""): string {
	const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
	const token = new URLSearchParams(query).get("controlToken")?.trim();
	if (token) return token;
	const envToken =
		typeof import.meta !== "undefined" &&
		import.meta.env &&
		typeof import.meta.env.VITE_BATTLE_LIVE_CONTROL_TOKEN === "string"
			? import.meta.env.VITE_BATTLE_LIVE_CONTROL_TOKEN.trim()
			: "";
	return envToken;
}

function latestState(states: BattleHumanInterjectionPanelItem[]): BattleHumanInterjectionPanelItem | null {
	const reversed = [...states].reverse();
	const applied = reversed.find((state) => state.state === "applied");
	if (applied) return applied;
	const accepted = reversed.find((state) => state.state === "accepted");
	if (accepted) return accepted;
	const rejected = reversed.find((state) => state.state === "rejected");
	if (rejected) return rejected;
	return states.at(-1) ?? null;
}

function randomSuffix(): string {
	if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
		return crypto.randomUUID().slice(0, 8);
	}
	return Math.random().toString(16).slice(2, 10);
}
