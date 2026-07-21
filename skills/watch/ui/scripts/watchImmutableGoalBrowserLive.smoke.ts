import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'
import { chromium, type Browser, type Page } from 'playwright'
import { projectYoloTrackLabelAtTime } from '../src/yoloLabelProjection'
import {
  reserveLocalPort,
  runCommand,
  stopProcessTree,
  waitForHttpOk,
} from './proofUtils'

type ProcessHandle = {
  child: ChildProcess
  stdout: string
  stderr: string
}

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(uiRoot, '..', '..', '..')
const watchRoot = path.resolve(uiRoot, '..')

const memoryDaemonUrl = process.env.MEMORY_DAEMON_URL || 'http://127.0.0.1:8601'
const badSantaAssetUid = process.env.WATCH_IMMUTABLE_ASSET_UID || 'bad_santa_unrated_2003_brrip_xvidhd_720p_npw'
const badSantaRow9 = Number(process.env.WATCH_IMMUTABLE_ROW9 || 9)
const badSantaRow9Track = process.env.WATCH_IMMUTABLE_ROW9_TRACK_ID || 'track_2'
const proofAssetTitle = 'watch immutable proof asset'
const proofAssetUid = 'watch_immutable_proof_asset'
const proofRow10 = Number(process.env.WATCH_IMMUTABLE_ROW10 || 10)
const proofRow10Track = process.env.WATCH_IMMUTABLE_ROW10_TRACK_ID || 'track_15'

const badSantaClip = '/mnt/storage12tb/media/watch-frames/badsantaunrated2003brripxvidhd720p-npw/clips/segment_0009.mp4'
const proofClip = '/mnt/storage12tb/media/watch-frames/badsantaunrated2003brripxvidhd720p-npw/clips/segment_0010.mp4'
const badSantaMarcusCrop = path.join(
  watchRoot,
  'docs/architecture/generated/watch_identity_qdrant_marcus_eval',
  '20260704T172759115162Z_yolo_track_2_only/crops',
  'sample_15_12.515_marcus_detector_9_track_2_interpolated.png',
)

function repoRelative(filePath: string): string {
  return path.relative(repoRoot, filePath)
}

function qid(page: Page, value: string) {
  return page.locator(`[data-testid="${value}"]`)
}

function startProcess(command: string, args: string[], cwd: string, env: NodeJS.ProcessEnv): ProcessHandle {
  const child = spawn(command, args, {
    cwd,
    env,
    detached: process.platform !== 'win32',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const handle = { child, stdout: '', stderr: '' }
  child.stdout?.setEncoding('utf-8')
  child.stderr?.setEncoding('utf-8')
  child.stdout?.on('data', (chunk: string) => {
    handle.stdout = `${handle.stdout}${chunk}`.slice(-12_000)
  })
  child.stderr?.on('data', (chunk: string) => {
    handle.stderr = `${handle.stderr}${chunk}`.slice(-12_000)
  })
  return handle
}

async function assertMemoryHealth(): Promise<void> {
  const response = await fetch(`${memoryDaemonUrl}/health`, {
    headers: { 'X-Caller-Skill': 'watch' },
  })
  assert.equal(response.status, 200, `Memory health returned ${response.status}`)
  const data = await response.json().catch(() => null) as { ok?: boolean; status?: string } | null
  assert.ok(data?.ok === true || data?.status === 'ok', `Memory health was not ok: ${JSON.stringify(data)}`)
}

async function writeJson(filePath: string, value: unknown): Promise<void> {
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 })
}

function minimalReport(input: {
  title: string
  rowIndex: number
  timecode: string
  segment: string
  videoClipPath: string
  text: string
}) {
  return {
    watch_report: {
      title: input.title,
      duration_formatted: '00:00:24',
      frame_count: 1,
      sampling_mode: 'immutable-goal-live-fixture',
    },
    scene_elements: [
      {
        index: input.rowIndex,
        timecode: input.timecode,
        movie_segment: input.segment,
        video_clip_path: input.videoClipPath,
        text: input.text,
        srt_text: input.text,
        visual_description: input.text,
      },
    ],
    captions: { segment_count: 1 },
    transcript: { segment_count: 1 },
  }
}

function detectorCandidates(input: {
  assetUid: string
  rowIndex: number
  trackId: string
  candidates: Array<{ time: number; bbox: [number, number, number, number] }>
}) {
  return {
    schema: 'watch.detector_candidates.v1',
    asset_uid: input.assetUid,
    row_index: input.rowIndex,
    run_id: 'immutable-goal-live',
    source_width: 1280,
    source_height: 696,
    candidates: input.candidates.map((candidate, index) => ({
      id: `detector:${input.rowIndex}:${input.trackId}:${candidate.time}:${index}`,
      row_index: input.rowIndex,
      asset_uid: input.assetUid,
      track_id: input.trackId,
      detected_class: 'person',
      bbox: candidate.bbox,
      bbox_format: 'normalized_xyxy',
      time_seconds: candidate.time,
      media_time_seconds: candidate.time,
      confidence: 0.9,
      source_log: 'immutable-goal-live-fixture',
    })),
    total: input.candidates.length,
  }
}

async function startWatchStack(input: {
  reportPath: string
  detectorDir: string
  yoloDir: string
}): Promise<{
  apiBaseUrl: string
  uiBaseUrl: string
  api: ProcessHandle
  vite: ProcessHandle
}> {
  const apiPort = await reserveLocalPort()
  const uiPort = await reserveLocalPort()
  const apiBaseUrl = `http://127.0.0.1:${apiPort}`
  const uiBaseUrl = `http://127.0.0.1:${uiPort}`
  const api = startProcess('tsx', ['server/index.ts'], uiRoot, {
    ...process.env,
    WATCH_API_PORT: String(apiPort),
    WATCH_REPORT_PATH: input.reportPath,
    WATCH_DETECTOR_CANDIDATES_DIR: input.detectorDir,
    WATCH_YOLO_LABEL_DIR: input.yoloDir,
    MEMORY_DAEMON_URL: memoryDaemonUrl,
  })
  await waitForHttpOk(`${apiBaseUrl}/api/projects/watch/health`, 15_000)

  const vite = startProcess('npx', ['vite', '--host', '127.0.0.1', '--port', String(uiPort), '--strictPort'], uiRoot, {
    ...process.env,
    VITE_WATCH_API_TARGET: apiBaseUrl,
  })
  await waitForHttpOk(uiBaseUrl, 20_000)
  return { apiBaseUrl, uiBaseUrl, api, vite }
}

async function stopWatchStack(stack: { api: ProcessHandle; vite: ProcessHandle }): Promise<void> {
  await stopProcessTree(stack.vite.child)
  await stopProcessTree(stack.api.child)
}

async function setVideoTime(page: Page, seconds: number): Promise<void> {
  await qid(page, 'watch-clip-video').evaluate((node, value) => {
    const video = node as HTMLVideoElement
    video.pause()
    video.currentTime = value as number
    video.dispatchEvent(new Event('timeupdate', { bubbles: true }))
  }, seconds)
  await delay(200)
}

async function clickControl(page: Page, testId: string): Promise<void> {
  await qid(page, testId).evaluate((node) => {
    ;(node as HTMLElement).click()
  })
  await delay(250)
}

async function getJson(url: string, artifactPath?: string): Promise<any> {
  const response = await fetch(url, { headers: { 'X-Caller-Skill': 'watch' } })
  const text = await response.text()
  assert.ok(response.ok, `${url} returned ${response.status}: ${text}`)
  const json = JSON.parse(text)
  if (artifactPath) await writeJson(artifactPath, json)
  return json
}

async function postJson(url: string, body: Record<string, unknown>, artifactPath?: string): Promise<any> {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Caller-Skill': 'watch',
    },
    body: JSON.stringify(body),
  })
  const text = await response.text()
  assert.ok(response.ok, `${url} returned ${response.status}: ${text}`)
  const json = JSON.parse(text)
  if (artifactPath) await writeJson(artifactPath, json)
  return json
}

async function createLoopClipFromImage(imagePath: string, outputPath: string): Promise<void> {
  const result = await runCommand({
    command: 'ffmpeg',
    args: [
      '-y',
      '-loop', '1',
      '-i', imagePath,
      '-t', '2',
      '-vf', 'scale=ceil(iw/2)*2:ceil(ih/2)*2',
      '-pix_fmt', 'yuv420p',
      outputPath,
    ],
    cwd: repoRoot,
  })
  assert.equal(result.exit_code, 0, result.stderr || result.stdout)
}

async function row9SuggestionPhase(page: Page, proofDir: string, stack: { apiBaseUrl: string; uiBaseUrl: string }): Promise<void> {
  await page.goto(`${stack.uiBaseUrl}/#watch/clipRow=${badSantaRow9}`)
  await qid(page, 'watch-report-view').waitFor({ state: 'visible', timeout: 15_000 })
  await qid(page, `watch-open-annotation-${badSantaRow9}`).click()
  await qid(page, 'watch-clip-modal').waitFor({ state: 'visible', timeout: 15_000 })
  await setVideoTime(page, 0.5)
  await qid(page, `watch-yolo-track-${badSantaRow9Track}`).click()
  const suggestion = qid(page, `watch-suggestion-label-${badSantaRow9Track}`)
  await suggestion.waitFor({ state: 'visible', timeout: 20_000 })
  const text = (await suggestion.textContent()) || ''
  assert.match(text, /Marcus\?\s+0\.\d+/, `expected Marcus tentative suggestion, got ${text}`)
  const confidence = Number(text.match(/0\.\d+/)?.[0])
  assert.ok(confidence >= 0.82, `expected suggestion confidence >= 0.82, got ${confidence}`)
  assert.equal(await qid(page, `watch-accepted-label-${badSantaRow9Track}`).count(), 0)
  const crop = await readFile(badSantaMarcusCrop)
  const suggestionResponse = await postJson(`${stack.apiBaseUrl}/api/projects/watch/identity-suggestions`, {
    asset_uid: badSantaAssetUid,
    row_index: badSantaRow9,
    track_id: badSantaRow9Track,
    time_seconds: 0.5,
    image_data_url: `data:image/png;base64,${crop.toString('base64')}`,
    q: 'Who does this YOLO person crop most look like in Bad Santa row 9?',
  }, path.join(proofDir, 'api-row9-memory-suggestion.json'))
  assert.equal(suggestionResponse.suggestion?.character_name, 'Marcus')
  assert.ok(suggestionResponse.suggestion?.confidence >= 0.82)
  const receipt = await getJson(`${stack.apiBaseUrl}/api/projects/watch/yolo-labels?asset_uid=${encodeURIComponent(badSantaAssetUid)}&row_index=${badSantaRow9}`)
  assert.equal(receipt.events.filter((event: any) => event.action === 'accept').length, 0)
  await page.screenshot({ path: path.join(proofDir, '01-row9-tentative-marcus.png'), fullPage: false })
}

async function row10AcceptStopReassignPhase(page: Page, proofDir: string, stack: { apiBaseUrl: string; uiBaseUrl: string }): Promise<void> {
  await page.goto(`${stack.uiBaseUrl}/#watch/clipRow=${proofRow10}`)
  await qid(page, 'watch-report-view').waitFor({ state: 'visible', timeout: 15_000 })
  await qid(page, `watch-open-annotation-${proofRow10}`).click()
  await qid(page, 'watch-clip-modal').waitFor({ state: 'visible', timeout: 15_000 })

  await getJson(`${stack.apiBaseUrl}/api/projects/watch/yolo-labels/projected?asset_uid=${proofAssetUid}&row_index=${proofRow10}&track_id=${proofRow10Track}&time_seconds=0.5`, path.join(proofDir, 'api-row10-projection-before-accept.json'))

  await setVideoTime(page, 1.0)
  await qid(page, `watch-yolo-track-${proofRow10Track}`).click()
  await qid(page, `watch-character-select-${proofRow10Track}`).selectOption('Marcus')
  await clickControl(page, `watch-save-label-${proofRow10Track}`)
  await qid(page, `watch-identity-status-${proofRow10Track}`).waitFor({ state: 'visible', timeout: 15_000 })
  await qid(page, `watch-identity-status-${proofRow10Track}`).filter({ hasText: 'Marcus' }).waitFor({ state: 'visible', timeout: 15_000 })
  const projectionMarcus = await getJson(`${stack.apiBaseUrl}/api/projects/watch/yolo-labels/projected?asset_uid=${proofAssetUid}&row_index=${proofRow10}&track_id=${proofRow10Track}&time_seconds=1.2`, path.join(proofDir, 'api-row10-projection-after-marcus.json'))
  assert.equal(projectionMarcus.label?.characterName, 'Marcus')
  await page.screenshot({ path: path.join(proofDir, '02-row10-marcus-accepted.png'), fullPage: false })

  await setVideoTime(page, 1.79)
  await qid(page, `watch-yolo-track-${proofRow10Track}`).click()
  await page.locator('[data-qid="watch:clip-modal:inline-yolo-character-select"]').selectOption('__unassign_frame__')
  await delay(500)
  await setVideoTime(page, 2.02)
  const projectionStop = await getJson(`${stack.apiBaseUrl}/api/projects/watch/yolo-labels/projected?asset_uid=${proofAssetUid}&row_index=${proofRow10}&track_id=${proofRow10Track}&time_seconds=2.02`, path.join(proofDir, 'api-row10-projection-after-stop.json'))
  assert.equal(projectionStop.label, null)
  await qid(page, `watch-identity-status-${proofRow10Track}`).filter({ hasText: 'Unassigned' }).waitFor({ state: 'visible', timeout: 15_000 })
  await page.screenshot({ path: path.join(proofDir, '03-row10-after-stop-unassigned.png'), fullPage: false })

  await setVideoTime(page, 4.54)
  await qid(page, `watch-yolo-track-${proofRow10Track}`).click()
  await qid(page, `watch-character-select-${proofRow10Track}`).selectOption('Willie')
  await clickControl(page, `watch-save-label-${proofRow10Track}`)
  await qid(page, `watch-identity-status-${proofRow10Track}`).filter({ hasText: 'Willie' }).waitFor({ state: 'visible', timeout: 15_000 })
  const projectionWillie = await getJson(`${stack.apiBaseUrl}/api/projects/watch/yolo-labels/projected?asset_uid=${proofAssetUid}&row_index=${proofRow10}&track_id=${proofRow10Track}&time_seconds=5`, path.join(proofDir, 'api-row10-projection-after-willie.json'))
  assert.equal(projectionWillie.label?.characterName, 'Willie')
  await page.screenshot({ path: path.join(proofDir, '04-row10-willie-reassigned.png'), fullPage: false })

  await page.reload()
  await qid(page, 'watch-report-view').waitFor({ state: 'visible', timeout: 15_000 })
  await qid(page, 'watch-clip-modal').waitFor({ state: 'visible', timeout: 15_000 })
  await setVideoTime(page, 1.2)
  await qid(page, `watch-yolo-track-${proofRow10Track}`).click()
  await qid(page, `watch-identity-status-${proofRow10Track}`).filter({ hasText: 'Marcus' }).waitFor({ state: 'visible', timeout: 15_000 })
  await setVideoTime(page, 2.02)
  await qid(page, `watch-identity-status-${proofRow10Track}`).filter({ hasText: 'Unassigned' }).waitFor({ state: 'visible', timeout: 15_000 })
  await setVideoTime(page, 5.0)
  await qid(page, `watch-identity-status-${proofRow10Track}`).filter({ hasText: 'Willie' }).waitFor({ state: 'visible', timeout: 15_000 })
  await page.screenshot({ path: path.join(proofDir, '05-row10-reloaded.png'), fullPage: false })

  const finalReceipt = await getJson(`${stack.apiBaseUrl}/api/projects/watch/yolo-labels?asset_uid=${proofAssetUid}&row_index=${proofRow10}`, path.join(proofDir, 'api-row10-final-receipt.json'))
  assert.equal(finalReceipt.events.length, 3)
  assert.deepEqual(finalReceipt.events.map((event: any) => event.sequence), [1, 2, 3])
  assert.equal(finalReceipt.events[0].action, 'accept')
  assert.equal(finalReceipt.events[0].character_name, 'Marcus')
  assert.equal(finalReceipt.events[1].action, 'reject_box')
  assert.equal(finalReceipt.events[2].action, 'accept')
  assert.equal(finalReceipt.events[2].character_name, 'Willie')
  assert.ok(finalReceipt.events.every((event: any) => event.memory_sync?.state))
  assert.ok(finalReceipt.events.filter((event: any) => event.action === 'accept').every((event: any) => event.memory_sync.state === 'stored'))
  assert.equal(finalReceipt.labels[proofRow10Track]?.characterName, 'Willie')

  const sharedProjection = projectYoloTrackLabelAtTime({
    trackId: proofRow10Track,
    timeSeconds: 2.02,
    events: finalReceipt.events,
    labels: finalReceipt.labels,
  })
  assert.equal(sharedProjection, null)

  const memory = await postJson(`${memoryDaemonUrl}/recall`, {
    q: `Watch YOLO ${proofAssetUid} row ${proofRow10} ${proofRow10Track} Willie`,
    collections: ['watch_yolo_track_labels'],
    k: 5,
  })
  const memoryText = JSON.stringify(memory)
  assert.match(memoryText, /watch_yolo_track_labels/)
  assert.match(memoryText, /Willie|watch_yolo_track_label_event/)
}

async function main(): Promise<void> {
  assert.ok(existsSync(badSantaClip), `missing live Bad Santa row-9 clip: ${badSantaClip}`)
  assert.ok(existsSync(badSantaMarcusCrop), `missing live Bad Santa row-9 Marcus crop: ${badSantaMarcusCrop}`)
  assert.ok(existsSync(proofClip), `missing row-10 proof clip: ${proofClip}`)
  await assertMemoryHealth()

  const requestedProofDir = process.env.WATCH_PROOF_DIR
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), 'watch-immutable-goal-'))
  const proofDir = requestedProofDir ? path.resolve(requestedProofDir) : path.join(tempRoot, 'proof')
  await writeFile(path.join(tempRoot, '.keep'), '')

  let browser: Browser | null = null
  let row9Stack: Awaited<ReturnType<typeof startWatchStack>> | null = null
  let row10Stack: Awaited<ReturnType<typeof startWatchStack>> | null = null
  try {
    const row9Dir = path.join(tempRoot, 'row9')
    const row9Report = path.join(row9Dir, 'report.json')
    const row9DetectorDir = path.join(row9Dir, 'detectors')
    const row9YoloDir = path.join(row9Dir, 'receipts')
    await mkdtemp(path.join(row9Dir, 'init-')).catch(async () => undefined)
    await rm(row9Dir, { recursive: true, force: true })
    await writeFile(path.join(tempRoot, 'proof-dir.txt'), proofDir)
    await writeFile(path.join(tempRoot, 'repo-relative-proof-dir.txt'), repoRelative(proofDir))
    const row9Clip = path.join(tempRoot, 'row9-marcus-crop-loop.mp4')
    await createLoopClipFromImage(badSantaMarcusCrop, row9Clip)
    await import('node:fs/promises').then(async ({ mkdir }) => {
      await mkdir(row9DetectorDir, { recursive: true })
      await mkdir(row9YoloDir, { recursive: true })
      await mkdir(proofDir, { recursive: true })
    })
    await writeJson(row9Report, minimalReport({
      title: badSantaAssetUid.replace(/_/g, ' '),
      rowIndex: badSantaRow9,
      timecode: '00:00:00',
      segment: '00:00:00-00:00:02',
      videoClipPath: row9Clip,
      text: 'Marcus appears in the Bad Santa row 9 live suggestion canary.',
    }))
    await writeJson(path.join(row9DetectorDir, `detector_candidates_row${badSantaRow9}.json`), detectorCandidates({
      assetUid: badSantaAssetUid,
      rowIndex: badSantaRow9,
      trackId: badSantaRow9Track,
      candidates: [
        { time: 0.5, bbox: [0, 0, 1, 1] },
      ],
    }))

    browser = await chromium.launch({ headless: true })
    row9Stack = await startWatchStack({ reportPath: row9Report, detectorDir: row9DetectorDir, yoloDir: row9YoloDir })
    const row9Page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    await row9SuggestionPhase(row9Page, proofDir, row9Stack)
    await row9Page.close()
    await stopWatchStack(row9Stack)
    row9Stack = null

    const row10Dir = path.join(tempRoot, 'row10')
    const row10Report = path.join(row10Dir, 'report.json')
    const row10DetectorDir = path.join(row10Dir, 'detectors')
    const row10YoloDir = path.join(row10Dir, 'receipts')
    await import('node:fs/promises').then(async ({ mkdir }) => {
      await mkdir(row10DetectorDir, { recursive: true })
      await mkdir(row10YoloDir, { recursive: true })
    })
    await writeJson(row10Report, minimalReport({
      title: proofAssetTitle,
      rowIndex: proofRow10,
      timecode: '00:00:00',
      segment: '00:00:00-00:00:08',
      videoClipPath: proofClip,
      text: 'Marcus and Willie are proof-only names for immutable row 10 accept stop reassign browser flow.',
    }))
    await writeJson(path.join(row10DetectorDir, `detector_candidates_row${proofRow10}.json`), detectorCandidates({
      assetUid: proofAssetUid,
      rowIndex: proofRow10,
      trackId: proofRow10Track,
      candidates: [
        { time: 1.0, bbox: [0.18, 0.12, 0.42, 0.9] },
        { time: 1.79, bbox: [0.2, 0.12, 0.44, 0.9] },
        { time: 4.54, bbox: [0.58, 0.12, 0.82, 0.9] },
      ],
    }))

    row10Stack = await startWatchStack({ reportPath: row10Report, detectorDir: row10DetectorDir, yoloDir: row10YoloDir })
    const row10Page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    await row10AcceptStopReassignPhase(row10Page, proofDir, row10Stack)
    await row10Page.close()
  } finally {
    if (row10Stack) await stopWatchStack(row10Stack)
    if (row9Stack) await stopWatchStack(row9Stack)
    if (browser) await browser.close()
    if (!requestedProofDir) await rm(tempRoot, { recursive: true, force: true })
  }
}

main()
  .then(() => {
    console.log('watchImmutableGoalBrowserLive smoke passed')
  })
  .catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
