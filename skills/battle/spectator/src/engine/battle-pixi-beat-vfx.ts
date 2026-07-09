import { Container, Graphics, Sprite, type Texture } from "pixi.js";
import type { BattleRaceEngineRowLayout, Lane } from "../lib/battle-types";
import type { ReceiptBeat } from "../lib/battle-receipt-beats";
import { textureFromAtlas } from "./battle-race-atlas";
import { configureBattleSceneLayer } from "./battle-pixi-game-mechanics";
import { laneElapsedRange } from "../lib/battle-elapsed-axis";

export const SPAWN_PULSE_SECONDS = 0.62;
export const BLOCK_SHIELD_SECONDS = 0.88;

export type BeatVfxKind = "spawn_pulse" | "block_shield" | "none";

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
