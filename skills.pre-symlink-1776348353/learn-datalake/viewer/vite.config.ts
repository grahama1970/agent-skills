import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { createReadStream, statSync } from 'fs'
import { resolve } from 'path'

// Serve PDFs from the 12TB corpus so pdf.js can render them in-browser
function corpusPdfPlugin(): Plugin {
  const CORPUS_ROOT = '/mnt/storage12tb/extractor_corpus/source'
  const PREFIX = '/corpus-pdf/'
  return {
    name: 'corpus-pdf-server',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith(PREFIX)) return next()
        const relPath = decodeURIComponent(req.url.slice(PREFIX.length))
        const absPath = resolve(CORPUS_ROOT, relPath)
        // Security: don't allow path traversal out of corpus root
        if (!absPath.startsWith(CORPUS_ROOT)) { res.statusCode = 403; res.end('Forbidden'); return }
        try {
          const stat = statSync(absPath)
          res.setHeader('Content-Type', 'application/pdf')
          res.setHeader('Content-Length', stat.size)
          res.setHeader('Access-Control-Allow-Origin', '*')
          createReadStream(absPath).pipe(res)
        } catch {
          res.statusCode = 404; res.end('Not found')
        }
      })
    },
  }
}

// Serve corpus metadata JSON files (fix_registry.json, etc.) from the 12TB drive
function corpusMetadataPlugin(): Plugin {
  const METADATA_ROOT = '/mnt/storage12tb/extractor_corpus/metadata'
  const PREFIX = '/corpus-metadata/'
  return {
    name: 'corpus-metadata-server',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith(PREFIX)) return next()
        const relPath = decodeURIComponent(req.url.slice(PREFIX.length))
        const absPath = resolve(METADATA_ROOT, relPath)
        if (!absPath.startsWith(METADATA_ROOT)) { res.statusCode = 403; res.end('Forbidden'); return }
        try {
          const stat = statSync(absPath)
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Content-Length', stat.size)
          res.setHeader('Access-Control-Allow-Origin', '*')
          createReadStream(absPath).pipe(res)
        } catch {
          res.statusCode = 404; res.end('Not found')
        }
      })
    },
  }
}

// Serve fixture PDFs and ground-truth JSON from the fixtures directory
function corpusFixturePlugin(): Plugin {
  const FIXTURE_ROOT = '/mnt/storage12tb/extractor_corpus/fixtures/generated'
  const PREFIX = '/corpus-fixture/'
  return {
    name: 'corpus-fixture-server',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith(PREFIX)) return next()
        const relPath = decodeURIComponent(req.url.slice(PREFIX.length))
        const absPath = resolve(FIXTURE_ROOT, relPath)
        if (!absPath.startsWith(FIXTURE_ROOT)) { res.statusCode = 403; res.end('Forbidden'); return }
        try {
          const stat = statSync(absPath)
          const ct = absPath.endsWith('.json') ? 'application/json' : 'application/pdf'
          res.setHeader('Content-Type', ct)
          res.setHeader('Content-Length', stat.size)
          res.setHeader('Access-Control-Allow-Origin', '*')
          createReadStream(absPath).pipe(res)
        } catch {
          res.statusCode = 404; res.end('Not found')
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), corpusPdfPlugin(), corpusMetadataPlugin(), corpusFixturePlugin()],
  server: {
    host: '0.0.0.0',
    port: 5181,
    strictPort: true,
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/memory': {
        target: 'http://localhost:8601',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/memory/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-recharts': ['recharts'],
          'vendor-d3': ['d3-force'],
          'vendor-pdfjs': ['pdfjs-dist'],
        },
      },
    },
  },
})
