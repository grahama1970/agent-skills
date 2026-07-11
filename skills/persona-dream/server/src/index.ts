import { createReadStream } from 'node:fs'
import type { Router as ExpressRouter } from 'express'
import { Router } from 'express'
import { DreamPathPolicy, dreamContentType } from './paths'
import { buildRunDetail, collectRuns } from './runs'

export type PersonaDreamRouterOptions = {
  reportRoots: readonly string[]
  outputRoots: readonly string[]
  assetRoots?: readonly string[]
  repairEnqueueMode?: 'disabled' | 'explicit-post-only'
}

export function createPersonaDreamRouter(options: PersonaDreamRouterOptions): ExpressRouter {
  const router = Router()
  const roots = [...options.reportRoots, ...options.outputRoots, ...(options.assetRoots ?? [])]
  const policy = new DreamPathPolicy(roots)

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

  router.post('/stage-work-order', (_req, res) => {
    res.status(503).json({
      status: 'BLOCKED_REPAIR_ENQUEUE_NOT_INSTALLED',
      mocked: false,
      live: false,
      error: options.repairEnqueueMode === 'explicit-post-only'
        ? 'Tau repair queue port is not installed in the read-only extraction slice.'
        : 'Repair enqueue is disabled.',
    })
  })

  return router
}

export * from '../../contracts/src/index'
