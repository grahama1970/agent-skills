import express from 'express'
import { readFileSync, existsSync, statSync, realpathSync } from 'fs'
import { createReadStream } from 'fs'
import { spawn } from 'child_process'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const app = express()
const PORT = Number(process.env.WATCH_API_PORT || 3003)

app.use(express.json())

const WATCH_REPORT_PATH = process.env.WATCH_REPORT_PATH || '/tmp/watch-wex5uxs_/report.json'
const WATCH_FRAMES_DIR = process.env.WATCH_FRAMES_DIR || '/mnt/storage12tb/media/watch-frames'
const MEMORY_DAEMON = process.env.MEMORY_DAEMON_URL || 'http://127.0.0.1:8601'
const WATCH_SKILL_DIR = path.resolve(__dirname, '..', '..')
const WATCH_TRACKER_EVENTS_PATH = process.env.WATCH_TRACKER_EVENTS_PATH || path.join(
  WATCH_SKILL_DIR,
  'docs/architecture/generated/bad_santa_marcus_0248_yolo_bytetrack/watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl',
)
const WATCH_TRACKER_SCRIPT = process.env.WATCH_TRACKER_SCRIPT || path.join(WATCH_SKILL_DIR, 'scripts/track_yolo_bytetrack.py')
const WATCH_TRACKER_MODEL = process.env.WATCH_TRACKER_MODEL || path.join(WATCH_SKILL_DIR, 'yolo11n.pt')

// Serve report JSON
app.get('/api/projects/watch/report', async (_req, res) => {
  try {
    const raw = readFileSync(WATCH_REPORT_PATH, 'utf-8')
    res.json(JSON.parse(raw))
  } catch (err) {
    res.status(500).json({ error: String(err), report_path: WATCH_REPORT_PATH })
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

app.listen(PORT, () => {
  console.log(`Watch API server running on port ${PORT}`)
})
