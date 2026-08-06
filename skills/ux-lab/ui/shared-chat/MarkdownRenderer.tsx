/**
 * MarkdownRenderer — Shared markdown rendering with entity highlighting + syntax highlighting.
 * Used by Embry Terminal and SPARTA Explorer chat.
 */
import { Children, Fragment, isValidElement, memo, useCallback, useMemo, useState } from 'react';
import type { CSSProperties, ReactElement, ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { AlertTriangle, FileText, PlayCircle, Search, Sparkles } from 'lucide-react';
import { classifyEntity, getEntityStyle, highlightWithSpans } from './highlightEntities';
import DynamicChart from './DynamicChart';
import DataModal from './DataModal';
import CodeBlockWithCopy from './CodeBlockWithCopy';
import { csvEscape, triggerCSVDownload } from './downloadUtils';
import type { EntityType, EvidenceCaseSpan } from './types';
import { useRegisterAction } from './_support/useRegisterAction';

interface MarkdownRendererProps {
  content: string;
  onEntityClick?: (entity: string, type: EntityType) => void;
  /** Deterministic spans from /memory /extract-entities. These take precedence over static fallback highlighting. */
  entitySpans?: EvidenceCaseSpan[];
  /** Legacy: cap tables at 3 rows with fade + workspace link (non-sidebar only) */
  teaserMode?: boolean;
  /** Gemini sidebar: full readable prose/tables on flat canvas */
  sidebarMode?: boolean;
  onOpenWorkspace?: () => void;
  tableRowCount?: number;
  /** Optional: convert filesystem paths to URLs for inline media (image=/path, clip=/path, audio=/path) */
  mediaUrl?: (path: string) => string;
}

function preprocessMedia(content: string, mediaUrl?: (path: string) => string): string {
  if (!content) return content;
  const toUrl = (path: string) => mediaUrl ? mediaUrl(path) : path;
  return content
    .replace(/(?:^|[\s|])image=(\S+)/gm, (_match, path) => `![image](${toUrl(path)})`)
    .replace(/(?:^|[\s|])clip=(\S+)/gm, (_match, path) => `![clip](${toUrl(path)})`)
    .replace(/(?:^|[\s|])audio=(\S+)/gm, (_match, path) => `![audio](${toUrl(path)})`);
}

function isVideo(src?: string): boolean {
  return !!src && /\.(mp4|webm|mov|mkv|avi)$/i.test(src);
}

function isAudio(src?: string): boolean {
  return !!src && /\.(mp3|wav|ogg|m4a|flac|aac)$/i.test(src);
}

function textFromChildren(children: ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(textFromChildren).join('');
  return '';
}

type SpartaActionPayload = {
  title?: string;
  description?: string;
  buttonLabel?: string;
  label?: string;
  qsAction?: string;
  dataQsAction?: string;
  action?: string;
}

function qidToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'action';
}

function parseSpartaAction(rawJson: string): { payload?: SpartaActionPayload; error?: string } {
  try {
    const parsed = JSON.parse(rawJson) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { error: 'Action payload must be a JSON object.' };
    }
    return { payload: parsed as SpartaActionPayload };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Invalid JSON.' };
  }
}

function SpartaActionCard({ rawJson }: { rawJson: string }): JSX.Element {
  const [status, setStatus] = useState<'idle' | 'executed' | 'missing'>('idle');
  const { payload, error } = useMemo(() => parseSpartaAction(rawJson), [rawJson]);
  const title = payload?.title || payload?.label || 'Console Action';
  const description = payload?.description || 'Review the generated action before execution.';
  const actionId = payload?.qsAction || payload?.dataQsAction || payload?.action || '';
  const qid = `shared-chat:sparta-action:${qidToken(actionId || title)}`;

  useRegisterAction(qid, {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_EXECUTE_SPARTA_ACTION_CARD',
    label: title,
    description: `Execute generated Sparta Console action card: ${title}`,
  });

  const handleExecute = () => {
    if (!actionId) {
      setStatus('missing');
      return;
    }
    const target = document.querySelector<HTMLElement>(`[data-qs-action="${CSS.escape(actionId)}"]`);
    if (!target) {
      setStatus('missing');
      return;
    }
    target.click();
    setStatus('executed');
  };

  if (error) {
    return (
      <div
        data-qid={`${qid}:parse-error`}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          margin: '12px 0',
          padding: 12,
          border: '1px solid rgba(248, 81, 73, 0.42)',
          borderRadius: 8,
          background: 'rgba(248, 81, 73, 0.08)',
          color: '#fca5a5',
          fontSize: 12,
        }}
      >
        <AlertTriangle size={15} aria-hidden="true" />
        <span>Failed to parse sparta-action JSON: {error}</span>
      </div>
    );
  }

  return (
    <div
      data-qid={qid}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        margin: '14px 0',
        padding: 14,
        border: '1px solid rgba(88, 166, 255, 0.28)',
        borderRadius: 10,
        background: 'rgba(15, 23, 42, 0.62)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, minWidth: 0 }}>
        <span
          aria-hidden="true"
          style={{
            width: 28,
            height: 28,
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
            borderRadius: 8,
            color: '#58a6ff',
            background: 'rgba(88, 166, 255, 0.10)',
            border: '1px solid rgba(88, 166, 255, 0.18)',
          }}
        >
          <Sparkles size={15} />
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 750, marginBottom: 4 }}>{title}</div>
          <div style={{ color: '#94a3b8', fontSize: 12, lineHeight: 1.45 }}>{description}</div>
          {!actionId ? (
            <div style={{ color: '#fbbf24', fontSize: 11, marginTop: 8 }}>
              Backend action contract required: add `qsAction` to enable execution.
            </div>
          ) : status === 'missing' ? (
            <div style={{ color: '#fbbf24', fontSize: 11, marginTop: 8 }}>
              No live control found for data-qs-action `{actionId}`.
            </div>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        data-qid={`${qid}:execute`}
        data-qs-action="SHARED_CHAT_EXECUTE_SPARTA_ACTION_CARD"
        title={actionId ? `Execute ${actionId}` : 'Backend action contract required'}
        onClick={handleExecute}
        disabled={!actionId}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          minHeight: 36,
          flexShrink: 0,
          padding: '0 12px',
          border: '1px solid',
          borderColor: actionId ? 'rgba(88, 166, 255, 0.5)' : 'rgba(148, 163, 184, 0.22)',
          borderRadius: 8,
          background: actionId ? '#1d4ed8' : 'rgba(15, 23, 42, 0.4)',
          color: actionId ? '#eff6ff' : '#64748b',
          cursor: actionId ? 'pointer' : 'not-allowed',
          fontSize: 12,
          fontWeight: 700,
        }}
      >
        <PlayCircle size={14} aria-hidden="true" />
        {status === 'executed' ? 'Executed' : payload?.buttonLabel || 'Execute'}
      </button>
    </div>
  );
}

function splitTranscriptLine(text: string): { meta: string; body: string; visual?: string } | null {
  const match = text.match(/^(\d{2}:\d{2}(?:\s*\([^)]*\))?)(?:\s*\[[^\]]+\])?\s*:\s*([\s\S]+)$/);
  if (!match) return null;
  const [, meta, rawBody] = match;
  const [body, visual] = rawBody.split(/\s+visual:\s*\d+\.\s*/i);
  return {
    meta: meta.trim(),
    body: body.trim(),
    visual: visual?.replace(/\s*\|+\s*$/, '').trim(),
  };
}

function previewText(text: string, maxLength = 92): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}...`;
}

function extractTextFromNode(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (!node) return '';
  if (Array.isArray(node)) return node.map(extractTextFromNode).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) return extractTextFromNode(node.props.children);
  return '';
}

function isElementWithChildren(node: ReactNode): node is ReactElement<{
  children?: ReactNode;
  node?: { tagName?: string };
}> {
  return isValidElement(node);
}

function markdownTagName(node: ReactNode): string | null {
  if (!isElementWithChildren(node)) return null;
  if (typeof node.type === 'string') return node.type;
  return node.props.node?.tagName ?? null;
}

function InteractiveTableRow({ children }: { children?: ReactNode }): JSX.Element {
  const [isHovered, setHovered] = useState(false);
  return (
    <tr
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        backgroundColor: isHovered ? 'rgba(88, 166, 255, 0.08)' : 'transparent',
        transition: 'background-color 0.15s ease',
      }}
    >
      {children}
    </tr>
  );
}

const RECOGNIZED_SKILL_NAMES = new Set([
  'memory',
  'extract-entities',
  'create-evidence-case',
  'create-qras',
  'create-figure',
  'qra-review',
  'sparta-review',
  'lean4-prove',
]);
const FALLBACK_ENTITY_REGEX = /([$\/][a-z][a-z0-9-]*|[A-Z0-9]{2,}-[A-Z0-9]{2,}-\d+|[A-Z]{2,}-\d+)/g;
const FALLBACK_ENTITY_TEST_REGEX = /^[$\/][a-z][a-z0-9-]*$|^[A-Z0-9]{2,}-[A-Z0-9]{2,}-\d+$|^[A-Z]{2,}-\d+$/i;

function highlightFallbackEntities(
  text: string,
  onEntityClick?: (entity: string, type: EntityType) => void,
): ReactNode[] {
  const parts = text.split(FALLBACK_ENTITY_REGEX);
  return parts.map((part, index) => {
    if (!FALLBACK_ENTITY_TEST_REGEX.test(part)) return part;
    const isSkillToken = part.startsWith('/') || part.startsWith('$');
    if (isSkillToken && !RECOGNIZED_SKILL_NAMES.has(part.slice(1).toLowerCase())) return part;
    const type: EntityType = isSkillToken ? 'skill' : classifyEntity(part);
    const style = getEntityStyle(type);
    return (
      <span
        key={`${part}-${index}`}
        data-qid={`shared-chat:markdown-entity:${qidToken(part)}`}
        data-qs-action="SHARED_CHAT_SELECT_MARKDOWN_ENTITY"
        data-entity-type={type}
        data-entity-text={part}
        title={isSkillToken ? `Recognized skill: ${part}` : `${type}: ${part}`}
        onClick={onEntityClick ? () => onEntityClick(part, type) : undefined}
        style={{
          color: 'inherit',
          borderBottom: `2px solid ${style.color}aa`,
          fontFamily: type === 'skill' ? 'var(--font-mono, monospace)' : 'inherit',
          cursor: onEntityClick ? 'pointer' : 'help',
          textUnderlineOffset: 4,
        }}
      >
        {part}
      </span>
    );
  });
}

function highlightInlineChildren(
  children: ReactNode,
  highlightText: (text: string) => ReactNode,
): ReactNode {
  if (typeof children === 'string' || typeof children === 'number') {
    return highlightText(String(children));
  }
  if (Array.isArray(children)) {
    return Children.toArray(children).map((child, index) => (
      <Fragment key={index}>
        {typeof child === 'string' || typeof child === 'number'
          ? highlightText(String(child))
          : child}
      </Fragment>
    ));
  }
  return children;
}

function modalButtonStyle(disabled: boolean): CSSProperties {
  return {
    backgroundColor: disabled ? 'transparent' : 'var(--border-subtle)',
    color: disabled ? '#484f58' : 'var(--text-primary)',
    border: '1px solid',
    borderColor: disabled ? 'var(--border-subtle)' : 'var(--border-default)',
    borderRadius: 4,
    padding: '4px 10px',
    fontSize: 11,
    fontFamily: '"SF Mono", Consolas, monospace',
    cursor: disabled ? 'not-allowed' : 'pointer',
    transition: 'background-color 0.2s, color 0.2s, border-color 0.2s',
  };
}

function ExpandableTable({
  children,
  teaserMode,
  sidebarMode,
  tableRowCount,
  onOpenWorkspace,
}: {
  children?: ReactNode;
  teaserMode: boolean;
  sidebarMode: boolean;
  tableRowCount?: number;
  onOpenWorkspace?: () => void;
}): JSX.Element {
  const [isExpanded, setExpanded] = useState(false);
  const [isHovered, setHovered] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(15);

  useRegisterAction('shared-chat:table:previous-page', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_TABLE_PREVIOUS_PAGE',
    label: 'Previous table page',
    description: 'Navigate to the previous page in an expanded markdown table',
  });
  useRegisterAction('shared-chat:table:next-page', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_TABLE_NEXT_PAGE',
    label: 'Next table page',
    description: 'Navigate to the next page in an expanded markdown table',
  });

  const { thead, allRows } = useMemo(() => {
    const childrenArray = Children.toArray(children);
    const headNode = childrenArray.find((child) => markdownTagName(child) === 'thead');
    const bodyNode = childrenArray.find((child) => markdownTagName(child) === 'tbody');

    return {
      thead: headNode,
      allRows: isElementWithChildren(bodyNode)
        ? Children.toArray(bodyNode.props.children)
        : childrenArray.filter((child) => markdownTagName(child) === 'tr'),
    };
  }, [children]);

  const totalRows = allRows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / rowsPerPage));
  const startIndex = (currentPage - 1) * rowsPerPage;
  const inFeedRows = allRows.slice(0, 5);
  const paginatedRows = allRows.slice(startIndex, startIndex + rowsPerPage);
  const teaser = teaserMode && !sidebarMode;

  const exportTableToCSV = () => {
    const headerRow = Children.toArray(isElementWithChildren(thead) ? thead.props.children : [])[0];
    const headerCells = Children.toArray(isElementWithChildren(headerRow) ? headerRow.props.children : []);
    const csvHeaders = headerCells.map((cell) => csvEscape(extractTextFromNode(cell))).join(',');
    const csvRows = allRows.map((row) => {
      const cells = Children.toArray(isElementWithChildren(row) ? row.props.children : []);
      return cells.map((cell) => csvEscape(extractTextFromNode(cell))).join(',');
    });
    const csvString = csvHeaders ? [csvHeaders, ...csvRows].join('\n') : csvRows.join('\n');
    triggerCSVDownload(csvString, `sparta_dataset_${Date.now()}.csv`);
  };

  return (
    <>
      <div
        data-qid="shared-chat:markdown-table"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        style={{ position: 'relative', margin: '12px 0' }}
      >
        <button
          type="button"
          data-qid="shared-chat:table:expand"
          onClick={() => setExpanded(true)}
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            zIndex: 10,
            backgroundColor: 'var(--border-subtle)',
            color: 'var(--text-primary)',
            border: '1px solid #484f58',
            borderRadius: 6,
            padding: '4px 8px',
            fontSize: 11,
            cursor: 'pointer',
            opacity: isHovered ? 1 : 0,
            transition: 'opacity 0.2s',
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          }}
        >
          Expand Grid
        </button>

        <div
          className={`custom-scrollbar ${teaser ? 'chat-prose-table-teaser' : 'chat-prose-table'}`}
          style={{
            width: '100%',
            overflowX: 'auto',
            backgroundColor: 'var(--surface-base)',
            border: '1px solid var(--border-default)',
            borderRadius: 6,
            boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.02)',
          }}
        >
          <table
            style={{
              width: 'max-content',
              minWidth: '100%',
              borderCollapse: 'collapse',
              fontSize: 12,
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            }}
          >
            {thead}
            <tbody>{inFeedRows}</tbody>
          </table>
          {totalRows > 5 ? (
            <div
              data-qid="shared-chat:table:overflow-indicator"
              style={{
                padding: 8,
                textAlign: 'center',
                backgroundColor: 'var(--surface-raised)',
                borderTop: '1px solid var(--border-default)',
                color: 'var(--text-muted)',
                fontSize: 10,
                fontFamily: '"SF Mono", Consolas, monospace',
              }}
            >
              +{totalRows - 5} MORE ROWS - CLICK EXPAND
            </div>
          ) : null}
          {teaser && onOpenWorkspace ? (
            <button type="button" className="chat-prose-table-workspace-link" data-qid="chat:markdown-table:workspace" onClick={onOpenWorkspace}>
              View all{tableRowCount ? ` ${tableRowCount}` : ''} rows in Workspace
            </button>
          ) : null}
        </div>
      </div>

      <DataModal
        isOpen={isExpanded}
        onClose={() => setExpanded(false)}
        title={`DATA GRID: ${totalRows} RECORDS`}
        onExport={exportTableToCSV}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 560 }}>
          <div
            className="custom-scrollbar"
            style={{
              flex: 1,
              overflow: 'auto',
              backgroundColor: 'var(--surface-base)',
              border: '1px solid var(--border-default)',
              borderRadius: '6px 6px 0 0',
              borderBottom: 'none',
            }}
          >
            <table
              style={{
                width: 'max-content',
                minWidth: '100%',
                borderCollapse: 'collapse',
                fontSize: 14,
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              }}
            >
              {thead}
              <tbody>{paginatedRows}</tbody>
            </table>
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              padding: '12px 16px',
              backgroundColor: 'var(--surface-raised)',
              border: '1px solid var(--border-default)',
              borderRadius: '0 0 6px 6px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <select
                data-qid="shared-chat:table:rows-per-page"
                value={rowsPerPage}
                onChange={(event) => {
                  setRowsPerPage(Number(event.target.value));
                  setCurrentPage(1);
                }}
                style={{
                  backgroundColor: 'var(--surface-base)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 4,
                  padding: '4px 8px',
                  fontSize: 11,
                  fontFamily: '"SF Mono", Consolas, monospace',
                }}
              >
                <option value={15}>15 rows</option>
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
              </select>
              <span style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: '"SF Mono", Consolas, monospace' }}>
                PAGE {currentPage} OF {totalPages}
              </span>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                data-qid="shared-chat:table:previous-page"
                data-qs-action="SHARED_CHAT_TABLE_PREVIOUS_PAGE"
                title="Previous table page"
                onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                disabled={currentPage === 1}
                style={modalButtonStyle(currentPage === 1)}
              >
                PREV
              </button>
              <button
                type="button"
                data-qid="shared-chat:table:next-page"
                data-qs-action="SHARED_CHAT_TABLE_NEXT_PAGE"
                title="Next table page"
                onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                disabled={currentPage === totalPages}
                style={modalButtonStyle(currentPage === totalPages)}
              >
                NEXT
              </button>
            </div>
          </div>
        </div>
      </DataModal>
    </>
  );
}

export const MarkdownRenderer = memo(function MarkdownRenderer({ content, onEntityClick, entitySpans = [], teaserMode = false, sidebarMode = false, onOpenWorkspace, tableRowCount, mediaUrl }: MarkdownRendererProps) {
  useRegisterAction('shared-chat:markdown-entity:select', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_SELECT_MARKDOWN_ENTITY',
    label: 'Select markdown entity',
    description: 'Select a highlighted entity in rendered markdown content',
  });

  const processedContent = preprocessMedia(content, mediaUrl);

  // sparta#48: hl and the components map below must be referentially stable —
  // inline definitions remounted the entire markdown subtree on every parent
  // re-render (e.g. message hover), destroying entity-token hover state.
  const hl = useCallback((text: string) => {
    if (!entitySpans.length) return highlightFallbackEntities(text, onEntityClick);

    // /extract-entities spans are authoritative and are indexed against the
    // full source text. ReactMarkdown renders smaller text nodes, so project
    // those deterministic spans into each text node without re-parsing text.
    const start = processedContent.indexOf(text);
    if (start < 0) {
      const directSpans = text === processedContent
        ? entitySpans.filter((span): span is EvidenceCaseSpan & { span: [number, number] } => (
          Array.isArray(span.span)
          && span.span.length === 2
          && span.span[0] >= 0
          && span.span[1] <= text.length
        ))
        : [];
      if (directSpans.length) return highlightWithSpans(text, directSpans, onEntityClick);
      return text;
    }
    const end = start + text.length;
    let localSpans = entitySpans
      .filter((span): span is EvidenceCaseSpan & { span: [number, number] } => (
        Array.isArray(span.span)
        && span.span.length === 2
        && span.span[0] >= start
        && span.span[1] <= end
      ))
      .map((span) => ({
        ...span,
        span: [span.span[0] - start, span.span[1] - start] as [number, number],
      }));
    if (!localSpans.length && text === processedContent) {
      localSpans = entitySpans.filter((span): span is EvidenceCaseSpan & { span: [number, number] } => (
        Array.isArray(span.span)
        && span.span.length === 2
        && span.span[0] >= 0
        && span.span[1] <= text.length
      ));
    }
    if (localSpans.length) return highlightWithSpans(text, localSpans, onEntityClick);
    return highlightFallbackEntities(text, onEntityClick);
  }, [entitySpans, onEntityClick, processedContent]);

  const markdownComponents = useMemo<Components>(() => ({
        p: ({ children }) => (
          <p style={{ margin: '0 0 12px 0' }}>
            {highlightInlineChildren(children, hl)}
          </p>
        ),
        strong: ({ children }) => (
          <strong style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
            {highlightInlineChildren(children, hl)}
          </strong>
        ),
        h1: ({ children }) => <h1>{children}</h1>,
        h2: ({ children }) => <h2>{children}</h2>,
        h3: ({ children }) => <h3>{children}</h3>,
        h4: ({ children }) => <h4>{children}</h4>,
        ul: ({ children }) => <ul style={{ margin: '0 0 12px 20px', padding: 0 }}>{children}</ul>,
        ol: ({ children }) => <ol style={{ margin: '0 0 12px 20px', padding: 0 }}>{children}</ol>,
        li: ({ children }) => {
          if (sidebarMode) {
            const transcript = splitTranscriptLine(textFromChildren(children));
            if (transcript) {
              return (
                <li className="chat-prose__transcript-row">
                  <details className="chat-prose__evidence-card">
                    <summary className="chat-prose__evidence-summary">
                      <span className="chat-prose__transcript-meta">{transcript.meta}</span>
                      <span className="chat-prose__evidence-preview">{previewText(transcript.body)}</span>
                      <span className="chat-prose__evidence-actions" title="View evidence" aria-label="View evidence">
                        <FileText size={14} strokeWidth={1.8} aria-hidden="true" />
                        <Search size={13} strokeWidth={1.8} aria-hidden="true" />
                      </span>
                    </summary>
                    <span className="chat-prose__transcript-text">{transcript.body}</span>
                    {transcript.visual ? (
                      <span className="chat-prose__transcript-visual">{transcript.visual}</span>
                    ) : null}
                  </details>
                </li>
              );
            }
          }
          return (
            <li style={{ marginBottom: 6 }}>
              {highlightInlineChildren(children, hl)}
            </li>
          );
        },
	        code: ({ className, children }) => {
	          const language = className?.replace('language-', '') || '';
	          const text = textFromChildren(children).replace(/\n$/, '');
	          if (className && language === 'chart') return <DynamicChart rawJson={text} />;
	          if (className && language === 'sparta-action') return <SpartaActionCard rawJson={text} />;
	          if (!className) {
            if (sidebarMode) return <code className="chat-prose__code">{text}</code>;
            return (
              <code
                style={{
                  backgroundColor: 'rgba(139, 148, 158, 0.15)',
                  padding: '2px 6px',
                  borderRadius: 4,
                  fontFamily: '"SF Mono", Consolas, monospace',
                  fontSize: 12,
                  color: '#c9d1d9',
                }}
              >
                {text}
              </code>
            );
          }
          return <CodeBlockWithCopy language={language}>{text}</CodeBlockWithCopy>;
        },
        img: ({ src, alt, title }) => {
          if (isVideo(src)) {
            return (
              <video
                src={src}
                title={title ?? alt ?? ''}
                controls
                preload="metadata"
                className="chat-prose__video"
                style={{ maxWidth: '100%', borderRadius: 12, display: 'block', margin: '8px 0' }}
              />
            );
          }
          if (isAudio(src)) {
            return (
              <audio
                src={src}
                title={title ?? alt ?? ''}
                controls
                preload="none"
                className="chat-prose__audio"
                style={{ width: '100%', margin: '8px 0' }}
              />
            );
          }
          return (
            <>
              <img src={src} alt={alt ?? ''} title={title} loading="lazy" className="chat-prose__img" />
              {alt ? <span className="chat-prose__caption">{alt}</span> : null}
            </>
          );
        },
        table: ({ children }) => (
          <ExpandableTable
            teaserMode={teaserMode}
            sidebarMode={sidebarMode}
            tableRowCount={tableRowCount}
            onOpenWorkspace={onOpenWorkspace}
          >
            {children}
          </ExpandableTable>
        ),
        tr: ({ children }) => <InteractiveTableRow>{children}</InteractiveTableRow>,
        th: ({ children }) => (
          <th
            style={{
              padding: '10px 12px',
              backgroundColor: 'var(--surface-raised)',
              color: 'var(--text-muted)',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              fontSize: 10,
              borderBottom: '1px solid var(--border-default)',
              whiteSpace: 'nowrap',
              textAlign: 'left',
            }}
          >
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td
            style={{
              padding: '8px 12px',
              color: '#c9d1d9',
              borderBottom: '1px solid var(--border-subtle)',
              verticalAlign: 'top',
              whiteSpace: 'nowrap',
            }}
          >
            {highlightInlineChildren(children, hl)}
          </td>
        ),
  }), [hl, teaserMode, sidebarMode, onOpenWorkspace, tableRowCount, mediaUrl, onEntityClick]);

  return (
    <div className={sidebarMode ? 'chat-prose chat-prose--sidebar' : 'chat-prose'}>
    <style>
      {`
        .katex-display {
          overflow-x: auto;
          overflow-y: hidden;
          padding-bottom: 8px;
          margin: 12px 0;
        }
        .katex-display::-webkit-scrollbar { height: 6px; }
        .katex-display::-webkit-scrollbar-track { background: transparent; }
        .katex-display::-webkit-scrollbar-thumb { background-color: var(--border-default); border-radius: 3px; }
        .katex-display:hover::-webkit-scrollbar-thumb { background-color: #484f58; }

        .katex {
          color: var(--text-primary);
        }
        .katex .mathnormal {
          color: #79c0ff;
        }
        .katex .mbin,
        .katex .mrel,
        .katex .mop {
          color: #ff7b72;
        }
        .katex .mord {
          color: #c9d1d9;
        }
        .katex .frac-line,
        .katex .overline .overline-line,
        .katex .underline .underline-line,
        .katex .hline,
        .katex .sqrt-line {
          border-color: var(--border-default) !important;
          border-bottom-color: var(--border-default) !important;
        }
        .katex svg path {
          stroke: var(--border-default);
        }
      `}
    </style>
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={markdownComponents}
    >
      {processedContent}
    </ReactMarkdown>
    </div>
  );
});
