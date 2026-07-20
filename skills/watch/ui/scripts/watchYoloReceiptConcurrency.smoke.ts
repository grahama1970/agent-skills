import assert from 'node:assert/strict'
import { spawn, type ChildProcess } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { createServer } from 'node:net'
import type { AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const uiRoot = path.resolve(scriptDir, '..')
const assetUid = 'watch_concurrency_fixture'
const rowIndex = 12
const trackId = 'track_40'

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

async function main(): Promise<void> {
  const receiptDir = await mkdtemp(path.join(tmpdir(), 'watch-yolo-concurrency-'))
  const apiPort = await unusedLocalPort()
  const unavailableMemoryPort = await unusedLocalPort()
  const baseUrl = `http://127.0.0.1:${apiPort}`
  const tsxCommand = process.platform === 'win32' ? 'tsx.cmd' : 'tsx'
  const child = spawn(tsxCommand, ['server/index.ts'], {
    cwd: uiRoot,
    env: {
      ...process.env,
      WATCH_API_PORT: String(apiPort),
      WATCH_YOLO_LABEL_DIR: receiptDir,
      MEMORY_DAEMON_URL: `http://127.0.0.1:${unavailableMemoryPort}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  try {
    await waitForApi(baseUrl, child)
    await Promise.all(Array.from({ length: 40 }, async (_, index) => {
      const time = 1
      const action = index % 2 === 0 ? 'accept' : 'reject_box'
      const body: Record<string, unknown> = {
        action,
        asset_uid: assetUid,
        row_index: rowIndex,
        track_id: trackId,
        box_key: `${trackId}@${Math.round(time * 100)}-${index}`,
        time_seconds: time,
        timecode: '00:12',
        movie_segment: '00:12-00:24',
      }
      if (action === 'accept') {
        body.character_name = index % 4 === 0 ? 'Marcus' : 'Willie'
        body.actor_name = body.character_name === 'Marcus' ? 'Tony Cox' : 'Billy Bob Thornton'
        body.confidence = 1
      }
      const response = await fetch(`${baseUrl}/api/projects/watch/yolo-labels`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': `concurrent-${index}`,
        },
        body: JSON.stringify(body),
      })
      const text = await response.text()
      assert.equal(response.status, 200, text)
    }))

    const response = await fetch(`${baseUrl}/api/projects/watch/yolo-labels?asset_uid=${assetUid}&row_index=${rowIndex}`)
    const receipt = await response.json() as {
      revision: number
      receipt_path: string
      events: Array<{ id: string; sequence: number; memory_sync?: { state?: string } }>
    }
    assert.equal(receipt.events.length, 40)
    assert.equal(new Set(receipt.events.map((event) => event.id)).size, 40)
    assert.deepEqual(receipt.events.map((event) => event.sequence), Array.from({ length: 40 }, (_, index) => index + 1))
    assert.ok(receipt.revision >= 40)
    assert.equal(receipt.events.every((event) => event.memory_sync?.state === 'failed'), true)

    const persisted = JSON.parse(await readFile(path.join(receiptDir, receipt.receipt_path), 'utf-8')) as { events: unknown[] }
    assert.equal(persisted.events.length, 40)
  } finally {
    await stopChild(child)
    await rm(receiptDir, { recursive: true, force: true })
  }
}

main()
  .then(() => {
    console.log('watchYoloReceiptConcurrency smoke passed')
  })
  .catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
