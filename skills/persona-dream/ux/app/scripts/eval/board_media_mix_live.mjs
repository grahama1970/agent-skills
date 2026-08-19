/** Eval: live board data path — recall from the real memory daemon, hydrate
 * by keys, stratify, and assert the 12-card board would contain at least one
 * image, one video, and one audio card for the Embry/Kai surf directive.
 *
 * Guards the 2026-08-19 incident where video and audio memories existed and
 * ranked in recall's top-24, but the board's hardcoded pinned-key ordering
 * plus the 12-card cut dropped them. Exercises the same helpers the UI uses
 * (dreamMemoryResultFromDocument, stratifiedMemorySample) against LIVE
 * /api/memory responses — no fixture inputs.
 */
import { build } from 'esbuild'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const appRoot = resolve(here, '../..')
const outfile = join(mkdtempSync(join(tmpdir(), 'pd-board-eval-')), 'board.cjs')
await build({
  entryPoints: [join(here, 'board_media_mix_live.probe.ts')],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  outfile,
  logLevel: 'silent',
  alias: { 'pd-ui-memory': resolve(appRoot, '../../ui/src/lib/memory.tsx') },
})
await import(pathToFileURL(outfile).href)
