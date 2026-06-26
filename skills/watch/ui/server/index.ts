import express from 'express'
import { readFileSync, existsSync, statSync } from 'fs'
import { createReadStream } from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const app = express()
const PORT = Number(process.env.WATCH_API_PORT || 3003)

app.use(express.json())

const WATCH_REPORT_PATH = process.env.WATCH_REPORT_PATH || '/tmp/watch-wex5uxs_/report.json'
const WATCH_FRAMES_DIR = process.env.WATCH_FRAMES_DIR || '/mnt/storage12tb/media/watch-frames'
const MEMORY_DAEMON = process.env.MEMORY_DAEMON_URL || 'http://127.0.0.1:8601'

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

function serveMediaFile(rawPath: string, req: express.Request, res: express.Response) {
  try {
    const realPath = require('fs').realpathSync(rawPath)
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
