#!/usr/bin/env node
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'
import { createHash } from 'node:crypto'

const host = await resolveBattleProveHost()
const outDir = resolve(process.env.BATTLE_MUSIC_M1_PROOF_DIR ?? '/tmp/battle-music-m1-ux-proof')
const fixtureUrl = `${host}/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json`
const route = `${host}/#battle/music?fixture=battle-004-music-runtime`
const checks = []
const record = (id, pass, detail) => {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${detail}`)
}

await mkdir(outDir, { recursive: true })

const localBytes = await readFile(resolve(process.cwd(), 'public/battle-fixtures/battle-004-music-runtime/battle.normalized_music_fixture.json'))
const local = JSON.parse(localBytes.toString('utf8'))
record('1-local-schema', local.schema === 'battle.normalized_music_fixture.v1', local.schema)
record('2-local-mocked-false', local.mocked === false, String(local.mocked))
record('3-entries-2', local.schedule?.entries?.length === 2, String(local.schedule?.entries?.length))
record('4-not-emitted', Array.isArray(local.events_not_emitted) && local.events_not_emitted.includes('exploit_victory_stinger'), JSON.stringify(local.events_not_emitted))

const http = await fetch(fixtureUrl)
record('5-fixture-http', http.ok, String(http.status))
const remoteBytes = Buffer.from(await http.arrayBuffer())
record('6-fixture-byte-identical', remoteBytes.equals(localBytes), `${remoteBytes.length}:${localBytes.length}`)
const remote = JSON.parse(remoteBytes.toString('utf8'))

for (const entry of remote.schedule.entries) {
  const ogg = entry.asset_ref.ogg.public_url
  record(`7-promoted-path-${entry.schedule_entry_id}`, ogg.startsWith('/battle-audio/promoted/v1/'), ogg)
  const asset = await fetch(`${host}${ogg}`)
  record(`8-ogg-http-${entry.schedule_entry_id}`, asset.ok, String(asset.status))
  const body = Buffer.from(await asset.arrayBuffer())
  const sha = createHash('sha256').update(body).digest('hex')
  record(`9-ogg-sha-${entry.schedule_entry_id}`, sha === entry.asset_ref.ogg.sha256, sha)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', (error) => errors.push(error.message))
await page.goto(route, { waitUntil: 'networkidle', timeout: 60_000 })
await page.waitForSelector('[data-qid="battle:music:banner"]', { timeout: 20_000 })
const chrome = await page.evaluate(() => {
  const entryNodes = [...document.querySelectorAll('[data-qid^="battle:music:entry:"]')]
  return {
    banner: !!document.querySelector('[data-qid="battle:music:banner"]'),
    scrubber: !!document.querySelector('[data-qid="battle:music:scrubber"]'),
    noSpeaker: /NO SPEAKER CLAIM/i.test(document.querySelector('[data-qid="battle:music:no-speaker-claim"]')?.textContent ?? ''),
    disclaimer: /speaker|headphone|Decode/i.test(document.querySelector('[data-qid="battle:music:disclaimer"]')?.textContent ?? ''),
    nav: !!document.querySelector('[data-qid="battle:nav:music"]'),
    composerLive: document.querySelector('[data-qid="battle:music:composer-live"]')?.textContent ?? '',
    present: [...document.querySelectorAll('[data-qid^="battle:music:present:"]')].map((n) => n.textContent),
    notEmitted: [...document.querySelectorAll('[data-qid^="battle:music:not-emitted:"]')].map((n) => n.textContent),
    entries: entryNodes.map((node) => ({
      musicId: node.getAttribute('data-music-id'),
      playbackClass: node.getAttribute('data-playback-class'),
      oggUrl: node.getAttribute('data-ogg-url'),
      receiptId: node.getAttribute('data-receipt-id'),
    })),
    may: document.querySelector('[data-qid="battle:music:claim-may"]')?.textContent ?? '',
    mustNot: document.querySelector('[data-qid="battle:music:claim-must-not"]')?.textContent ?? '',
  }
})
record('10-banner', chrome.banner, 'banner')
record('10b-scrubber', chrome.scrubber, 'scrubber')
record('10c-no-speaker-badge', chrome.noSpeaker, 'no speaker')
record('10d-disclaimer', chrome.disclaimer, 'disclaimer')
record('11-nav', chrome.nav, 'nav')
record('12-composer-live-false', /composer_live:false/i.test(chrome.composerLive), chrome.composerLive)
record('13-entries-ui', chrome.entries.length === 2, JSON.stringify(chrome.entries))
record('14-promoted-only', chrome.entries.every((e) => e.playbackClass === 'promoted' && e.oggUrl?.startsWith('/battle-audio/promoted/v1/')), JSON.stringify(chrome.entries))
record('15-present-loop-motif', chrome.present.some((t) => /live_arena_loop/.test(t)) && chrome.present.some((t) => /motif:plague_nurgling/.test(t)), JSON.stringify(chrome.present))
record('16-not-emitted-terminal', chrome.notEmitted.some((t) => /exploit_death_stinger/.test(t)) && chrome.notEmitted.some((t) => /exploit_victory_stinger/.test(t)), JSON.stringify(chrome.notEmitted))
record('17-claim-boundary', /assets_promoted/.test(chrome.may) && /speaker_output|speaker|victory/i.test(chrome.mustNot), JSON.stringify({ may: chrome.may, mustNot: chrome.mustNot }))

await page.click('[data-qid="battle:music:arm"]')
await page.waitForTimeout(500)
let active = await page.evaluate(() => document.querySelector('[data-qid="battle:music:active"]')?.textContent ?? '')
record('18-armed-loop', /live_arena_loop/i.test(active), active)
await page.click('[data-qid="battle:music:seek-spawn"]')
await page.waitForTimeout(200)
await page.click('[data-qid="battle:music:play-due"]')
await page.waitForTimeout(700)
active = await page.evaluate(() => document.querySelector('[data-qid="battle:music:active"]')?.textContent ?? '')
record('19-armed-motif', /motif:plague_nurgling/i.test(active), active)
record('20-no-page-errors', errors.length === 0, JSON.stringify(errors.slice(0, 5)))
await page.screenshot({ path: resolve(outDir, '01-music-m1-schedule.png'), fullPage: true })
await browser.close()

const failed = checks.filter((item) => !item.pass)
await writeFile(
  resolve(outDir, 'summary.json'),
  JSON.stringify(
    {
      host,
      route,
      fixtureUrl,
      mocked: false,
      live: 'normalized_music_fixture_http_and_ui',
      composer_live: false,
      browser_playback_attempted: true,
      speaker_output_proven: false,
      checks,
      failed: failed.map((item) => item.id),
      passCount: checks.filter((item) => item.pass).length,
      total: checks.length,
    },
    null,
    2,
  ),
)
if (failed.length) {
  console.error(`prove:music-m1 FAILED ${failed.length}/${checks.length}`)
  process.exit(1)
}
console.log(`prove:music-m1 PASS ${checks.length}/${checks.length}`)
