import { createReadStream } from 'node:fs'
import { resolve } from 'node:path'
import type { Router as ExpressRouter } from 'express'
import { Router } from 'express'
import { DreamPathPolicy, dreamContentType } from './paths'

export function createPersonaMediaRouter(root: string): ExpressRouter {
  const router = Router()
  const policy = new DreamPathPolicy([root])
  router.get('/', (req, res) => {
    try {
      const persona = typeof req.query.persona === 'string' ? req.query.persona.replace(/[^a-z0-9_-]/gi, '') : ''
      const path = typeof req.query.path === 'string' ? req.query.path : ''
      if (!persona || !path) return res.status(400).send('persona and path required')
      const real = policy.resolveFile(resolve(root, persona, path))
      res.setHeader('Content-Type', dreamContentType(real))
      createReadStream(real).pipe(res)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      res.status(message === 'path_not_allowed' ? 403 : 404).send('not found')
    }
  })
  return router
}
