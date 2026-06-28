/** EmbryStyle — shared design tokens matching /create-evidence-case viewer */

export const EMBRY = {
	// Backgrounds (dark → light)
	bg: "#141414",
	bgCard: "#1a1a1a",
	bgPanel: "#111111",
	bgDeep: "#0b1220",
	bgHeader: "#0f172a",
	surface: "#1a1a1a", // alias for bgCard — used by InlineEvidenceCase
	surfaceAlt: "#1e1e1e", // slightly lighter surface for contrast

	// Text (aliases for consistency with other token sets)
	text: "#f5f5f5", // alias for white
	textMuted: "#94a3b8", // alias for muted/dim

	// Border
	border: "rgba(255, 255, 255, 0.13)",
	borderHover: "rgba(255, 255, 255, 0.25)",

	// NVIS MIL-STD-3009
	green: "#00ff88",
	red: "#ff4444",
	amber: "#ffaa00",
	blue: "#4a9eff",
	accent: "#7c3aed",
	white: "#f5f5f5", // high-contrast primary text
	dim: "#94a3b8", // slate-500
	muted: "#94a3b8", // slate-400 (COTS: ≥4.5:1 on dark bg)

	// Framework colors
	fw: {
		SPARTA: "#7c3aed",
		"ATT&CK": "#ff4444",
		D3FEND: "#00ff88",
		NIST: "#4a9eff",
		CWE: "#ffaa00",
	} as Record<string, string>,

	/**
	 * Graph node-type semantic colors — colorblind-safe palette.
	 *
	 * Design rationale:
	 *  - Avoids pure red/green pairs (deuteranopia/protanopia affects ~8% of males).
	 *  - Each type is distinguishable by hue AND luminance so grayscale screenshots
	 *    still separate types visually — important for CTF write-up videos.
	 *  - Matches a fixed legend: same type → same color everywhere in the tool.
	 *
	 * Legend:
	 *  function   #4a9eff  blue    — callable unit / top-level symbol
	 *  block      #f59e0b  amber   — basic block inside a function
	 *  syscall    #c084fc  purple  — OS interface boundary
	 *  extern     #22d3ee  cyan    — PLT / imported symbol
	 *  data       #a3a3a3  gray    — static data / rodata reference
	 *  entry      #00ff88  green   — program / function entry point
	 *  exit       #ff6b6b  coral   — return / tail-call exit
	 *  selected   #ffd700  gold    — currently focused node (high contrast)
	 *  highlight  #ff9500  orange  — search match / user annotation
	 */
	graph: {
		function: "#4a9eff", // blue        — callable unit
		block: "#f59e0b", // amber       — basic block
		syscall: "#c084fc", // violet      — OS boundary
		extern: "#22d3ee", // cyan        — PLT / imported
		data: "#a3a3a3", // gray        — static data
		entry: "#a8ff57", // lime        — entry point (lime not green: avoids red/green confusion in deuteranopia)
		exit: "#ff6b6b", // coral       — return/exit (coral not pure red: safer for protanopia)
		selected: "#ffd700", // gold        — active selection (high contrast on dark bg)
		highlight: "#ff9500", // orange      — search / annotation
		edge: "rgba(255,255,255,0.25)", // default edge
		edgeBack: "#ff6b6b", // back-edge (loop) — coral, matches exit
		edgeCross: "#c084fc", // cross-edge       — violet, matches syscall
	} as const,
} as const;

/**
 * Ordered legend rows for rendering a graph color-key in the UI or video
 * thumbnails.  Import this wherever you render a <GraphLegend> component so
 * every surface shows the same mapping.
 *
 * Colorblind notes:
 *  - entry (lime #a8ff57) and exit (coral #ff6b6b) differ by both hue AND
 *    luminance — distinguishable under deuteranopia/protanopia simulation.
 *  - function (blue) / syscall (violet) / extern (cyan) are spread across the
 *    blue spectrum but differ enough in luminance that grayscale screenshots
 *    still separate them.
 *  - selected (gold) is the highest-luminance color — pops on any background.
 */
export const GRAPH_LEGEND = [
	{ type: "function", color: "#4a9eff", label: "Function", desc: "Callable unit / top-level symbol" },
	{ type: "block", color: "#f59e0b", label: "Block", desc: "Basic block inside a function" },
	{ type: "syscall", color: "#c084fc", label: "Syscall", desc: "OS interface / system call" },
	{ type: "extern", color: "#22d3ee", label: "Extern", desc: "PLT / imported symbol" },
	{ type: "data", color: "#a3a3a3", label: "Data", desc: "Static data / rodata reference" },
	{ type: "entry", color: "#a8ff57", label: "Entry", desc: "Program / function entry point" },
	{ type: "exit", color: "#ff6b6b", label: "Exit", desc: "Return / tail-call exit" },
	{ type: "selected", color: "#ffd700", label: "Selected", desc: "Currently focused node" },
	{ type: "highlight", color: "#ff9500", label: "Highlight", desc: "Search match / annotation" },
] as const;

/** Resolve a graph node-type key to its color; falls back to EMBRY.dim for unknown types. */
export function graphNodeColor(type: string): string {
	return (EMBRY.graph as Record<string, string>)[type] ?? EMBRY.dim;
}

/** Card wrapper style (NVIS: sharp tactical edges) */
export const card = {
	backgroundColor: EMBRY.bgCard,
	border: `1px solid ${EMBRY.border}`,
	padding: 20,
} as const;

/** Panel wrapper (darker than card, NVIS: sharp edges) */
export const panel = {
	backgroundColor: EMBRY.bgPanel,
	border: `1px solid ${EMBRY.border}`,
	padding: 16,
} as const;

/** Section label — 10px uppercase tracking-widest */
export const label = {
	fontSize: 10,
	fontWeight: 700,
	textTransform: "uppercase" as const,
	letterSpacing: "0.15em",
	color: EMBRY.dim,
} as const;

/** Section heading */
export const heading = {
	fontSize: 14,
	fontWeight: 900,
	color: EMBRY.white,
	letterSpacing: "-0.02em",
} as const;

/** Body text */
export const body = {
	fontSize: 13,
	color: EMBRY.white,
	lineHeight: 1.6,
} as const;

/** Status glow dot */
export function glowDot(color: string, size = 8): React.CSSProperties {
	return {
		width: size,
		height: size,
		borderRadius: "50%",
		backgroundColor: color,
		boxShadow: `0 0 10px ${color}99`,
		flexShrink: 0,
	};
}

/** Fluid typography scale using clamp() for responsive sizing */
export const FLUID = {
	/** Technique label: 10px → 14px */
	techLabel: "clamp(0.625rem, 0.8vw + 0.4rem, 0.875rem)",
	/** Tactic header: 8px → 12px */
	tacticHeader: "clamp(0.5rem, 0.6vw + 0.3rem, 0.75rem)",
	/** Card padding: 6px → 12px */
	cardPadding: "clamp(6px, 0.8vw, 12px)",
	/** Grid gap: 8px → 16px */
	gridGap: "clamp(8px, 1vw, 16px)",
} as const;

/** Framework badge */
export function fwBadge(framework: string): React.CSSProperties {
	const color = EMBRY.fw[framework] ?? EMBRY.dim;
	return {
		fontSize: 9,
		fontWeight: 700,
		padding: "2px 6px",
		borderRadius: 4,
		color,
		backgroundColor: `${color}18`,
		border: `1px solid ${color}33`,
		letterSpacing: "0.05em",
	};
}
