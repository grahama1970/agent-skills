/**
 * asset helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */


export function dreamAssetUrl(value?: string): string | undefined {
  if (!value) return undefined
  if (/^(https?:\/\/|\/api\/|\/assets\/)/i.test(value)) return value
  if (value.startsWith('/mnt/storage12tb/media/personas/')) return `/api/projects/dream/asset?path=${encodeURIComponent(value)}`
  if (value.startsWith('/home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/')) return `/api/projects/dream/asset?path=${encodeURIComponent(value)}`
  if (value.startsWith('/mnt/storage12tb/skills/persona-dream/outputs/')) return `/api/projects/dream/asset?path=${encodeURIComponent(value)}`
  return value.startsWith('/') ? `/api/projects/dream/asset?path=${encodeURIComponent(value)}` : undefined
}

export function assetExtension(path: string, contentType?: string | null): string {
  const fromPath = path.match(/\.(png|jpe?g|webp|gif|mp4|mov|wav|mp3)(?:[?#].*)?$/i)?.[1]
  if (fromPath) return fromPath.toLowerCase().replace('jpeg', 'jpg')
  if (contentType?.includes('png')) return 'png'
  if (contentType?.includes('jpeg')) return 'jpg'
  if (contentType?.includes('webp')) return 'webp'
  if (contentType?.includes('gif')) return 'gif'
  if (contentType?.includes('mp4')) return 'mp4'
  if (contentType?.includes('mpeg')) return 'mp3'
  if (contentType?.includes('wav')) return 'wav'
  return 'bin'
}
