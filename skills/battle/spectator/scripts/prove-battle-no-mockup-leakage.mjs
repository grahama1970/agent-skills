#!/usr/bin/env node
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-parent-spawn`
const checks = []

function record(id, pass, detail) {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-battle-pixi-engine="animated-sprites"]', { timeout: 20000 })
await page.waitForTimeout(1200)

const proof = await page.evaluate(() => ({
  receiptFooter: !!document.querySelector('[data-qid="battle:receipt-footer"]'),
  designFooterArm: !!document.querySelector('[data-qid="battle:footer:spectator-arm"]'),
  highlightNext: !!document.querySelector('[data-qid="battle:control:highlight-next"]'),
  highlightReel: !!document.querySelector('[data-qid="battle:control:highlight-reel"]'),
  mockupPatchLabel: Array.from(document.querySelectorAll('.battle-blue-patch span, .bluePatch span')).some((el) => /CanonGuard v1|PathSanity Patch/i.test(el.textContent ?? '')),
  blueStripText: document.querySelector('.battle-blue-strip-stat, .blueStat')?.textContent ?? '',
  lifecycle: (() => {
    const el = document.querySelector('[data-qid="battle:agent-pane:lifecycle-evidence"]');
    if (!el) return false;
    // Fail-closed is proven by the explicit data-material="0" marker or the
    // fail-closed copy ("nothing invented" / "not emitted") — no fabricated data.
    return el.getAttribute('data-material') === '0' || /not emitted|nothing invented|fail-closed/i.test(el.textContent ?? '');
  })(),
}))

record('1-receipt-footer-present', proof.receiptFooter, JSON.stringify({ receiptFooter: proof.receiptFooter }))
record('2-no-design-footer-qids', !proof.designFooterArm, JSON.stringify({ designFooterArm: proof.designFooterArm }))
record('3-highlight-controls', proof.highlightNext && proof.highlightReel, JSON.stringify({ highlightNext: proof.highlightNext, highlightReel: proof.highlightReel }))
record('4-no-mockup-patch-labels', !proof.mockupPatchLabel, JSON.stringify({ mockupPatchLabel: proof.mockupPatchLabel }))
record('5-receipt-blue-counts', /Interventions\s+4/i.test(proof.blueStripText) && /Blocks\s+2/i.test(proof.blueStripText), proof.blueStripText)
record('6-lifecycle-fail-closed', proof.lifecycle, JSON.stringify({ lifecycle: proof.lifecycle }))

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_NO_MOCKUP_LEAKAGE_PASS')
