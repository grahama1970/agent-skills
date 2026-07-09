#!/usr/bin/env node
import { chromium } from "playwright";

const host = process.env.BATTLE_HOST ?? "http://127.0.0.1:3002";
const fixture = await (await fetch(`${host}/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json`)).json();
const lane = fixture.lanes.find((item) => item.id === "payload-857-red-1");
const blastAt = lane.events.find((event) => event.kind === "blue_blast").elapsed_seconds;
const impactAt = blastAt + 0.55 + 0.05;

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto(`${host}/#battle/receipt?fixture=battle-004-kill-shot&pixiTest=1&pixiSeconds=${impactAt}`, {
  waitUntil: "networkidle",
  timeout: 60000,
});
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 });
await page.waitForTimeout(800);

const state = await page.evaluate(() => {
  const stage = document.querySelector('[data-qid="battle:pixi:stage"]');
  const deathCard = document.querySelector('[data-testid="battle-hunger-games-death-card"]');
  return {
    beatKind: stage?.dataset.battleReceiptBeatKind ?? null,
    emphasis: stage?.dataset.battleReceiptBeatEmphasis ?? null,
    killImpact: stage?.dataset.battleKillShotImpact ?? null,
    deathCard: Boolean(deathCard),
    vfx: stage?.dataset.battleReceiptBeatVfx ?? null,
  };
});

const pass =
  state.emphasis === "kill_impact" &&
  state.killImpact === "killed" &&
  state.beatKind === "kill_impact" &&
  state.deathCard;
console.log(JSON.stringify({ state, pass }, null, 2));
if (!pass) process.exit(1);
console.log("BATTLE_PROVE_RECEIPT_DIRECTOR_KILLED_PASS");
await browser.close();
