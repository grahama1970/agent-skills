/** Minimal browser globals for server-rendering a DOM-oriented component.
 * Imported before ui/src so the shims exist when module-level code runs. */
const g = globalThis as Record<string, unknown>
if (!g.window) {
  const location = { hash: '#dream', pathname: '/', search: '', href: 'http://127.0.0.1:5173/#dream' }
  const storage = { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }
  g.window = {
    location,
    history: { replaceState: () => undefined },
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    matchMedia: () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }),
    innerWidth: 1280,
    innerHeight: 800,
    localStorage: storage,
    sessionStorage: storage,
  }
  g.location = location
  g.localStorage = storage
  g.sessionStorage = storage
  Object.defineProperty(g, 'navigator', { value: { userAgent: 'agentic-evals-ssr' }, configurable: true })
}
export {}
