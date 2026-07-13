import { createReadStream } from 'node:fs'
import type { Router as ExpressRouter } from 'express'
import { Router } from 'express'
import { DreamPathPolicy, dreamContentType } from './paths'
import { buildRunDetail, collectRuns } from './runs'
import { enqueueRepairCandidate, FileTauRepairQueue, type TauRepairQueuePort } from './repair'
import { createPanelPromptBundle } from './bundles'
import { createDefaultResearchPort, createDefaultVoiceAuditionPort, type DreamResearchPort, type VoiceAuditionPort } from './services'
import { resolveRevisionArtifact } from './artifacts'

export type PersonaDreamRouterOptions = {
  reportRoots: readonly string[]
  outputRoots: readonly string[]
  assetRoots?: readonly string[]
  repairEnqueueMode?: 'disabled' | 'explicit-post-only'
  tauRepairQueue?: TauRepairQueuePort
  temporaryRoot?: string
  research?: DreamResearchPort
  voiceAudition?: VoiceAuditionPort
}

export function createPersonaDreamRouter(options: PersonaDreamRouterOptions): ExpressRouter {
  const router = Router()
  const roots = [...options.reportRoots, ...options.outputRoots, ...(options.assetRoots ?? [])]
  const policy = new DreamPathPolicy(roots)
  const research = options.research ?? createDefaultResearchPort()
  const voiceAudition = options.voiceAudition ?? createDefaultVoiceAuditionPort(options)

  router.get('/runs', async (_req, res) => {
    try {
      const runs = await collectRuns(options.reportRoots, options.outputRoots)
      res.json({ status: 'ok', mocked: false, live: false, sourceRoots: [...options.reportRoots, ...options.outputRoots], runs })
    } catch (error) {
      res.status(500).json({ status: 'error', error: error instanceof Error ? error.message : String(error), runs: [] })
    }
  })

  router.get('/run-detail', async (req, res) => {
    try {
      const root = typeof req.query.root === 'string' ? req.query.root : ''
      if (!root) return res.status(400).json({ status: 'error', error: 'root required' })
      res.json(await buildRunDetail(policy, root))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const status = message === 'path_not_allowed' ? 403 : 500
      res.status(status).json({ status: 'error', error: message, stages: [] })
    }
  })

  router.get('/runs/:runId/revisions/:revisionId/artifacts/:artifactId', (req, res) => {
    try {
      const artifact = resolveRevisionArtifact(
        [...options.reportRoots, ...options.outputRoots],
        {
          runId: req.params.runId,
          revisionId: req.params.revisionId,
          artifactId: req.params.artifactId,
        },
      )
      res.setHeader('Content-Type', artifact.contentType)
      res.setHeader('Content-Length', String(artifact.sizeBytes))
      res.setHeader('ETag', `"${artifact.sha256.slice('sha256:'.length)}"`)
      res.setHeader('X-Persona-Dream-Run-Id', artifact.runId)
      res.setHeader('X-Persona-Dream-Revision-Id', artifact.revisionId)
      res.setHeader('X-Persona-Dream-Artifact-Id', artifact.artifactId)
      res.setHeader('X-Persona-Dream-Sha256', artifact.sha256)
      createReadStream(artifact.path).pipe(res)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const status = message === 'artifact_identity_invalid'
        ? 400
        : message === 'artifact_sha256_mismatch' || message === 'artifact_index_identity_mismatch'
          ? 409
          : 404
      res.status(status).json({ status: 'error', error: message })
    }
  })

  router.get('/asset', (req, res) => {
    try {
      const path = typeof req.query.path === 'string' ? req.query.path : ''
      if (!path) return res.status(400).send('path required')
      const real = policy.resolveFile(path)
      res.setHeader('Content-Type', dreamContentType(real))
      createReadStream(real).pipe(res)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      res.status(message === 'path_not_allowed' ? 403 : 404).send('asset not found')
    }
  })

  router.get('/report', (req, res) => {
    try {
      const path = typeof req.query.path === 'string' ? req.query.path : ''
      if (!path) return res.status(400).send('path required')
      const real = policy.resolveFile(path)
      if (!real.endsWith('/report.html')) return res.status(403).send('report path not allowed')
      res.sendFile(real)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      res.status(message === 'path_not_allowed' ? 403 : 404).send('report not found')
    }
  })

  router.post('/panel-prompt-bundle', async (req, res) => {
    try {
      const result = await createPanelPromptBundle({
        policy,
        temporaryRoot: options.temporaryRoot ?? '/tmp/persona-dream-panel-prompt-bundles',
        filename: req.body?.filename,
        entries: req.body?.entries,
      })
      res.json({ status: 'ok', mocked: false, live: false, copied: false, browserDownloadRequired: true, ...result })
    } catch (error) {
      res.status(400).json({ status: 'error', error: error instanceof Error ? error.message : String(error) })
    }
  })

  router.post('/brave-search', async (req, res) => {
    try {
      const query = typeof req.body?.query === 'string' ? req.body.query.trim() : ''
      if (!query) return res.status(400).json({ error: 'query required' })
      res.json(await research.search(query))
    } catch (error) {
      res.status(502).json({ error: error instanceof Error ? error.message : String(error) })
    }
  })

  router.post('/voices/audition', async (req, res) => {
    try {
      res.json(await voiceAudition.audition(req.body))
    } catch (error) {
      res.status(503).json({ status: 'error', mocked: false, live: true, error: error instanceof Error ? error.message : String(error) })
    }
  })

  router.post('/stage-work-order', async (req, res) => {
    if (options.repairEnqueueMode !== 'explicit-post-only') {
      return res.status(503).json({ status: 'BLOCKED_REPAIR_ENQUEUE_DISABLED', mocked: false, live: false })
    }
    try {
      const root = typeof req.body?.runRoot === 'string' ? req.body.runRoot : ''
      if (!root) return res.status(400).json({ status: 'error', error: 'runRoot required' })
      const detail = await buildRunDetail(policy, root)
      const result = await enqueueRepairCandidate(detail, options.tauRepairQueue ?? new FileTauRepairQueue())
      res.status(result.reused ? 200 : 202).json({ status: 'REPAIR_WORK_ORDER_QUEUED', mocked: false, live: false, ...result })
    } catch (error) {
      res.status(409).json({ status: 'BLOCKED_REPAIR_WORK_ORDER', mocked: false, live: false, error: error instanceof Error ? error.message : String(error) })
    }
  })

  return router
}

export * from '../../contracts/src/index'
export * from './repair'
export * from './services'
export * from './personaMedia'
export * from './artifacts'
