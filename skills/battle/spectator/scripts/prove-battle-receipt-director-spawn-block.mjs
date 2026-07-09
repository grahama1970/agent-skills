#!/usr/bin/env node
import { chromium } from "playwright";

const host = process.env.BATTLE_HOST ?? "http://127.0.0.1:3002";
const fixture = await (await fetch(`${host}/battle-fixtures/battle-004-parent-spawn-pixi-replay/battle.normalized_ux_fixture.json`)).json();
const child = fixture.lanes.find((item) => item.id === "payload-857-red-1");
const handoffAt = child.events.find((event) => event.kind === "handoff").elapsed_seconds;
const blastAt = child.events.find((event) => event.kind === "blue_blast").elapsed_seconds;
const blockAt = blastAt + 0.55 + 0.05;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

async function readStage() {
  return page.evaluate(() => {
    const stage = document.querySelector('[data-qid="battle:pixi:stage"]');
    return {
      beatKind: stage?.dataset.battleReceiptBeatKind ?? null,
      emphasis: stage?.dataset.battleReceiptBeatEmphasis ?? null,
      vfx: stage?.dataset.battleReceiptBeatVfx ?? null,
      killImpact: stage?.dataset.battleKillShotImpact ?? null,
    };
  });
}

await page.goto(`${host}/#battle/receipt?fixture=battle-004-parent-spawn&pixiTest=1&pixiSeconds=${handoffAt}`, {
  waitUntil: "networkidle",
  timeout: 60000,
});
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 });
await page.waitForTimeout(500);
const spawn = await readStage();

await page.goto(`${host}/#battle/receipt?fixture=battle-004-parent-spawn&pixiTest=1&pixiSeconds=${blockAt}`, {
  waitUntil: "networkidle",
  timeout: 60000,
});
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 });
await page.waitForTimeout(500);
const block = await readStage();

const pass =
  spawn.emphasis === "spawn" &&
  spawn.beatKind === "spawn" &&
  spawn.vfx === "spawn_pulse" &&
  block.emphasis === "block_impact" &&
  block.beatKind === "block_impact" &&
  block.vfx === "block_shield" &&
  block.killImpact === "blocked";
console.log(JSON.stringify({ spawn, block, pass }, null, 2));
if (!pass) process.exit(1);
console.log("BATTLE_PROVE_RECEIPT_DIRECTOR_SPAWN_BLOCK_PASS");
await browser.close();
