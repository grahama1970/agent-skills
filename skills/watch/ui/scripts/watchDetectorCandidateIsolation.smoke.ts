import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')

async function unusedLocalPort(): Promise<number> {
  const reservation = createServer()
  await new Promise<void>((resolve, reject) => {
    reservation.once('error', reject)
    reservation.listen(0, '127.0.0.1', resolve)
  })
  const address = reservation.address() as AddressInfo | null
  assert.ok(address)
  await new Promise<void>((resolve, reject) => reservation.close((error) => error ? reject(error) : resolve()))
  return address.port
}

async function stopChild(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null) return
  const closeEvent = once(child, 'close')
  child.kill('SIGTERM')
  await Promise.race([closeEvent, delay(2_000)])
  if (child.exitCode === null) {
    const forcedClose = once(child, 'close')
    child.kill('SIGKILL')
    await forcedClose
  }
}

async function waitForApi(baseUrl: string, child: ChildProcess): Promise<void> {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Watch API exited before readiness: ${child.exitCode}`)
    try {
      const response = await fetch(`${baseUrl}/api/projects/watch/health`)
      if (response.ok) return
    } catch {
      // wait
    }
    await delay(50)
  }
  throw new Error('Watch API did not become ready')
}

async function writeFixture(root: string, dirName: string, assetUid: string, runId: string): Promise<string> {
  const dir = path.join(root, dirName)
  await mkdir(dir, { recursive: true })
  const fixturePath = path.join(dir, 'detector_candidates_row9.json')
  await writeFile(fixturePath, JSON.stringify({
    schema: 'watch.detector_candidates.v1',
    asset_uid: assetUid,
    row_index: 9,
    run_id: runId,
    candidates: [{
      id: `${assetUid}-${runId}`,
      row_index: 9,
      asset_uid: assetUid,
      track_id: 'track_2',
      detected_class: 'person',
      bbox: [0.1, 0.1, 0.2, 0.4],
      bbox_format: 'normalized_xyxy',
      time_seconds: 1,
    }],
    total: 1,
  }, null, 2))
  return fixturePath
}

async function main(): Promise<void> {
  const candidatesRoot = await mkdtemp(path.join(tmpdir(), 'watch-detector-candidates-'))
  const receiptDir = await mkdtemp(path.join(tmpdir(), 'watch-detector-labels-'))
  const apiPort = await unusedLocalPort()
  const baseUrl = `http://127.0.0.1:${apiPort}`
  const tsxCommand = process.platform === 'win32' ? 'tsx.cmd' : 'tsx'
  const child = spawn(tsxCommand, ['server/index.ts'], {
    cwd: uiRoot,
    env: {
      ...process.env,
      WATCH_API_PORT: String(apiPort),
      WATCH_YOLO_LABEL_DIR: receiptDir,
      WATCH_DETECTOR_CANDIDATES_DIR: candidatesRoot,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  try {
    const pathA1 = await writeFixture(candidatesRoot, 'asset-a-run-1', 'asset_A', 'run_1')
    await writeFixture(candidatesRoot, 'asset-b-run-1', 'asset_B', 'run_1')
    const pathA2 = await writeFixture(candidatesRoot, 'asset-a-run-2', 'asset_A', 'run_2')
    await waitForApi(baseUrl, child)

    async function get(params: URLSearchParams): Promise<{ status: number; json: any }> {
      const response = await fetch(`${baseUrl}/api/projects/watch/detector-candidates?${params}`)
      return { status: response.status, json: await response.json() }
    }

    const assetA1 = await get(new URLSearchParams({ asset_uid: 'asset_A', row_index: '9', run_id: 'run_1' }))
    assert.equal(assetA1.status, 200)
    assert.equal(assetA1.json.asset_uid, 'asset_A')
    assert.equal(assetA1.json.run_id, 'run_1')

    const assetB = await get(new URLSearchParams({ asset_uid: 'asset_B', row_index: '9' }))
    assert.equal(assetB.status, 200)
    assert.equal(assetB.json.asset_uid, 'asset_B')

    const ambiguous = await get(new URLSearchParams({ asset_uid: 'asset_A', row_index: '9' }))
    assert.equal(ambiguous.status, 409)
    assert.equal(ambiguous.json.code, 'DETECTOR_CANDIDATES_AMBIGUOUS')
    assert.deepEqual(ambiguous.json.candidate_paths, [pathA1, pathA2].sort((a, b) => a.localeCompare(b)))
    assert.equal(JSON.stringify(ambiguous.json).includes('asset_B'), false)

    const missing = await get(new URLSearchParams({ asset_uid: 'asset_C', row_index: '9' }))
    assert.equal(missing.status, 404)
    assert.equal(missing.json.code, 'DETECTOR_CANDIDATES_NOT_FOUND')
  } finally {
    await stopChild(child)
    await rm(candidatesRoot, { recursive: true, force: true })
    await rm(receiptDir, { recursive: true, force: true })
  }
}

main()
  .then(() => {
    console.log('watchDetectorCandidateIsolation smoke passed')
  })
  .catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
