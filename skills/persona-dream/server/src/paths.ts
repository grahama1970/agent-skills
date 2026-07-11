import { realpathSync, statSync } from 'node:fs'
import { relative, resolve, sep } from 'node:path'

export class DreamPathPolicy {
  readonly roots: string[]

  constructor(roots: readonly string[]) {
    this.roots = roots.map((root) => realpathSync(root))
  }

  resolveFile(requested: string): string {
    if (!requested || requested.includes('\0')) throw new Error('invalid_path')
    const real = realpathSync(resolve(requested))
    const allowed = this.roots.some((root) => {
      const rel = relative(root, real)
      return rel !== '' && rel !== '..' && !rel.startsWith(`..${sep}`) && !rel.includes(`${sep}..${sep}`)
    })
    if (!allowed) throw new Error('path_not_allowed')
    if (!statSync(real).isFile()) throw new Error('not_a_regular_file')
    return real
  }

  resolveDirectory(requested: string): string {
    if (!requested || requested.includes('\0')) throw new Error('invalid_path')
    const real = realpathSync(resolve(requested))
    const allowed = this.roots.some((root) => {
      const rel = relative(root, real)
      return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`))
    })
    if (!allowed) throw new Error('path_not_allowed')
    if (!statSync(real).isDirectory()) throw new Error('not_a_directory')
    return real
  }
}

export function dreamContentType(path: string): string {
  const lower = path.toLowerCase()
  if (lower.endsWith('.json')) return 'application/json; charset=utf-8'
  if (lower.endsWith('.html')) return 'text/html; charset=utf-8'
  if (lower.endsWith('.md') || lower.endsWith('.txt')) return 'text/plain; charset=utf-8'
  if (lower.endsWith('.png')) return 'image/png'
  if (/\.jpe?g$/.test(lower)) return 'image/jpeg'
  if (lower.endsWith('.webp')) return 'image/webp'
  if (lower.endsWith('.wav')) return 'audio/wav'
  if (lower.endsWith('.mp3')) return 'audio/mpeg'
  if (lower.endsWith('.mp4')) return 'video/mp4'
  return 'application/octet-stream'
}
