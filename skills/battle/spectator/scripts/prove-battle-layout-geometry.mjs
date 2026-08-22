#!/usr/bin/env node
/**
 * Live geometric proof for Battle spectator chrome.
 * Critical layout must use real CSS (not unscanned Tailwind arbitrary grids).
 * mocked: no — exercises the running host via Playwright.
 */
import { chromium } from 'playwright'
import { resolveBattleProveHost } from './battle-prove-host.mjs'

const host = await resolveBattleProveHost()
const url = `${host}/#battle/receipt?engine=pixi&fixture=battle-004-adaptive-lineage-v13`
const checks = []

function record(id, pass, detail) {
  checks.push({ id, pass, detail })
  if (!pass) console.error(`FAIL ${id}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`)
}

function overlaps(a, b) {
  return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom)
}

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1672, height: 941 } })
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForSelector('[data-qid="battle:header:receipt"]', { timeout: 20000 })
await page.waitForTimeout(1200)

const proof = await page.evaluate(() => {
  const box = (el) => {
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height }
  }
  const overlaps = (a, b) => a && b && !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom)

  const header = document.querySelector('[data-qid="battle:header:receipt"]')
  const score = document.querySelector('[data-qid="battle:header:score"]')
  const facts = document.querySelector('[data-qid="battle:header:facts"]')
  const title = header?.querySelector('h1')
  const subtitle = header?.querySelector('p')
  const main = document.querySelector('.battle-mockup-main')
  const raceCard = main?.children?.[1]?.querySelector(':scope > *')
  const centerWrap = main?.children?.[1]
  const agentWrap = main?.children?.[2]
  const scroll = document.querySelector('[data-qid="battle:timeline:scroll"]')
  const scrub = document.querySelector('[data-qid="battle:timeline:scrub"]')

  const headerCols = header ? getComputedStyle(header).gridTemplateColumns : ''
  const factsCols = facts ? getComputedStyle(facts).gridTemplateColumns : ''
  const mainCols = main ? getComputedStyle(main).gridTemplateColumns : ''
  const colCount = (cols) => (cols || '').trim().split(/\s+/).filter(Boolean).length

  const factClip = [...(facts?.children || [])].map((el) => {
    const label = el.querySelector('div')
    return {
      label: label?.textContent?.trim(),
      clipped: label ? label.scrollWidth > label.clientWidth + 1 : false,
    }
  })

  const nav = [...document.querySelectorAll('.battle-proof-nav button, .battle-proof-nav a, [data-qid^="battle:proof-nav"] button')]
  const navBoxes = nav.map((el) => ({ text: (el.textContent || '').trim().slice(0, 40), ...box(el) }))
  const navHits = []
  for (let i = 0; i < navBoxes.length; i++) {
    for (let j = i + 1; j < navBoxes.length; j++) {
      if (overlaps(navBoxes[i], navBoxes[j])) navHits.push([navBoxes[i].text, navBoxes[j].text])
    }
  }

  const vpH = window.innerHeight
  const raceBox = box(raceCard)
  const centerBox = box(centerWrap)
  const agentBox = box(agentWrap)
  const scrollBox = box(scroll)
  const scrubBox = box(scrub)

  return {
    headerColCount: colCount(headerCols),
    headerCols,
    factsColCount: colCount(factsCols),
    mainColCount: colCount(mainCols),
    scorePosition: score ? getComputedStyle(score).position : null,
    scoreTitleOverlap: overlaps(box(title), box(score)),
    scoreSubtitleOverlap: overlaps(box(subtitle), box(score)),
    difficultyClipped: factClip.find((f) => f.label === 'Difficulty')?.clipped ?? true,
    factClip,
    navHits,
    raceFillsCenter: !!(raceBox && centerBox && Math.abs(raceBox.height - centerBox.height) <= 8),
    raceHeight: raceBox?.height ?? 0,
    centerHeight: centerBox?.height ?? 0,
    agentInViewport: !!(agentBox && agentBox.right <= window.innerWidth + 2 && agentBox.bottom <= vpH + 48),
    scrollHasGrid: scroll ? /linear-gradient/i.test(getComputedStyle(scroll).backgroundImage) : false,
    scrollHeight: scrollBox?.height ?? 0,
    scrubHeight: scrubBox?.height ?? 0,
    scrubWidth: scrubBox?.width ?? 0,
  }
})

record('1-header-three-columns', proof.headerColCount === 3, proof.headerCols)
record('2-facts-five-columns', proof.factsColCount === 5, proof.factsCols ?? proof.factClip)
record('3-main-three-columns', proof.mainColCount === 3, proof.mainCols)
record('4-score-static', proof.scorePosition === 'static', proof.scorePosition)
record('5-no-score-title-overlap', proof.scoreTitleOverlap === false, { scoreTitleOverlap: proof.scoreTitleOverlap })
record('6-no-score-subtitle-overlap', proof.scoreSubtitleOverlap === false, { scoreSubtitleOverlap: proof.scoreSubtitleOverlap })
record('7-difficulty-label-unclipped', proof.difficultyClipped === false, proof.factClip)
record('8-no-nav-collisions', proof.navHits.length === 0, proof.navHits)
record('9-race-fills-center-height', proof.raceFillsCenter, { race: proof.raceHeight, center: proof.centerHeight })
record('10-agent-pane-in-viewport', proof.agentInViewport, true)
record('11-scroll-track-atmosphere', proof.scrubHeight > 200 && proof.scrubWidth > 900, { scrollHasGrid: proof.scrollHasGrid, scrollHeight: proof.scrollHeight, scrubHeight: proof.scrubHeight, scrubWidth: proof.scrubWidth })

await browser.close()
const failed = checks.filter((c) => !c.pass).length
console.log(JSON.stringify({ pass: failed === 0, checks, mocked: false, live: true, host, url }, null, 2))
if (failed) process.exit(1)
console.log('BATTLE_PROVE_LAYOUT_GEOMETRY_PASS')
