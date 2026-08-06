/** Local NVIS tokens for Embry Console lean-in surfaces (PR4 r6b). */
export const SPARTA_CHAT_NVIS = {
	bgDeep: "#0b1220",
	bgHeader: "#0f172a",
	bgPanel: "#111827",
	bgCard: "#1a1a1a",
	border: "rgba(255,255,255,0.13)",
	activeGreen: "#00ff41",
	embryCyan: "#00d1ff",
	warningAmber: "#ffaa00",
	blockedRed: "#ff4444",
	textWhite: "#f5f5f5",
	textDim: "#94a3b8",
} as const;

/** Readable sidebar-chat typography (15px body, 40+ / arm's-length). */
export const CHAT_READABLE = {
	/** Primary assistant/user prose — Gemini sidebar ~15–16px */
	bodySize: 16,
	/** Receipt meta lines — still smaller than body but readable */
	metaSize: 14,
	labelSize: 12,
	/** Empty-state greeting / section title */
	greetingSize: 22,
	/** Starter prompt pills */
	promptSize: 14,
	lineHeight: 1.75,
	/** User bubble padding — comfortable, not tight */
	chatBubblePadding: "12px 16px",
	/** Vertical space between conversation turns (Chrome/Gemini sidebar density) */
	turnSpacing: 12,
	/** Space between prose and figure/table/receipt in same turn */
	blockGap: 8,
	threadPadding: "12px 16px",
	/** @deprecated use turnSpacing */
	turnGap: 18,
	messageGap: 12,
	cardPadding: "16px 20px",
	cardGap: 12,
	fontSans: 'var(--font-ui, "Google Sans Text", "Google Sans", system-ui, sans-serif)',
	fontMono: "var(--font-mono, ui-monospace, monospace)",
	/** Legacy non-receipt user bubble (10ft/5ft fallback) */
	userSurface: "#282a2c",
	userBubbleBorder: "rgba(255, 255, 255, 0.08)",
	userBubbleRadius: "20px",
	userWellPadding: "12px 20px",
	/** Tinted assistant turn well — single container, no nested cards */
	/** Ghost well — ~2% darker than chat pane, no inner borders */
	assistantWellBg: "transparent",
	assistantWellRadius: 0,
	assistantWellPadding: "0px",
	/** Embry authority accent — left bar, not full box */
	assistantWellAccent: "#60a5fa",
	/** Agent prose stays on the canvas (no competing bubble) */
	assistantSurface: "transparent",
	assistantSurfaceRadius: 0,
	assistantSurfacePadding: "0",
	metadataSize: 11,
	tablePreviewFontSize: 11,
	/** Gemini-like figure/image containment in chat receipts */
	figureFrameRadius: 12,
	figureFrameBorder: "rgba(255, 255, 255, 0.22)",
	figureFrameBg: "rgba(255, 255, 255, 0.04)",
	figureCaptionColor: "#94a3b8",
	borderSubtle: "rgba(255, 255, 255, 0.08)",
	borderMedium: "rgba(255, 255, 255, 0.15)",
	borderStrong: "rgba(255, 255, 255, 0.22)",
	/** Rows shown in chat table previews; remainder in workspace */
	tablePreviewRows: 3,
	/** Max preview height for chat-pane tables (3-row rule) */
	chatTableMaxHeight: 150,
	chatArtifactMaxHeight: 120,
} as const;

/** Chat layout density — token-driven, not a runtime CSS class toggle yet */
export type ChatReadableTokens = typeof CHAT_READABLE;
export type ChatDensity = keyof typeof CHAT_DENSITY;

export function chatTokensForDensity(density: ChatDensity): ChatReadableTokens {
	return CHAT_DENSITY[density] as ChatReadableTokens;
}

export const CHAT_DENSITY = {
	comfortable: CHAT_READABLE,
	compact: {
		...CHAT_READABLE,
		bodySize: 15,
		turnSpacing: 6,
		blockGap: 12,
		chatBubblePadding: "10px 12px",
		assistantSurfacePadding: "10px 12px",
		tablePreviewRows: 2,
		threadPadding: "6px 14px",
		messageGap: 6,
	},
} as const;
