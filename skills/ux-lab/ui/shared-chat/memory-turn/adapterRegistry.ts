import type { MemoryTurnAdapter, TurnBranch, TurnInput, TurnSurface } from "./MemoryTurnAdapter";
import type { PersonaPlexAdapterOptions } from "./PersonaPlexAdapter";
import { PersonaPlexAdapter } from "./PersonaPlexAdapter";
import type { SpartaComplianceAdapterOptions } from "./SpartaComplianceAdapter";
import { SpartaComplianceAdapter } from "./SpartaComplianceAdapter";
import type { WatchChatAdapterOptions } from "./WatchChatAdapter";
import { WatchChatAdapter } from "./WatchChatAdapter";

export type SharedChatMode = "compliance" | "personaplex";

export interface AdapterRegistryConfig {
	surface: TurnSurface;
	mode?: SharedChatMode;
	defaultBranch?: TurnBranch;
	sparta?: SpartaComplianceAdapterOptions;
	watch?: WatchChatAdapterOptions;
	personaplex?: PersonaPlexAdapterOptions;
	/** Allow host tests to inject prebuilt adapters without changing surface code. */
	adapters?: Partial<Record<TurnBranch, MemoryTurnAdapter>>;
}

export interface AdapterRegistry {
	getAdapter(input?: Partial<TurnInput>): MemoryTurnAdapter;
	getAdapterForBranch(branch: TurnBranch): MemoryTurnAdapter;
	branchForInput(input: Partial<TurnInput>): TurnBranch;
}

export function createAdapterRegistry(config: AdapterRegistryConfig): AdapterRegistry {
	const adapters = new Map<TurnBranch, MemoryTurnAdapter>();

	const getOrCreate = (branch: TurnBranch): MemoryTurnAdapter => {
		const injected = config.adapters?.[branch];
		if (injected) return injected;

		const existing = adapters.get(branch);
		if (existing) return existing;

		let created: MemoryTurnAdapter;
		if (branch === "watch") {
			if (!config.watch) throw new Error("WatchChatAdapter requires watch adapter options");
			created = new WatchChatAdapter(config.watch);
		} else if (branch === "personaplex") {
			created = new PersonaPlexAdapter(config.personaplex);
		} else {
			created = new SpartaComplianceAdapter(config.sparta);
		}

		adapters.set(branch, created);
		return created;
	};

	const branchForInput = (input: Partial<TurnInput>): TurnBranch => {
		if (input.branchHint) return input.branchHint;
		if (config.surface === "watch") return "watch";
		if (input.mode === "personaplex" || config.mode === "personaplex") return "personaplex";
		if (config.defaultBranch) return config.defaultBranch;
		return "compliance";
	};

	return {
		getAdapter(input: Partial<TurnInput> = {}): MemoryTurnAdapter {
			return getOrCreate(branchForInput(input));
		},
		getAdapterForBranch(branch: TurnBranch): MemoryTurnAdapter {
			return getOrCreate(branch);
		},
		branchForInput,
	};
}

/**
 * Branch table consumed by SharedChatShell to avoid if/else drift across host
 * surfaces. Persona mode still uses ComplianceChatWell for rendering; this only
 * selects the turn adapter.
 */
export const SHARED_CHAT_BRANCH_TABLE: Record<
	TurnSurface | "persona-mode",
	{ defaultBranch: TurnBranch; allowedBranches: TurnBranch[]; renderer: "ComplianceChatWell" }
> = {
	"sparta-explorer": {
		defaultBranch: "compliance",
		allowedBranches: ["evidence-case", "compliance", "utility", "aql", "personaplex"],
		renderer: "ComplianceChatWell",
	},
	watch: {
		defaultBranch: "watch",
		allowedBranches: ["watch"],
		renderer: "ComplianceChatWell",
	},
	"embry-voice": {
		defaultBranch: "embry-voice",
		allowedBranches: ["embry-voice"],
		renderer: "ComplianceChatWell",
	},
	"final-site": {
		defaultBranch: "compliance",
		allowedBranches: ["compliance", "personaplex", "evidence-case", "utility", "aql"],
		renderer: "ComplianceChatWell",
	},
	"shared-chat": {
		defaultBranch: "compliance",
		allowedBranches: ["compliance", "personaplex", "evidence-case", "utility", "aql", "watch"],
		renderer: "ComplianceChatWell",
	},
	"persona-mode": {
		defaultBranch: "personaplex",
		allowedBranches: ["personaplex"],
		renderer: "ComplianceChatWell",
	},
};
