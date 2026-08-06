import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

interface DataModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  onExport?: () => void;
  children: ReactNode;
}

export default function DataModal({
  isOpen,
  onClose,
  title,
  onExport,
  children,
}: DataModalProps): JSX.Element | null {
  useEffect(() => {
    if (!isOpen) return undefined;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  if (!isOpen || typeof document === 'undefined') return null;

  return createPortal(
    <div
      data-qid="shared-chat:data-modal:backdrop"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100000,
        backgroundColor: 'rgba(5, 11, 20, 0.85)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 48,
      }}
    >
      <div
        data-qid="shared-chat:data-modal"
        onClick={(event) => event.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 1400,
          height: '100%',
          maxHeight: 900,
          backgroundColor: 'var(--surface-base)',
          border: '1px solid var(--border-default)',
          borderRadius: 12,
          boxShadow: '0 24px 64px rgba(0,0,0,0.8), 0 0 0 1px rgba(88,166,255,0.1)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 16,
            padding: '16px 24px',
            borderBottom: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--surface-raised)',
          }}
        >
          <span
            style={{
              color: 'var(--text-primary)',
              fontFamily: '"SF Mono", Consolas, monospace',
              fontSize: 13,
              fontWeight: 800,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {title}
          </span>

          <div style={{ display: 'flex', gap: 12, flexShrink: 0 }}>
            {onExport ? (
              <button
                type="button"
                data-qid="shared-chat:data-modal:export"
                onClick={onExport}
                style={{
                  background: 'var(--border-subtle)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 6,
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  padding: '6px 12px',
                  fontSize: 12,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  transition: 'background-color 0.2s, border-color 0.2s',
                }}
                onMouseEnter={(event) => {
                  event.currentTarget.style.backgroundColor = 'var(--border-default)';
                  event.currentTarget.style.borderColor = 'var(--text-muted)';
                }}
                onMouseLeave={(event) => {
                  event.currentTarget.style.backgroundColor = 'var(--border-subtle)';
                  event.currentTarget.style.borderColor = 'var(--border-default)';
                }}
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                  <path d="M4.75 2.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zM3 5.5a.75.75 0 01.75-.75h8.5a.75.75 0 010 1.5h-8.5A.75.75 0 013 5.5zm1.75 2.25a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zM6.22 11.28a.75.75 0 011.06 0l1.47 1.47V9.75a.75.75 0 011.5 0v3l1.47-1.47a.75.75 0 111.06 1.06l-2.75 2.75a.75.75 0 01-1.06 0l-2.75-2.75a.75.75 0 010-1.06z" />
                </svg>
                Export CSV
              </button>
            ) : null}

            <button
              type="button"
              data-qid="shared-chat:data-modal:close"
              onClick={onClose}
              style={{
                background: 'transparent',
                border: '1px solid var(--border-default)',
                borderRadius: 6,
                color: 'var(--text-muted)',
                cursor: 'pointer',
                padding: '6px 12px',
                fontSize: 12,
                transition: 'color 0.2s, border-color 0.2s',
              }}
              onMouseEnter={(event) => {
                event.currentTarget.style.color = 'var(--text-primary)';
                event.currentTarget.style.borderColor = 'var(--text-muted)';
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.color = 'var(--text-muted)';
                event.currentTarget.style.borderColor = 'var(--border-default)';
              }}
            >
              Close (ESC)
            </button>
          </div>
        </div>

        <div className="custom-scrollbar" style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
