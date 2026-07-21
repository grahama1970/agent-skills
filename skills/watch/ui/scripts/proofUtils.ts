import { spawn, type ChildProcess } from 'node:child_process'
import { createHash } from 'node:crypto'
import { once } from 'node:events'
import { createReadStream } from 'node:fs'
import { mkdir, readdir, stat, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import type { AddressInfo } from 'node:net'
import path from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'

export async function sha256File(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash('sha256')
    const stream = createReadStream(filePath)
    stream.on('data', (chunk) => hash.update(chunk))
    stream.on('error', reject)
    stream.on('end', () => resolve(hash.digest('hex')))
  })
}

export async function reserveLocalPort(): Promise<number> {
  const server = createServer()
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address() as AddressInfo | null
  await new Promise<void>((resolve, reject) => {
    server.close((error) => error ? reject(error) : resolve())
  })
  if (!address || !Number.isInteger(address.port)) {
    throw new Error('failed to reserve a local port')
  }
  return address.port
}

export async function waitForHttpOk(url: string, timeoutMs: number): Promise<void> {
  const started = Date.now()
  let lastError = ''
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = `HTTP ${response.status}`
    } catch (error) {
      lastError = String(error)
    }
    await delay(100)
  }
  throw new Error(`timed out waiting for ${url}: ${lastError}`)
}

export async function runCommand(input: {
  command: string
  args: string[]
  cwd: string
  env?: NodeJS.ProcessEnv
}): Promise<{
  command: string
  exit_code: number
  stdout: string
  stderr: string
  started_at: string
  finished_at: string
}> {
  const startedAt = new Date().toISOString()
  const child = spawn(input.command, input.args, {
    cwd: input.cwd,
    env: input.env || process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stdout = ''
  let stderr = ''
  child.stdout?.setEncoding('utf-8')
  child.stderr?.setEncoding('utf-8')
  child.stdout?.on('data', (chunk: string) => {
    stdout += chunk
  })
  child.stderr?.on('data', (chunk: string) => {
    stderr += chunk
  })
  const [exitCode] = await once(child, 'close') as [number]
  return {
    command: [input.command, ...input.args].join(' '),
    exit_code: exitCode ?? 1,
    stdout,
    stderr,
    started_at: startedAt,
    finished_at: new Date().toISOString(),
  }
}

export async function stopProcessTree(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return

  const closePromise = once(child, 'close')
  if (process.platform !== 'win32' && typeof child.pid === 'number') {
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch {
      child.kill('SIGTERM')
    }
  } else {
    child.kill('SIGTERM')
  }
  await Promise.race([closePromise, delay(2_000)])

  if (child.exitCode === null && child.signalCode === null) {
    const forcedClose = once(child, 'close')
    if (process.platform !== 'win32' && typeof child.pid === 'number') {
      try {
        process.kill(-child.pid, 'SIGKILL')
      } catch {
        child.kill('SIGKILL')
      }
    } else {
      child.kill('SIGKILL')
    }
    await forcedClose
  }
}

export async function assertCleanWorktree(repoRoot: string): Promise<void> {
  const result = await runCommand({
    command: 'git',
    args: ['status', '--porcelain'],
    cwd: repoRoot,
  })
  if (result.exit_code !== 0) {
    throw new Error(`git status failed:\n${result.stderr || result.stdout}`)
  }
  if (result.stdout.trim()) {
    throw new Error(`worktree is dirty:\n${result.stdout}`)
  }
}

async function listFiles(root: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true })
  const files: string[] = []
  for (const entry of entries) {
    const fullPath = path.join(root, entry.name)
    if (entry.isDirectory()) {
      files.push(...await listFiles(fullPath))
    } else if (entry.isFile()) {
      files.push(fullPath)
    }
  }
  return files
}

export async function writeProofManifest(input: {
  proofDir: string
  manifest: Record<string, unknown>
}): Promise<void> {
  const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..', '..', '..')
  const proofDir = path.resolve(input.proofDir)
  const files = (await listFiles(proofDir))
    .filter((filePath) => path.basename(filePath) !== 'manifest.json')
    .sort()
  const artifacts = []
  for (const filePath of files) {
    const relativePath = path.relative(repoRoot, filePath)
    if (path.isAbsolute(relativePath) || relativePath.startsWith('..')) {
      throw new Error(`proof artifact is outside repo root: ${filePath}`)
    }
    const info = await stat(filePath)
    artifacts.push({
      path: relativePath,
      sha256: await sha256File(filePath),
      bytes: info.size,
    })
  }

  const manifest = {
    ...input.manifest,
    artifacts,
  }
  const serialized = JSON.stringify(manifest, null, 2)
  if (/\"(?:path|manifest)\":\s*\"\/[^"]*\"/.test(serialized)) {
    throw new Error('manifest contains an absolute artifact path')
  }
  await mkdir(proofDir, { recursive: true })
  await writeFile(path.join(proofDir, 'manifest.json'), `${serialized}\n`, { mode: 0o600 })
}
