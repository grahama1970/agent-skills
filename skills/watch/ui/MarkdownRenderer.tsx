/**
 * MarkdownRenderer - shared markdown rendering with entity highlighting and syntax highlighting.
 */
import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import go from 'highlight.js/lib/languages/go'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import javascript from 'highlight.js/lib/languages/javascript'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import yaml from 'highlight.js/lib/languages/yaml'
import rust from 'highlight.js/lib/languages/rust'
import { highlightEntities } from './highlightEntities'
import type { EntityType } from './types'

hljs.registerLanguage('go', go)
hljs.registerLanguage('python', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('shell', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('yaml', yaml)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('tsx', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('py', python)
hljs.registerLanguage('sh', bash)

interface MarkdownRendererProps {
  content: string
  onEntityClick?: (entity: string, type: EntityType) => void
  teaserMode?: boolean
  sidebarMode?: boolean
  onOpenWorkspace?: () => void
  tableRowCount?: number
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  onEntityClick,
  teaserMode = false,
  sidebarMode = false,
  onOpenWorkspace,
  tableRowCount,
}: MarkdownRendererProps) {
  const hl = (text: string) => (sidebarMode ? text : highlightEntities(text, onEntityClick))

  return (
    <div className={sidebarMode ? 'chat-prose chat-prose--sidebar' : 'chat-prose'}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p>
              {typeof children === 'string' ? hl(children) : children}
            </p>
          ),
          strong: ({ children }) => (
            <strong>
              {typeof children === 'string' ? hl(children) : children}
            </strong>
          ),
          h1: ({ children }) => <h1>{children}</h1>,
          h2: ({ children }) => <h2>{children}</h2>,
          h3: ({ children }) => <h3>{children}</h3>,
          h4: ({ children }) => <h4>{children}</h4>,
          ul: ({ children }) => <ul>{children}</ul>,
          ol: ({ children }) => <ol>{children}</ol>,
          li: ({ children }) => (
            <li>
              {typeof children === 'string' ? hl(children) : children}
            </li>
          ),
          code: ({ className, children }) => {
            const lang = className?.replace('language-', '') || ''
            const text = String(children).replace(/\n$/, '')
            if (!className) {
              return <code className="chat-prose__code">{text}</code>
            }

            let highlighted = text
            try {
              highlighted = lang && hljs.getLanguage(lang)
                ? hljs.highlight(text, { language: lang }).value
                : hljs.highlightAuto(text).value
            } catch {
              highlighted = text
            }

            return (
              <div className="chat-prose-codeblock">
                {lang ? <div className="chat-prose-codeblock__lang">{lang}</div> : null}
                <pre>
                  <code dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(highlighted) }} />
                </pre>
              </div>
            )
          },
          img: ({ src, alt, title }) => (
            <figure className="chat-prose__figure">
              <img src={src ?? ''} alt={alt ?? ''} title={title} loading="lazy" className="chat-prose__img" />
              {alt ? <figcaption className="chat-prose__caption">{alt}</figcaption> : null}
            </figure>
          ),
          table: ({ children }) => {
            const teaser = teaserMode && !sidebarMode
            return (
              <div className={teaser ? 'chat-prose-table-teaser' : 'chat-prose-table'}>
                <table>{children}</table>
                {teaser && onOpenWorkspace ? (
                  <button
                    aria-label="Open full table in workspace"
                    type="button"
                    className="chat-prose-table-workspace-link"
                    data-qid="chat:markdown-table:workspace"
                    onClick={onOpenWorkspace}
                  >
                    View all{tableRowCount ? ` ${tableRowCount}` : ''} rows in Workspace
                  </button>
                ) : null}
              </div>
            )
          },
          th: ({ children }) => <th>{children}</th>,
          td: ({ children }) => (
            <td>{typeof children === 'string' ? hl(children) : children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
})
