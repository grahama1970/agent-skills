import express from 'express'
import { readFileSync, existsSync, statSync, realpathSync, readdirSync } from 'fs'
import { createReadStream } from 'fs'
import { spawn } from 'child_process'
import path from 'path'
import { fileURLToPath } from 'url'
import crypto from 'node:crypto'
import type { WatchServerConfig } from './config'
import { WATCH_SKILL_DIR_PATH } from './config'
import {
  DetectorCandidatesAmbiguousError,
  DetectorCandidatesNotFoundError,
  resolveDetectorCandidates,
} from './detectorCandidateStore'
import {
  IdempotencyConflictError,
  MalformedYoloReceiptError,
  OutOfOrderTrackEventError,
  YoloReceiptStore,
  eventIdFor,
  fingerprintFor,
  type YoloLabelAction,
} from './yoloReceiptStore'
import { deliverYoloEventToMemory, retryYoloMemorySync, withYoloMemorySyncClaim } from './yoloMemorySync'
import { projectYoloTrackLabelAtTime } from '../src/yoloLabelProjection'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export function createWatchApp(config: WatchServerConfig): express.Express {
const app = express()

app.use(express.json({ limit: '2mb' }))

const WATCH_REPORT_PATH = config.reportPath
const WATCH_FRAMES_DIR = config.framesDir
const MEMORY_DAEMON = config.memoryDaemonUrl
const WATCH_SKILL_DIR = WATCH_SKILL_DIR_PATH
const WATCH_TRACKER_EVENTS_PATH = config.trackerEventsPath
const WATCH_TRACKER_SCRIPT = config.trackerScriptPath
const WATCH_TRACKER_MODEL = config.trackerModelPath
const WATCH_YOLO_LABEL_DIR = config.yoloLabelDir
const WATCH_OVERLAY_PAYLOAD_PATH = config.overlayPayloadPath
const WATCH_DETECTOR_CANDIDATES_DIR = config.detectorCandidatesDir
const yoloReceiptStore = new YoloReceiptStore(WATCH_YOLO_LABEL_DIR)

if (config.retryMemorySyncOnStart) {
  setTimeout(() => {
    void retryYoloMemorySync({ store: yoloReceiptStore, memoryDaemonUrl: MEMORY_DAEMON })
  }, 0)
}

function safeFilePart(value: unknown, fallback: string): string {
  const raw = typeof value === 'string' && value.trim() ? value.trim() : fallback
  return raw.replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || fallback
}

function yoloLabelFilePath(assetUid: unknown, rowIndex: unknown): string {
  const asset = safeFilePart(assetUid, 'watch_asset')
  const row = Number.isFinite(Number(rowIndex)) ? String(Number(rowIndex)).padStart(4, '0') : 'unknown'
  return path.join(WATCH_YOLO_LABEL_DIR, `${asset}_row${row}.json`)
}

function yoloBoxInstanceKey(trackId: string, timeSeconds: unknown): string {
  const seconds = Number.isFinite(Number(timeSeconds)) ? Math.max(0, Number(timeSeconds)) : 0
  return `${trackId}@${Math.round(seconds * 100)}`
}

function readYoloLabelReceipt(assetUid: unknown, rowIndex: unknown): any {
  const receiptPath = yoloLabelFilePath(assetUid, rowIndex)
  if (!existsSync(receiptPath)) {
    return {
      schema: 'watch.yolo_track_labels.v1',
      asset_uid: assetUid || null,
      row_index: rowIndex ?? null,
      labels: {},
      box_rejections: {},
      events: [],
      receipt_path: receiptPath,
      updated_at: null,
    }
  }
  return JSON.parse(readFileSync(receiptPath, 'utf-8'))
}

function findDetectorCandidatesFile(rowIndex: number): string | null {
  const target = `detector_candidates_row${rowIndex}.json`
  const stack = [WATCH_DETECTOR_CANDIDATES_DIR]
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) continue
    let entries
    try {
      entries = readdirSync(current, { withFileTypes: true })
    } catch {
      continue
    }
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name)
      if (entry.isDirectory()) {
        stack.push(fullPath)
      } else if (entry.isFile() && entry.name === target) {
        return fullPath
      }
    }
  }
  return null
}

async function storeYoloLabelInMemory(document: Record<string, unknown>): Promise<{ ok: boolean; error?: string }> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8_000)
  try {
    const resp = await fetch(`${MEMORY_DAEMON}/store`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Caller-Skill': 'watch',
      },
      signal: controller.signal,
      body: JSON.stringify({
        collection: 'watch_yolo_track_labels',
        document,
      }),
    })
    if (!resp.ok) return { ok: false, error: `memory_store_http_${resp.status}` }
    return { ok: true }
  } catch (err) {
    return { ok: false, error: String(err) }
  } finally {
    clearTimeout(timeout)
  }
}

// Serve report JSON
app.get('/api/projects/watch/report', async (_req, res) => {
  try {
    const raw = readFileSync(WATCH_REPORT_PATH, 'utf-8')
    res.json(JSON.parse(raw))
  } catch (err) {
    res.status(500).json({ error: String(err), report_path: WATCH_REPORT_PATH })
  }
})

app.get('/api/projects/watch/health', (_req, res) => {
  res.json({
    schema: 'watch.api_health.v1',
    status: 'ok',
  })
})

app.get('/api/projects/watch/overlay-payload', async (req, res) => {
  const requestedPath = typeof req.query.path === 'string' && req.query.path.trim()
    ? req.query.path.trim()
    : WATCH_OVERLAY_PAYLOAD_PATH

  try {
    const realPayloadPath = realpathSync(requestedPath)
    const realWatchSkillDir = realpathSync(WATCH_SKILL_DIR)
    const realTmpDir = realpathSync('/tmp')
    const allowed = realPayloadPath.startsWith(`${realWatchSkillDir}${path.sep}`) ||
      realPayloadPath.startsWith(`${realTmpDir}${path.sep}`)

    if (!allowed) {
      res.status(403).json({ error: 'overlay payload path is outside allowed roots', path: requestedPath })
      return
    }

    const raw = readFileSync(realPayloadPath, 'utf-8')
    const payload = JSON.parse(raw)
    const schema = payload?.schema || payload?.schema_version
    if (schema !== 'watch.ui_overlay_payload.v1') {
      res.status(422).json({
        error: 'unexpected overlay payload schema',
        schema: schema || null,
        path: realPayloadPath,
      })
      return
    }
    res.json(payload)
  } catch (err) {
    res.status(404).json({
      error: String(err),
      path: requestedPath,
      default_path: WATCH_OVERLAY_PAYLOAD_PATH,
    })
  }
})

app.get('/api/projects/watch/detector-candidates', async (req, res) => {
  const rowIndex = typeof req.query.row_index === 'string' ? Number(req.query.row_index) : NaN
  const assetUid = typeof req.query.asset_uid === 'string' ? req.query.asset_uid : ''
  const runId = typeof req.query.run_id === 'string' && req.query.run_id.trim() ? req.query.run_id.trim() : undefined
  if (!assetUid || !Number.isFinite(rowIndex)) {
    res.status(400).json({ error: 'asset_uid and row_index are required' })
    return
  }

  try {
    const resolved = await resolveDetectorCandidates({
      rootDir: WATCH_DETECTOR_CANDIDATES_DIR,
      assetUid,
      rowIndex,
      runId,
    })
    res.json({ ...resolved.payload, source_path: resolved.path })
  } catch (err) {
    if (err instanceof DetectorCandidatesAmbiguousError) {
      res.status(409).json({
        code: err.code,
        error: err.message,
        candidate_paths: err.candidatePaths,
        candidate_run_ids: err.candidateRunIds,
      })
      return
    }
    if (err instanceof DetectorCandidatesNotFoundError) {
      res.status(404).json({
        code: err.code,
        schema: 'watch.detector_candidates.v1',
        row_index: rowIndex,
        asset_uid: assetUid,
        candidates: [],
        total: 0,
        error: err.message,
      })
      return
    }
    res.status(500).json({ error: String(err) })
  }
})

// Serve static media files
const MEDIA_ROOTS = ['/tmp', WATCH_FRAMES_DIR]

function isAllowedMediaPath(rawPath: string): boolean {
  try {
    const real = require.resolve(rawPath) // this won't work, use fs.realpathSync
    return true
  } catch { return false }
}

app.use('/api/projects/watch/static/tmp', express.static('/tmp', {
  acceptRanges: true,
  fallthrough: false,
  setHeaders: (res) => {
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin')
  },
}))

app.use('/api/projects/watch/static/watch-frames', express.static(WATCH_FRAMES_DIR, {
  acceptRanges: true,
  fallthrough: false,
  setHeaders: (res) => {
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin')
  },
}))

// Media proxy for arbitrary paths
app.get('/api/projects/watch/media', async (req, res) => {
  const rawPath = typeof req.query.path === 'string' ? req.query.path : ''
  if (!rawPath || !rawPath.startsWith('/')) {
    res.status(400).json({ error: 'absolute path required' })
    return
  }
  serveMediaFile(rawPath, req, res)
})

// Event-backed tracker stream. This replays live YOLO/ByteTrack event artifacts
// through the same SSE shape the modal will use for an active tracker process.
app.get('/api/projects/watch/tracker-events/stream', async (req, res) => {
  const mode = typeof req.query.mode === 'string' ? req.query.mode : 'replay'
  const segmentId = typeof req.query.segment_id === 'string' ? req.query.segment_id : ''
  const assetUid = typeof req.query.asset_uid === 'string' ? req.query.asset_uid : ''
  const streamId = typeof req.query.stream_id === 'string' ? req.query.stream_id : ''
  const sourcePath = typeof req.query.video_path === 'string' ? req.query.video_path : ''
  const startSeconds = typeof req.query.start_seconds === 'string' ? req.query.start_seconds : ''
  const maxEvents = typeof req.query.max_events === 'string' ? req.query.max_events : '200'
  const candidateName = typeof req.query.candidate_name === 'string' ? req.query.candidate_name : ''
  const candidateActorName = typeof req.query.candidate_actor_name === 'string' ? req.query.candidate_actor_name : ''

  if (mode === 'live') {
    streamLiveTrackerEvents({
      req,
      res,
      sourcePath,
      segmentId,
      assetUid,
      streamId,
      startSeconds,
      maxEvents,
      candidateName,
      candidateActorName,
    })
    return
  }

  const eventsPath = typeof req.query.path === 'string' ? req.query.path : WATCH_TRACKER_EVENTS_PATH

  if (!eventsPath.startsWith(WATCH_SKILL_DIR) && !eventsPath.startsWith('/tmp')) {
    res.status(403).json({ error: 'tracker event path outside allowed roots' })
    return
  }
  if (!existsSync(eventsPath)) {
    res.status(404).json({ error: 'tracker event log not found', events_path: eventsPath })
    return
  }

  const events = readTrackerEvents(eventsPath).filter((event) => {
    if (segmentId && event.segment_id !== segmentId) return false
    if (assetUid && event.asset_uid !== assetUid) return false
    return true
  })

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache, no-transform')
  res.setHeader('Connection', 'keep-alive')
  res.flushHeaders?.()

  res.write(`event: meta\ndata: ${JSON.stringify({
    schema: 'watch.tracker_event_stream.v1',
    status: events.length > 0 ? 'REPLAYING_EVENT_LOG' : 'NO_MATCHING_EVENTS',
    source: eventsPath,
    total_events: events.length,
    segment_id: segmentId || null,
    asset_uid: assetUid || null,
  })}\n\n`)

  if (events.length === 0) {
    res.write(`event: done\ndata: ${JSON.stringify({ status: 'NO_MATCHING_EVENTS' })}\n\n`)
    res.end()
    return
  }

  let index = 0
  const interval = setInterval(() => {
    if (index >= events.length) {
      clearInterval(interval)
      res.write(`event: done\ndata: ${JSON.stringify({ status: 'STREAM_COMPLETE', total_events: events.length })}\n\n`)
      res.end()
      return
    }
    res.write(`event: track_update\ndata: ${JSON.stringify(events[index])}\n\n`)
    index += 1
  }, 90)

  req.on('close', () => clearInterval(interval))
})

function streamLiveTrackerEvents({
  req,
  res,
  sourcePath,
  segmentId,
  assetUid,
  streamId,
  startSeconds,
  maxEvents,
  candidateName,
  candidateActorName,
}: {
  req: express.Request
  res: express.Response
  sourcePath: string
  segmentId: string
  assetUid: string
  streamId: string
  startSeconds: string
  maxEvents: string
  candidateName: string
  candidateActorName: string
}) {
  if (!sourcePath || !sourcePath.startsWith('/')) {
    res.status(400).json({ error: 'absolute video_path required for live tracker stream' })
    return
  }

  let realSource: string
  try {
    realSource = realpathSync(sourcePath)
  } catch {
    res.status(404).json({ error: 'tracker source not found', video_path: sourcePath })
    return
  }

  if (!MEDIA_ROOTS.some(root => realSource.startsWith(root))) {
    res.status(403).json({ error: 'tracker source outside allowed roots' })
    return
  }

  const args = [
    WATCH_TRACKER_SCRIPT,
    '--source', realSource,
    '--model', WATCH_TRACKER_MODEL,
    '--tracker', process.env.WATCH_TRACKER_CONFIG || 'bytetrack.yaml',
    '--sample-fps', process.env.WATCH_TRACKER_SAMPLE_FPS || '5',
    '--max-events', /^\d+$/.test(maxEvents) ? maxEvents : '200',
    '--stdout-jsonl',
  ]
  if (startSeconds && /^(\d+|\d+\.\d+)$/.test(startSeconds)) args.push('--start-seconds', startSeconds)
  if (segmentId) args.push('--segment-id', segmentId)
  if (assetUid) args.push('--asset-uid', assetUid)
  if (streamId) args.push('--stream-id', streamId)
  if (candidateName) {
    args.push('--candidate-name', candidateName, '--attach-domain-candidate')
    if (candidateActorName) args.push('--candidate-actor-name', candidateActorName)
  }

  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache, no-transform')
  res.setHeader('Connection', 'keep-alive')
  res.flushHeaders?.()

  res.write(`event: meta\ndata: ${JSON.stringify({
    schema: 'watch.tracker_event_stream.v1',
    status: 'STARTING_LIVE_TRACKER',
    source: realSource,
    segment_id: segmentId || null,
    asset_uid: assetUid || null,
    model: WATCH_TRACKER_MODEL,
    sample_fps: Number(process.env.WATCH_TRACKER_SAMPLE_FPS || 5),
  })}\n\n`)

  const child = spawn(process.env.PYTHON || 'python3', args, {
    cwd: WATCH_SKILL_DIR,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let eventCount = 0
  let stdoutBuffer = ''
  let stderrBuffer = ''

  child.stdout.setEncoding('utf-8')
  child.stdout.on('data', (chunk: string) => {
    stdoutBuffer += chunk
    const lines = stdoutBuffer.split(/\r?\n/)
    stdoutBuffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const event = JSON.parse(trimmed)
        eventCount += 1
        res.write(`event: track_update\ndata: ${JSON.stringify(event)}\n\n`)
      } catch {
        res.write(`event: diagnostic\ndata: ${JSON.stringify({ level: 'warn', message: trimmed.slice(0, 500) })}\n\n`)
      }
    }
  })

  child.stderr.setEncoding('utf-8')
  child.stderr.on('data', (chunk: string) => {
    stderrBuffer = `${stderrBuffer}${chunk}`.slice(-4000)
    for (const line of chunk.split(/\r?\n/).map(item => item.trim()).filter(Boolean).slice(-5)) {
      res.write(`event: diagnostic\ndata: ${JSON.stringify({ level: 'stderr', message: line.slice(0, 500) })}\n\n`)
    }
  })

  child.on('error', (err) => {
    res.write(`event: done\ndata: ${JSON.stringify({ status: 'TRACKER_SPAWN_ERROR', error: String(err), total_events: eventCount })}\n\n`)
    res.end()
  })

  child.on('close', (code) => {
    res.write(`event: done\ndata: ${JSON.stringify({
      status: code === 0 && eventCount > 0 ? 'LIVE_STREAM_COMPLETE' : 'LIVE_STREAM_FAILED',
      exit_code: code,
      total_events: eventCount,
      stderr_tail: stderrBuffer || null,
    })}\n\n`)
    res.end()
  })

  req.on('close', () => {
    if (!child.killed) child.kill('SIGTERM')
  })
}

function readTrackerEvents(eventsPath: string): any[] {
  return readFileSync(eventsPath, 'utf-8')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line))
}

function serveMediaFile(rawPath: string, req: express.Request, res: express.Response) {
  try {
    const realPath = realpathSync(rawPath)
    const allowed = MEDIA_ROOTS.some(root => realPath.startsWith(root))
    if (!allowed) {
      res.status(403).json({ error: 'path outside allowed roots' })
      return
    }
    const stat = statSync(realPath)
    if (!stat.isFile()) {
      res.status(404).json({ error: 'not a file' })
      return
    }
    const ext = path.extname(realPath).toLowerCase()
    const mime: Record<string, string> = {
      '.mp4': 'video/mp4', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
      '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
      '.webp': 'image/webp',
    }
    res.setHeader('Accept-Ranges', 'bytes')
    res.setHeader('Content-Type', mime[ext] || 'application/octet-stream')
    res.setHeader('Content-Length', String(stat.size))
    const range = req.headers.range
    if (range) {
      const parts = range.replace(/bytes=/, '').split('-')
      const start = parseInt(parts[0], 10)
      const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1
      res.status(206)
      res.setHeader('Content-Range', `bytes ${start}-${end}/${stat.size}`)
      createReadStream(realPath, { start, end }).pipe(res)
    } else {
      createReadStream(realPath).pipe(res)
    }
  } catch {
    res.status(404).json({ error: 'media not found' })
  }
}

// Question answering proxy
app.post('/api/projects/watch/question', async (req, res) => {
  const question = typeof req.body?.question === 'string' ? req.body.question.trim() : ''
  if (!question) {
    res.status(400).json({ error: 'question is required' })
    return
  }

  let report: any
  try {
    const raw = readFileSync(WATCH_REPORT_PATH, 'utf-8')
    report = JSON.parse(raw)
  } catch {
    res.status(500).json({ error: 'failed to read report' })
    return
  }

  const rows = Array.isArray(report.scene_elements) ? report.scene_elements : []
  const matchedRows = rows.slice(0, 8)

  try {
    const resp = await fetch(`${MEMORY_DAEMON}/recall`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: question, collections: ['watch_content'], k: 5 }),
    })
    const memoryData = await resp.json() as any
    res.json({
      question,
      route: 'RECALL',
      answer: buildLocalAnswer(question, matchedRows),
      confidence: 0.5,
      matched_rows: matchedRows,
      evidence: { local_row_count: matchedRows.length, sources: ['memory:recall'] },
      memory: memoryData,
    })
  } catch {
    res.json({
      question,
      route: 'LOCAL',
      answer: buildLocalAnswer(question, matchedRows),
      confidence: 0.3,
      matched_rows: matchedRows,
      evidence: { local_row_count: matchedRows.length, sources: ['local'] },
    })
  }
})

// Identity suggestion proxy. Watch owns character identity, but it must ask
// Memory/Qdrant rather than reaching into vector stores directly from the UI.
app.post('/api/projects/watch/identity-suggestions', async (req, res) => {
  const trackId = typeof req.body?.track_id === 'string' ? req.body.track_id : ''
  const imageDataUrl = typeof req.body?.image_data_url === 'string' ? req.body.image_data_url : ''
  const imagePath = typeof req.body?.image_path === 'string' ? req.body.image_path : ''
  const q = typeof req.body?.q === 'string' && req.body.q.trim()
    ? req.body.q.trim()
    : `Who does this Watch YOLO person crop most look like?`

  if (!trackId) {
    res.status(400).json({ error: 'track_id is required' })
    return
  }
  if (!imageDataUrl && !imagePath) {
    res.status(400).json({ error: 'image_data_url or image_path is required' })
    return
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 12_000)
  try {
    const resp = await fetch(`${MEMORY_DAEMON}/watch/identity/recall-crop`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Caller-Skill': 'watch',
      },
      signal: controller.signal,
      body: JSON.stringify({
        q,
        image_data_url: imageDataUrl || undefined,
        image_path: imagePath || undefined,
        k: 10,
        asset_uid: req.body?.asset_uid,
        row_index: req.body?.row_index,
        time_seconds: req.body?.time_seconds,
        track_id: trackId,
      }),
    })
    const memoryData = await resp.json() as any
    const topSuggestion = Array.isArray(memoryData?.suggestions) ? memoryData.suggestions[0] : null
    res.status(resp.ok ? 200 : 502).json({
      schema: 'watch.identity_suggestions.v1',
      status: resp.ok ? 'ok' : 'memory_error',
      track_id: trackId,
      suggestion: topSuggestion
        ? {
            character_name: topSuggestion.character_name,
            actor_name: topSuggestion.actor_name,
            confidence: topSuggestion.confidence,
            basis: ['memory_qdrant_crop_recall'],
            tentative: true,
            display_label: topSuggestion.display_label,
          }
        : null,
      memory: memoryData,
    })
  } catch (err) {
    res.status(502).json({
      schema: 'watch.identity_suggestions.v1',
      status: 'memory_unavailable',
      track_id: trackId,
      error: String(err),
    })
  } finally {
    clearTimeout(timeout)
  }
})

app.get('/api/projects/watch/yolo-labels', async (req, res) => {
  const assetUid = typeof req.query.asset_uid === 'string' ? req.query.asset_uid : ''
  const rowIndex = typeof req.query.row_index === 'string' ? Number(req.query.row_index) : NaN
  if (!assetUid || !Number.isFinite(rowIndex)) {
    res.status(400).json({ error: 'asset_uid and row_index are required' })
    return
  }
  try {
    const receipt = await yoloReceiptStore.read(assetUid, rowIndex)
    res.json(receipt)
  } catch (err) {
    if (err instanceof MalformedYoloReceiptError) {
      res.status(422).json({ code: 'MALFORMED_YOLO_RECEIPT', error: err.message, receipt_path: err.receiptPath })
      return
    }
    res.status(500).json({ error: String(err) })
  }
})

app.get('/api/projects/watch/yolo-labels/projected', async (req, res) => {
  const assetUid = typeof req.query.asset_uid === 'string' ? req.query.asset_uid : ''
  const rowIndex = typeof req.query.row_index === 'string' ? Number(req.query.row_index) : NaN
  const trackId = typeof req.query.track_id === 'string' ? req.query.track_id : ''
  const timeSeconds = typeof req.query.time_seconds === 'string' ? Number(req.query.time_seconds) : NaN
  if (!assetUid || !Number.isFinite(rowIndex) || !trackId || !Number.isFinite(timeSeconds)) {
    res.status(400).json({ error: 'asset_uid, row_index, track_id, and time_seconds are required' })
    return
  }
  try {
    const receipt = await yoloReceiptStore.read(assetUid, rowIndex)
    const label = projectYoloTrackLabelAtTime({
      trackId,
      timeSeconds,
      events: receipt.events,
      labels: receipt.labels as Record<string, { characterName?: string; actorName?: string; confidence?: number }>,
    })
    res.json({
      schema: 'watch.yolo_label_projection.v1',
      asset_uid: assetUid,
      row_index: rowIndex,
      track_id: trackId,
      time_seconds: timeSeconds,
      label,
    })
  } catch (err) {
    if (err instanceof MalformedYoloReceiptError) {
      res.status(422).json({ code: 'MALFORMED_YOLO_RECEIPT', error: err.message, receipt_path: err.receiptPath })
      return
    }
    res.status(500).json({ error: String(err) })
  }
})

app.post('/api/projects/watch/yolo-labels', async (req, res) => {
  const assetUid = typeof req.body?.asset_uid === 'string' ? req.body.asset_uid : ''
  const rowIndex = Number(req.body?.row_index)
  const trackId = typeof req.body?.track_id === 'string' ? req.body.track_id : ''
  const action = typeof req.body?.action === 'string' ? req.body.action as YoloLabelAction : 'accept'
  if (!assetUid || !Number.isFinite(rowIndex) || !trackId) {
    res.status(400).json({ error: 'asset_uid, row_index, and track_id are required' })
    return
  }
  if (!['accept', 'reject', 'reset', 'reject_box', 'reset_box'].includes(action)) {
    res.status(400).json({ error: 'unsupported YOLO label action' })
    return
  }

  const bodyBoxKey = typeof req.body?.box_key === 'string' && req.body.box_key.trim() ? req.body.box_key.trim() : ''
  const boxKey = bodyBoxKey || yoloBoxInstanceKey(trackId, req.body?.time_seconds)
  const timeSeconds = Number(req.body?.time_seconds)
  if (!Number.isFinite(timeSeconds) || timeSeconds < 0) {
    res.status(400).json({ error: 'finite nonnegative time_seconds is required' })
    return
  }
  const idempotencyKey = typeof req.header('Idempotency-Key') === 'string' && req.header('Idempotency-Key')?.trim()
    ? req.header('Idempotency-Key')!.trim()
    : typeof req.body?.idempotency_key === 'string' && req.body.idempotency_key.trim()
      ? req.body.idempotency_key.trim()
      : crypto.randomUUID()

  let characterName = typeof req.body?.character_name === 'string' ? req.body.character_name.trim() : undefined
  let actorName = typeof req.body?.actor_name === 'string' ? req.body.actor_name : undefined
  let confidence = typeof req.body?.confidence === 'number' ? req.body.confidence : undefined
  if (action === 'accept') {
    const acceptedCharacterName = typeof req.body?.character_name === 'string' ? req.body.character_name.trim() : ''
    if (!acceptedCharacterName || acceptedCharacterName === 'Unassigned') {
      res.status(400).json({ error: 'character_name is required for accepted labels' })
      return
    }
    characterName = acceptedCharacterName
    actorName = typeof req.body?.actor_name === 'string' ? req.body.actor_name : ''
    confidence = typeof req.body?.confidence === 'number' ? req.body.confidence : 1
  }

  try {
    const expectedEventId = eventIdFor(assetUid, rowIndex, idempotencyKey)
    const mutationInput = {
      idempotencyKey,
      action,
      assetUid,
      rowIndex,
      trackId,
      boxKey,
      timeSeconds: Math.round(timeSeconds * 100) / 100,
      timecode: typeof req.body?.timecode === 'string' ? req.body.timecode : null,
      movieSegment: typeof req.body?.movie_segment === 'string' ? req.body.movie_segment : null,
      characterName,
      actorName,
      confidence,
    }
    const expectedFingerprint = fingerprintFor(mutationInput)
    const result = await withYoloMemorySyncClaim(expectedEventId, async () => {
      const mutation = await yoloReceiptStore.applyMutation(mutationInput)
      if (mutation.deduplicated) {
        return {
          ...mutation.receipt,
          memory_sync: mutation.event.memory_sync.state,
          memory_sync_error: mutation.event.memory_sync.last_error,
          deduplicated: true,
        }
      }

      const memorySync = await deliverYoloEventToMemory({
        memoryDaemonUrl: MEMORY_DAEMON,
        receipt: mutation.receipt,
        event: mutation.event,
      })
      const finalReceipt = await yoloReceiptStore.updateMemorySync(assetUid, rowIndex, mutation.event.id, {
        state: memorySync.ok ? 'stored' : 'failed',
        lastError: memorySync.error,
      })
      const finalEvent = finalReceipt.events.find((event) => event.id === mutation.event.id) ?? mutation.event
      return {
        ...finalReceipt,
        memory_sync: finalEvent.memory_sync.state,
        memory_sync_error: finalEvent.memory_sync.last_error,
        deduplicated: false,
      }
    }, null)
    if (!result) {
      const receipt = await yoloReceiptStore.read(assetUid, rowIndex)
      const event = receipt.events.find((item) => item.id === expectedEventId)
      if (event) {
        if (!event.request_fingerprint || event.request_fingerprint !== expectedFingerprint) {
          throw new IdempotencyConflictError()
        }
        res.json({
          ...receipt,
          memory_sync: event.memory_sync.state,
          memory_sync_error: event.memory_sync.last_error,
          deduplicated: true,
        })
        return
      }
      res.status(409).json({
        code: 'MEMORY_SYNC_IN_FLIGHT',
        error: 'memory sync is already in flight for this event',
        memory_sync: 'pending',
      })
      return
    }
    res.json(result)
  } catch (err) {
    if (err instanceof IdempotencyConflictError || err instanceof OutOfOrderTrackEventError) {
      res.status(409).json({ code: err.code, error: err.message })
      return
    }
    if (err instanceof MalformedYoloReceiptError) {
      res.status(422).json({ code: 'MALFORMED_YOLO_RECEIPT', error: err.message, receipt_path: err.receiptPath })
      return
    }
    res.status(500).json({ error: String(err) })
  }
})

app.post('/api/projects/watch/yolo-labels/retry-memory-sync', async (req, res) => {
  const assetUid = typeof req.body?.asset_uid === 'string' ? req.body.asset_uid : undefined
  const rowIndex = Number.isFinite(Number(req.body?.row_index)) ? Number(req.body.row_index) : undefined
  const eventId = typeof req.body?.event_id === 'string' ? req.body.event_id : undefined
  try {
    const result = await retryYoloMemorySync({
      store: yoloReceiptStore,
      memoryDaemonUrl: MEMORY_DAEMON,
      assetUid,
      rowIndex,
      eventId,
    })
    res.json({
      schema: 'watch.yolo_memory_sync_retry.v1',
      ...result,
    })
  } catch (err) {
    if (err instanceof MalformedYoloReceiptError) {
      res.status(422).json({ code: 'MALFORMED_YOLO_RECEIPT', error: err.message, receipt_path: err.receiptPath })
      return
    }
    res.status(500).json({ error: String(err) })
  }
})

function buildLocalAnswer(question: string, rows: any[]): string {
  if (rows.length === 0) return 'No scene data available for this report.'
  const q = question.toLowerCase()
  const matching = rows.filter(r =>
    (r.srt_text || '').toLowerCase().includes(q) ||
    (r.text || '').toLowerCase().includes(q) ||
    (r.timecode || '').includes(q)
  )
  const hits = matching.length > 0 ? matching : rows.slice(0, 3)
  return hits.map((r: any) =>
    `[${r.timecode || '??'}] SRT: ${(r.srt_text || '').slice(0, 120)}`
  ).join('\n') || 'No matching scenes found.'
}

// Serve built UI in production
const distPath = path.join(__dirname, '..', 'dist')
if (existsSync(distPath)) {
  app.use(express.static(distPath))
  app.get('*', (_req, res) => {
    res.sendFile(path.join(distPath, 'index.html'))
  })
}

return app
}
