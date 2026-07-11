export interface DreamResearchPort {
  search(query: string): Promise<{ status: 'ok'; query: string; results: Array<{ title: string; url: string; snippet: string }>; total: number }>
}

export interface VoiceAuditionPort {
  audition(request: Record<string, unknown>): Promise<Record<string, unknown>>
}

export function createBraveResearchPort(apiKey: string): DreamResearchPort {
  return {
    async search(query) {
      if (!apiKey) throw new Error('brave_search_api_key_not_configured')
      const url = new URL('https://api.search.brave.com/res/v1/web/search')
      url.searchParams.set('q', query)
      url.searchParams.set('count', '5')
      const response = await fetch(url, {
        headers: { Accept: 'application/json', 'X-Subscription-Token': apiKey },
        signal: AbortSignal.timeout(10_000),
      })
      if (!response.ok) throw new Error(`brave_search_http_${response.status}`)
      const payload = await response.json() as { web?: { total?: number; results?: Array<Record<string, unknown>> } }
      const results = (payload.web?.results ?? []).map((item) => ({
        title: String(item.title ?? ''),
        url: String(item.url ?? ''),
        snippet: String(item.description ?? ''),
      }))
      return { status: 'ok' as const, query, results, total: Number(payload.web?.total ?? results.length) }
    },
  }
}
