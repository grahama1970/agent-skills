import type { DreamResearchPort } from './contracts'

export type BraveResearchAdapterOptions = {
  apiKey: string
  endpoint?: URL
  resultCount?: number
  timeoutMs?: number
  fetchImpl?: typeof fetch
}

export function createBraveResearchPort(options: BraveResearchAdapterOptions | string): DreamResearchPort {
  const config = typeof options === 'string' ? { apiKey: options } : options
  return {
    async search(query) {
      if (!config.apiKey) throw new Error('brave_search_api_key_not_configured')
      const endpoint = config.endpoint ?? new URL('https://api.search.brave.com/res/v1/web/search')
      if (endpoint.protocol !== 'https:' || endpoint.origin !== 'https://api.search.brave.com') {
        throw new Error('brave_search_endpoint_not_allowed')
      }
      const count = Math.max(1, Math.min(20, config.resultCount ?? 5))
      const url = new URL(endpoint)
      url.searchParams.set('q', query)
      url.searchParams.set('count', String(count))
      const response = await (config.fetchImpl ?? fetch)(url, {
        method: 'GET',
        headers: { Accept: 'application/json', 'X-Subscription-Token': config.apiKey },
        signal: AbortSignal.timeout(config.timeoutMs ?? 10_000),
      })
      if (!response.ok) throw new Error(`brave_search_http_${response.status}`)
      const payload = await response.json() as { web?: { total?: number; results?: Array<Record<string, unknown>> } }
      const results = (payload.web?.results ?? []).slice(0, count).map((item) => ({
        title: String(item.title ?? ''),
        url: String(item.url ?? ''),
        snippet: String(item.description ?? ''),
      }))
      return { status: 'ok', query, results, total: Number(payload.web?.total ?? results.length) }
    },
  }
}
