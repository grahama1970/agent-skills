import { Assets, Container, Graphics, GraphicsContext, Rectangle, Text } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import { BATTLE_LANE_LABEL_PX } from "../lib/layout-constants";

/**
 * The frozen lane-label column, rendered entirely in Pixi on a fixed layer that
 * sits ABOVE the panning viewport (so labels stay put while the track scrolls).
 * This replaces the DOM `.battle-receipt-pixi-lane-label` overlay — the timeline
 * well is 100% Pixi, no DOM inside it. Styling mirrors battle-pixi-engine.css.
 */

const LABEL_BG = 0x03080f;
const BORDER = 0xffffff;
const SELECTED = 0x39f278;
const ICON_TONE = 0xff4d5c;
const BUG_STROKE = 0xff6b7a;
const NAME_FILL = 0xe2e8f0;
const META_FILL = 0x94a3b8;
const GEN_FILL = 0x8fffb0;
const TERMINAL_FILL: Record<string, number> = { green: 0x8fffb0, blue: 0x7ec0ff, yellow: 0xffe070 };

// Lucide `bug` glyph (24x24 viewBox), stroked in the label's red tone.
const BUG_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#ff6b7a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M3 21c0-2.1 1.7-3.9 3.8-4"/><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4"/><path d="M22 13h-4"/><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4"/></svg>`;
// Lucide `chevron-down` glyph, slate stroke; rotated -90deg when the lane is collapsed.
const CHEVRON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;

let bugContext: GraphicsContext | null = null;
let chevronContext: GraphicsContext | null = null;
let iconsPromise: Promise<void> | null = null;

async function loadSvgContext(svg: string): Promise<GraphicsContext | null> {
	const ctx = await Assets.load<GraphicsContext>({
		src: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,
		parser: "svg",
		data: { parseAsGraphicsContext: true },
	});
	return ctx instanceof GraphicsContext ? ctx : null;
}

/** Load the bug + chevron glyphs as shared GraphicsContexts. Idempotent. */
export async function loadBattleLabelIcons(): Promise<void> {
	if (!iconsPromise) {
		iconsPromise = (async () => {
			const [bug, chevron] = await Promise.all([loadSvgContext(BUG_SVG), loadSvgContext(CHEVRON_SVG)]);
			bugContext = bug;
			chevronContext = chevron;
		})().catch((error) => {
			iconsPromise = null;
			throw error;
		});
	}
	return iconsPromise;
}

type LabelGroup = {
	root: Container;
	bg: Graphics;
	iconBox: Graphics;
	bug: Graphics | null;
	chevron: Container | null;
	chevronGlyph: Graphics | null;
	name: Text;
	meta: Text;
	gen: Text;
	terminal: Text;
	cache: { name: string; meta: string; gen: string; terminal: string; termColor: number; selected: boolean; w: number; h: number; collapsed: boolean; hasChildren: boolean };
};

export type BattleLabelLayer = {
	container: Container;
	groups: Map<string, LabelGroup>;
	onSelect: { current: (laneId: string) => void };
	onToggleCollapse: { current: (laneId: string) => void };
};

export function createBattleLabelLayer(): BattleLabelLayer {
	const container = new Container();
	container.label = "battle-labels";
	return { container, groups: new Map(), onSelect: { current: () => {} }, onToggleCollapse: { current: () => {} } };
}

function displayNameOf(lane: Lane): string {
	return lane.name.replace(/\s+red-\d+$/i, "");
}

function terminalLabelOf(lane: Lane): { label: string; color: number } {
	const label = lane.terminal === "none" ? "ACTIVE" : lane.terminal.replace(/_/g, " ").toUpperCase();
	const variant = lane.terminal === "blocked" ? "blue" : label === "QUALIFIED" ? "green" : lane.terminal === "none" ? "yellow" : "green";
	return { label, color: TERMINAL_FILL[variant] ?? GEN_FILL };
}

function metaOf(lane: Lane): string {
	const display = displayNameOf(lane);
	const suffix = lane.name === display ? null : lane.name.slice(display.length).trim();
	return suffix ? `${suffix} · ${lane.payloadId}` : lane.payloadId;
}

function makeText(size: number, weight: string, fill: number, anchorX: number): Text {
	const text = new Text({ text: "", style: { fontFamily: "Inter, system-ui, sans-serif", fontSize: size, fontWeight: weight as never, fill, letterSpacing: size <= 10 ? 0.6 : 0 } });
	text.anchor.set(anchorX, 0.5);
	text.eventMode = "none";
	return text;
}

function createGroup(layer: BattleLabelLayer, laneId: string): LabelGroup {
	const root = new Container();
	root.label = `battle-label-${laneId}`;
	root.eventMode = "static";
	root.cursor = "pointer";
	root.accessible = true;
	root.accessibleType = "button";
	root.on("pointertap", () => layer.onSelect.current(laneId));

	const bg = new Graphics();
	const iconBox = new Graphics();
	const bug = bugContext ? new Graphics(bugContext) : null;
	if (bug) {
		bug.eventMode = "none";
		bug.pivot.set(12, 12);
	}
	const name = makeText(12, "800", NAME_FILL, 0);
	const meta = makeText(10, "600", META_FILL, 0);
	const gen = makeText(9, "800", GEN_FILL, 1);
	const terminal = makeText(9, "800", GEN_FILL, 1);

	root.addChild(bg, iconBox);
	if (bug) root.addChild(bug);
	root.addChild(name, meta, gen, terminal);

	// Collapse chevron: its own interactive container so a click toggles the
	// parent's children without also selecting the lane (stopPropagation).
	let chevron: Container | null = null;
	let chevronGlyph: Graphics | null = null;
	if (chevronContext) {
		chevron = new Container();
		chevron.eventMode = "static";
		chevron.cursor = "pointer";
		chevron.visible = false;
		chevron.hitArea = new Rectangle(-10, -10, 20, 20);
		chevronGlyph = new Graphics(chevronContext);
		chevronGlyph.eventMode = "none";
		chevronGlyph.pivot.set(12, 12);
		chevronGlyph.scale.set(16 / 24);
		chevron.addChild(chevronGlyph);
		chevron.on("pointertap", (event: { stopPropagation?: () => void }) => {
			event.stopPropagation?.();
			layer.onToggleCollapse.current(laneId);
		});
		root.addChild(chevron);
	}
	layer.container.addChild(root);

	const group: LabelGroup = {
		root,
		bg,
		iconBox,
		bug,
		chevron,
		chevronGlyph,
		name,
		meta,
		gen,
		terminal,
		cache: { name: "", meta: "", gen: "", terminal: "", termColor: 0, selected: false, w: 0, h: 0, collapsed: false, hasChildren: false },
	};
	layer.groups.set(laneId, group);
	return group;
}

function drawChrome(group: LabelGroup, w: number, h: number, isChild: boolean, selected: boolean): void {
	const c = group.cache;
	if (c.w === w && c.h === h && c.selected === selected) return;
	c.w = w;
	c.h = h;
	c.selected = selected;

	group.bg.clear();
	group.bg.rect(0, 0, w, h).fill(LABEL_BG);
	if (selected) {
		group.bg.rect(0, 0, w, h).fill({ color: SELECTED, alpha: 0.08 });
		group.bg.rect(0.5, 0.5, w - 1, h - 1).stroke({ color: SELECTED, alpha: 0.22, width: 1 });
	}
	group.bg.moveTo(w - 0.5, 0).lineTo(w - 0.5, h).stroke({ color: BORDER, alpha: 0.06, width: 1 });

	const padLeft = isChild ? 28 : 12;
	const cy = h / 2;
	// 22x22 red icon box
	group.iconBox.clear();
	group.iconBox.roundRect(padLeft, cy - 11, 22, 22, 6).fill({ color: ICON_TONE, alpha: 0.08 }).stroke({ color: ICON_TONE, alpha: 0.35, width: 1 });
	if (group.bug) {
		group.bug.scale.set(15 / 24);
		group.bug.position.set(padLeft + 11, cy);
	}
	const textLeft = padLeft + 22 + 8;
	group.name.position.set(textLeft, cy - 7);
	group.meta.position.set(textLeft, cy + 8);
	group.terminal.position.set(w - 10, cy);
}

export function syncBattleLabelLayer(
	layer: BattleLabelLayer,
	lanes: Lane[],
	rowLayout: BattleRaceEngineRowLayout[],
	selectedLaneId: string | null,
	collapsedIds: Set<string> = new Set(),
): void {
	const rowByLane = new Map(rowLayout.map((row) => [row.laneId, row]));
	const seen = new Set<string>();

	for (const lane of lanes) {
		const row = rowByLane.get(lane.id);
		if (!row) continue;
		seen.add(lane.id);
		const group = layer.groups.get(lane.id) ?? createGroup(layer, lane.id);
		const w = BATTLE_LANE_LABEL_PX;
		const isChild = lane.parentId != null;
		const selected = selectedLaneId === lane.id;
		const hasChildren = Boolean(lane.children?.length);
		const collapsed = collapsedIds.has(lane.id);

		group.root.visible = true;
		group.root.position.set(0, row.topPx);
		group.root.hitArea = new Rectangle(0, 0, w, row.heightPx);
		drawChrome(group, w, row.heightPx, isChild, selected);

		if (group.chevron && group.chevronGlyph) {
			group.chevron.visible = hasChildren;
			if (hasChildren) {
				group.chevron.position.set(16, row.heightPx / 2);
				// chevron-down when expanded, rotate to point right when collapsed
				group.chevronGlyph.rotation = collapsed ? -Math.PI / 2 : 0;
			}
		}

		const nameStr = displayNameOf(lane);
		const metaStr = metaOf(lane);
		const genStr = `GEN ${lane.generation}`;
		const { label: termStr, color: termColor } = terminalLabelOf(lane);
		const c = group.cache;
		if (c.name !== nameStr) { group.name.text = nameStr; c.name = nameStr; }
		if (c.meta !== metaStr) { group.meta.text = metaStr; c.meta = metaStr; }
		if (c.gen !== genStr) { group.gen.text = genStr; c.gen = genStr; }
		if (c.terminal !== termStr || c.termColor !== termColor) {
			group.terminal.text = termStr;
			group.terminal.style.fill = termColor;
			c.terminal = termStr;
			c.termColor = termColor;
		}
		// GEN sits to the left of the terminal label (both right-anchored).
		group.gen.position.set(group.terminal.x - group.terminal.width - 8, row.heightPx / 2);
		group.root.accessibleTitle = `Select lane ${lane.name}`;
	}

	for (const [laneId, group] of layer.groups) {
		if (!seen.has(laneId)) group.root.visible = false;
	}
}

export function teardownBattleLabelLayer(layer: BattleLabelLayer): void {
	for (const group of layer.groups.values()) {
		// Preserve the shared bug GraphicsContext; destroy the wrapper only.
		group.root.destroy({ children: true, context: false });
	}
	layer.groups.clear();
	layer.container.destroy({ children: true });
}
