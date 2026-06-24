/**
 * MarkdownRenderer — Shared markdown rendering with entity highlighting + syntax highlighting.
 * Used by Embry Terminal and SPARTA Explorer chat.
 */
import { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';
import go from 'highlight.js/lib/languages/go';
import python from 'highlight.js/lib/languages/python';
import typescript from 'highlight.js/lib/languages/typescript';
import javascript from 'highlight.js/lib/languages/javascript';
import bash from 'highlight.js/lib/languages/bash';
import json from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import rust from 'highlight.js/lib/languages/rust';
import { highlightEntities } from './highlightEntities';
import type { EntityType } from './types';

// Register languages once
hljs.registerLanguage('go', go);
hljs.registerLanguage('python', python);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('shell', bash);
hljs.registerLanguage('json', json);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('tsx', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('py', python);
hljs.registerLanguage('sh', bash);

interface MarkdownRendererProps {
  content: string;
  onEntityClick?: (entity: string, type: EntityType) => void;
  /** Legacy: cap tables at 3 rows with fade + workspace link (non-sidebar only) */
  teaserMode?: boolean;
  /** Gemini sidebar: full readable prose/tables on flat canvas */
  sidebarMode?: boolean;
  onOpenWorkspace?: () => void;
  tableRowCount?: number;
}

export const MarkdownRenderer = memo(function MarkdownRenderer({ content, onEntityClick, teaserMode = false, sidebarMode = false, onOpenWorkspace, tableRowCount }: MarkdownRendererProps) {
  // Sidebar: clean reading surface — no neon entity underlines (workspace owns that).
  const hl = (text: string) => sidebarMode ? text : highlightEntities(text, onEntityClick);

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
          const lang = className?.replace('language-', '') || '';
          const text = String(children).replace(/\n$/, '');
          if (!className) {
            if (sidebarMode) {
              return <code className="chat-prose__code">{text}</code>;
            }
            return (
              <code style={{
                fontFamily: 'var(--font-mono, monospace)', fontSize: 13,
                background: '#0b1220', padding: '2px 6px', borderRadius: 4, color: '#4a9eff',
              }}>
                {text}
              </code>
            );
          }
          let highlighted = text;
          try {
            highlighted = lang && hljs.getLanguage(lang)
              ? hljs.highlight(text, { language: lang }).value
              : hljs.highlightAuto(text).value;
          } catch { /* fallback */ }
          return (
            <div style={{ margin: '12px 0', overflow: 'hidden', background: '#0b1220', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8 }}>
              {lang && (
                <div style={{
                  padding: '6px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)',
                  fontSize: 11, fontFamily: 'var(--font-mono, monospace)', color: '#64748b', textTransform: 'uppercase',
                }}>
                  {lang}
                </div>
              )}
              <pre style={{ margin: 0, padding: 12, fontFamily: 'var(--font-mono, monospace)', fontSize: 13, color: '#e2e8f0', overflowX: 'auto', lineHeight: 1.5 }}>
                <code dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(highlighted) }} />
              </pre>
            </div>
          );
        },
        img: ({ src, alt, title }) => (
          <figure className="chat-prose__figure">
            <img src={src} alt={alt ?? ''} title={title} loading="lazy" className="chat-prose__img" />
            {alt ? <figcaption className="chat-prose__caption">{alt}</figcaption> : null}
          </figure>
        ),
        table: ({ children }) => {
          const teaser = teaserMode && !sidebarMode;
          return (
            <div className={teaser ? 'chat-prose-table-teaser' : 'chat-prose-table'}>
              <table>{children}</table>
              {teaser && onOpenWorkspace ? (
                <button type="button" className="chat-prose-table-workspace-link" data-qid="chat:markdown-table:workspace" onClick={onOpenWorkspace}>
                  ↗ View all{tableRowCount ? ` ${tableRowCount}` : ''} rows in Workspace
                </button>
              ) : null}
            </div>
          );
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
  );
});
