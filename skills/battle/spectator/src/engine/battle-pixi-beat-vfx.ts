import { Container, Graphics, Sprite, type Texture } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import type { ReceiptBeat } from "../lib/battle-receipt-beats";
import { textureFromAtlas } from "./battle-race-atlas";
import { configureBattleSceneLayer } from "./battle-pixi-game-mechanics";
import { laneElapsedRange } from "../lib/battle-elapsed-axis";

export const SPAWN_PULSE_SECONDS = 0.62;
export const BLOCK_SHIELD_SECONDS = 0.88;

export type BeatVfxKind = "spawn_pulse" | "block_shield" | "genetic" | "none";

export type BeatVfxLayer = {
	container: Container;
	pulseGfx: Graphics;
	shieldPool: Sprite[];
	activeKey: string | null;
};

function secondsToWorldX(seconds: number, allottedSeconds: number, contentWidth: number): number {
	return (Math.max(0, seconds) / Math.max(1, allottedSeconds)) * contentWidth;
}

function runnerXAtSeconds(
	lane: Lane,
	seconds: number,
	allottedSeconds: number,
	contentWidth: number,
	useElapsed: boolean,
): number {
	const { start, end } = laneElapsedRange(lane, allottedSeconds, useElapsed);
	const clamped = Math.max(start, Math.min(end, seconds));
	return secondsToWorldX(clamped, allottedSeconds, contentWidth);
}

export function createBeatVfxLayer(): BeatVfxLayer {
	const container = configureBattleSceneLayer(new Container(), { label: "battle-beat-vfx", cullable: true });
	const pulseGfx = new Graphics();
	pulseGfx.label = "battle-spawn-pulse";
	container.addChild(pulseGfx);
	return { container, pulseGfx, shieldPool: [], activeKey: null };
}

function hideShieldPool(pool: Sprite[], visibleCount: number) {
	for (let index = 0; index < pool.length; index += 1) {
		pool[index].visible = index < visibleCount;
	}
}

function drawSpawnPulse(gfx: Graphics, x: number, y: number, progress: number) {
	gfx.clear();
	for (let ring = 0; ring < 3; ring += 1) {
		const ringProgress = Math.max(0, Math.min(1, progress * 1.25 - ring * 0.18));
		if (ringProgress <= 0) continue;
		const radius = 6 + ringProgress * 30;
		gfx.circle(x, y, radius);
		gfx.stroke({ width: 2.5 - ring * 0.4, color: ring === 0 ? 0x7dd3fc : 0x38bdf8, alpha: (1 - ringProgress) * 0.8 });
	}
	gfx.circle(x, y, 5 + progress * 4);
	gfx.fill({ color: 0xe0f2fe, alpha: Math.max(0, 0.55 - progress * 0.45) });
}

function placeBlockShield(
	pool: Sprite[],
	container: Container,
	markerAtlas: Record<string, Texture>,
	index: number,
	x: number,
	y: number,
	elapsed: number,
	shieldKey: string,
	layer: BeatVfxLayer,
): number {
	const texture = textureFromAtlas("fx-blocked", markerAtlas) ?? textureFromAtlas("marker-blocked", markerAtlas);
	if (!texture) return index;

	let sprite = pool[index];
	if (!sprite) {
		sprite = new Sprite({ texture, anchor: 0.5, eventMode: "none" });
		sprite.cullable = true;
		container.addChild(sprite);
		pool[index] = sprite;
	}

	const pulse = 0.88 + 0.12 * Math.sin(elapsed * 14);
	const fadeIn = Math.min(1, elapsed / 0.12);
	const fadeOut = elapsed > BLOCK_SHIELD_SECONDS - 0.18 ? Math.max(0, (BLOCK_SHIELD_SECONDS - elapsed) / 0.18) : 1;
	sprite.visible = true;
	sprite.position.set(x, y - 2);
	sprite.scale.set(1.35 * pulse);
	sprite.alpha = fadeIn * fadeOut * 0.92;
	sprite.rotation = Math.sin(elapsed * 6) * 0.04;
	layer.activeKey = shieldKey;
	return index + 1;
}


export const GENETIC_VFX_SECONDS = 0.9;

const GENETIC_COLORS: Record<string, number> = {
	research_scan: 0xa78bfa,
	research_receipt: 0xc4b5fd,
	genome_lock: 0xfbbf24,
	gene_shard_join: 0x34d399,
	gene_shard_fade: 0xf87171,
	code_authoring: 0x38bdf8,
	code_glyph: 0x22d3ee,
	compile_error: 0xfb7185,
	compile_lock: 0x4ade80,
	endpoint_pulse: 0x60a5fa,
	judge_pending: 0x94a3b8,
	branch_fade: 0x64748b,
	repair_pulse: 0xf59e0b,
	repair_glyph: 0xfbbf24,
	judge_victory: 0xfacc15,
	genome_promote: 0xfde047,
};

function drawGeneticEffect(gfx: Graphics, x: number, y: number, progress: number, effect: string) {
	gfx.clear();
	const color = GENETIC_COLORS[effect] ?? 0xa78bfa;
	const fade = Math.max(0, 1 - progress);
	if (effect === "research_scan" || effect === "endpoint_pulse" || effect === "judge_pending") {
		for (let ring = 0; ring < 3; ring += 1) {
			const ringProgress = Math.max(0, Math.min(1, progress * 1.2 - ring * 0.15));
			if (ringProgress <= 0) continue;
			const radius = 8 + ringProgress * (effect === "endpoint_pulse" ? 36 : 28);
			gfx.circle(x, y, radius);
			gfx.stroke({ width: 2.2 - ring * 0.35, color, alpha: (1 - ringProgress) * 0.85 });
		}
		return;
	}
	if (effect === "genome_lock" || effect === "compile_lock") {
		const radius = 10 + Math.sin(progress * Math.PI) * 8;
		gfx.circle(x, y, radius);
		gfx.stroke({ width: 3, color, alpha: fade * 0.95 });
		gfx.circle(x, y, 4);
		gfx.fill({ color, alpha: fade * 0.8 });
		return;
	}
	if (effect === "gene_shard_join" || effect === "code_glyph" || effect === "code_authoring" || effect === "repair_glyph") {
		const spread = 18 * (1 - progress);
		for (const dx of [-spread, 0, spread]) {
			gfx.moveTo(x + dx, y - 10);
			gfx.lineTo(x + dx + 4, y);
			gfx.lineTo(x + dx, y + 10);
			gfx.lineTo(x + dx - 4, y);
			gfx.closePath();
			gfx.fill({ color, alpha: fade * 0.75 });
		}
		return;
	}
	if (effect === "gene_shard_fade" || effect === "branch_fade" || effect === "compile_error") {
		const radius = 6 + progress * 22;
		gfx.circle(x, y, radius);
		gfx.stroke({ width: 2, color, alpha: fade * 0.7 });
		gfx.moveTo(x - 10, y - 10);
		gfx.lineTo(x + 10, y + 10);
		gfx.moveTo(x + 10, y - 10);
		gfx.lineTo(x - 10, y + 10);
		gfx.stroke({ width: 2.5, color, alpha: fade * 0.9 });
		return;
	}
	// default pulse
	gfx.circle(x, y, 7 + progress * 20);
	gfx.stroke({ width: 2, color, alpha: fade * 0.8 });
	gfx.circle(x, y, 4);
	gfx.fill({ color, alpha: fade * 0.55 });
}

export function syncBeatEmphasisVfx(args: {
	layer: BeatVfxLayer;
	markerAtlas: Record<string, Texture>;
	lanes: Lane[];
	rowLayout: BattleRaceEngineRowLayout[];
	activeBeat: ReceiptBeat | null | undefined;
	currentSeconds: number;
	allottedSeconds: number;
	contentWidth: number;
	useElapsed?: boolean;
}): { vfx: BeatVfxKind } {
	const {
		layer,
		markerAtlas,
		lanes,
		rowLayout,
		activeBeat,
		currentSeconds,
		allottedSeconds,
		contentWidth,
		useElapsed = false,
	} = args;

	if (!activeBeat) {
		layer.pulseGfx.clear();
		hideShieldPool(layer.shieldPool, 0);
		layer.activeKey = null;
		return { vfx: "none" };
	}

	const lane = lanes.find((item) => item.id === activeBeat.laneId);
	const row = rowLayout.find((item) => item.laneId === activeBeat.laneId);
	if (!lane || !row) {
		layer.pulseGfx.clear();
		hideShieldPool(layer.shieldPool, 0);
		layer.activeKey = null;
		return { vfx: "none" };
	}

	const y = row.topPx + row.heightPx / 2;
	const elapsed = currentSeconds - activeBeat.atSeconds;
	const emphasis = activeBeat.pixi.emphasis;

	if (emphasis === "spawn" && elapsed >= 0 && elapsed <= SPAWN_PULSE_SECONDS) {
		const x = secondsToWorldX(activeBeat.atSeconds, allottedSeconds, contentWidth);
		drawSpawnPulse(layer.pulseGfx, x, y, elapsed / SPAWN_PULSE_SECONDS);
		hideShieldPool(layer.shieldPool, 0);
		layer.activeKey = `${activeBeat.id}:spawn`;
		return { vfx: "spawn_pulse" };
	}

	if (emphasis === "block_impact" && elapsed >= 0 && elapsed <= BLOCK_SHIELD_SECONDS) {
		layer.pulseGfx.clear();
		const x = runnerXAtSeconds(lane, activeBeat.atSeconds, allottedSeconds, contentWidth, useElapsed);
		const shieldCount = placeBlockShield(
			layer.shieldPool,
			layer.container,
			markerAtlas,
			0,
			x,
			y,
			elapsed,
			`${activeBeat.id}:shield`,
			layer,
		);
		hideShieldPool(layer.shieldPool, shieldCount);
		return { vfx: "block_shield" };
	}

	if (
		emphasis !== "none" &&
		emphasis !== "kill_shot_travel" &&
		emphasis !== "kill_impact" &&
		emphasis !== "block_impact" &&
		emphasis !== "spawn" &&
		emphasis !== "terminal" &&
		elapsed >= 0 &&
		elapsed <= GENETIC_VFX_SECONDS
	) {
		const x = secondsToWorldX(activeBeat.atSeconds, allottedSeconds, contentWidth);
		drawGeneticEffect(layer.pulseGfx, x, y, elapsed / GENETIC_VFX_SECONDS, emphasis);
		hideShieldPool(layer.shieldPool, 0);
		layer.activeKey = `${activeBeat.id}:genetic:${emphasis}`;
		return { vfx: "genetic" };
	}

	layer.pulseGfx.clear();
	hideShieldPool(layer.shieldPool, 0);
	layer.activeKey = null;
	return { vfx: "none" };
}

export function teardownBeatVfxLayer(layer: BeatVfxLayer): void {
	layer.pulseGfx.clear();
	for (const sprite of layer.shieldPool) sprite.destroy();
	layer.shieldPool.length = 0;
	layer.activeKey = null;
}
