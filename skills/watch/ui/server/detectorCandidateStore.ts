import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'

export class DetectorCandidatesNotFoundError extends Error {
  readonly code = 'DETECTOR_CANDIDATES_NOT_FOUND'

  constructor(message = 'detector candidates not found') {
    super(message)
    this.name = 'DetectorCandidatesNotFoundError'
  }
}

export class DetectorCandidatesAmbiguousError extends Error {
  readonly code = 'DETECTOR_CANDIDATES_AMBIGUOUS'

  constructor(
    readonly candidatePaths: string[],
    readonly candidateRunIds: Array<string | null>,
  ) {
    super('detector candidates lookup is ambiguous')
    this.name = 'DetectorCandidatesAmbiguousError'
  }
}

async function walkDetectorFiles(rootDir: string, targetName: string): Promise<string[]> {
  const results: string[] = []
  async function walk(current: string): Promise<void> {
    let entries
    try {
      entries = await readdir(current, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name)
      if (entry.isDirectory()) await walk(fullPath)
      else if (entry.isFile() && entry.name === targetName) results.push(fullPath)
    }
  }
  await walk(rootDir)
  return results.sort((a, b) => a.localeCompare(b))
}

export async function resolveDetectorCandidates(input: {
  rootDir: string
  assetUid: string
  rowIndex: number
  runId?: string
}): Promise<{
  path: string
  payload: Record<string, unknown>
}> {
  const targetName = `detector_candidates_row${input.rowIndex}.json`
  const candidatePaths = await walkDetectorFiles(input.rootDir, targetName)
  const matches: Array<{ path: string; payload: Record<string, unknown>; runId: string | null }> = []

  for (const candidatePath of candidatePaths) {
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(await readFile(candidatePath, 'utf-8')) as Record<string, unknown>
    } catch {
      continue
    }
    if (payload.schema !== 'watch.detector_candidates.v1') continue
    if (payload.asset_uid !== input.assetUid) continue
    if (Number(payload.row_index) !== input.rowIndex) continue
    const runId = typeof payload.run_id === 'string' ? payload.run_id : null
    if (input.runId && runId !== input.runId) continue
    matches.push({ path: candidatePath, payload, runId })
  }

  if (matches.length === 0) throw new DetectorCandidatesNotFoundError()
  if (matches.length > 1) {
    throw new DetectorCandidatesAmbiguousError(
      matches.map((match) => match.path).sort((a, b) => a.localeCompare(b)),
      Array.from(new Set(matches.map((match) => match.runId))).sort((a, b) => String(a).localeCompare(String(b))),
    )
  }
  return { path: matches[0].path, payload: matches[0].payload }
}
