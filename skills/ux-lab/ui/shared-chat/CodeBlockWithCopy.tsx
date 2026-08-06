import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useRegisterAction } from './_support/useRegisterAction';

interface CodeBlockWithCopyProps {
  language?: string;
  children: string;
}

export default function CodeBlockWithCopy({
  language,
  children,
}: CodeBlockWithCopyProps): JSX.Element {
  const [isCopied, setCopied] = useState(false);
  const normalizedLanguage = language || 'text';

  useRegisterAction('shared-chat:code-block:copy', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_COPY_CODE_BLOCK',
    label: 'Copy code block',
    description: 'Copy a rendered code block to the clipboard',
  });

  const handleCopy = () => {
    if (!navigator.clipboard) return;
    void navigator.clipboard.writeText(children).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div
      data-qid="shared-chat:code-block"
      style={{
        margin: '12px 0',
        backgroundColor: 'var(--surface-base)',
        border: '1px solid var(--border-default)',
        borderRadius: 8,
        overflow: 'hidden',
        boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 16px',
          backgroundColor: 'var(--surface-raised)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span
          style={{
            color: 'var(--text-muted)',
            fontFamily: '"SF Mono", Consolas, monospace',
            fontSize: 11,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          {normalizedLanguage}
        </span>

        <button
          type="button"
          data-qid="shared-chat:code-block:copy"
          data-qs-action="SHARED_CHAT_COPY_CODE_BLOCK"
          onClick={handleCopy}
          title={isCopied ? 'Copied code' : 'Copy code'}
          style={{
            background: 'transparent',
            border: 'none',
            color: isCopied ? '#3fb950' : 'var(--text-muted)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 11,
            fontFamily: '"SF Mono", Consolas, monospace',
            transition: 'color 0.2s ease',
          }}
          onMouseEnter={(event) => {
            if (!isCopied) event.currentTarget.style.color = 'var(--text-primary)';
          }}
          onMouseLeave={(event) => {
            if (!isCopied) event.currentTarget.style.color = 'var(--text-muted)';
          }}
        >
          {isCopied ? (
            <>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
              </svg>
              Copied
            </>
          ) : (
            <>
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 010 1.5h-1.5a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-1.5a.75.75 0 011.5 0v1.5A1.75 1.75 0 019.25 16h-7.5A1.75 1.75 0 010 14.25v-7.5z" />
                <path fillRule="evenodd" d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0114.25 11h-7.5A1.75 1.75 0 015 9.25v-7.5zm1.75-.25a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25h-7.5z" />
              </svg>
              Copy
            </>
          )}
        </button>
      </div>

      <div className="custom-scrollbar" style={{ width: '100%', overflowX: 'auto' }}>
        <SyntaxHighlighter
          language={normalizedLanguage}
          style={vscDarkPlus}
          customStyle={{
            margin: 0,
            padding: 16,
            backgroundColor: 'transparent',
            fontSize: 12,
            fontFamily: '"SF Mono", Consolas, monospace',
            lineHeight: 1.5,
          }}
          PreTag="div"
          CodeTag="div"
        >
          {children}
        </SyntaxHighlighter>
      </div>
    </div>
  );
}
