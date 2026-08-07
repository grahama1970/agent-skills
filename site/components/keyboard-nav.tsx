'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { announce } from '@/lib/announce';

/** Single source of truth for active bindings; the modal renders from it. */
const SHORTCUTS = [
  {
    category: 'Navigation',
    items: [
      { keys: ['J'], desc: 'Jump to next section' },
      { keys: ['K'], desc: 'Jump to previous section' },
      { keys: ['Shift', 'G'], desc: 'Jump to page bottom' },
      { keys: ['g', 'g'], desc: 'Jump to top of page' },
      { keys: ['/'], desc: 'Search the skill ledger' },
      { keys: ['Tab'], desc: 'Cycle focusable elements' },
    ],
  },
  {
    category: 'System & View',
    items: [
      { keys: ['?'], desc: 'Toggle this shortcuts helper' },
      { keys: ['Esc'], desc: 'Close open drawer or modal' },
    ],
  },
];

const FOCUSABLES =
  'button:not([disabled]), a[href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Flash the matching header badge key so the UI visibly reacts. */
function pulseKbd(key: string) {
  document.querySelectorAll<HTMLElement>('.hint-kbd').forEach((badge) => {
    if (badge.textContent?.trim().toUpperCase() === key) {
      badge.classList.add('is-pressed');
      setTimeout(() => badge.classList.remove('is-pressed'), 180);
    }
  });
}

function isEditing() {
  const el = document.activeElement as HTMLElement | null;
  return (
    !!el &&
    (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) ||
      el.isContentEditable)
  );
}

export function KeyboardNav() {
  const [open, setOpen] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const prevFocus = useRef<HTMLElement | null>(null);
  const lastG = useRef(0);

  const close = useCallback(() => {
    setOpen(false);
    announce('Keyboard shortcuts modal closed', 'polite');
    prevFocus.current?.focus();
  }, []);

  const openModal = useCallback(() => {
    prevFocus.current = document.activeElement as HTMLElement;
    setOpen(true);
    announce('Keyboard shortcuts modal opened', 'polite');
    requestAnimationFrame(() => {
      modalRef.current?.querySelector<HTMLElement>('button')?.focus();
    });
  }, []);

  const jump = useCallback((direction: 1 | -1) => {
    const sections = Array.from(
      document.querySelectorAll<HTMLElement>('section[id]'),
    );
    if (!sections.length) return;
    const threshold = window.scrollY + 100;
    let current = 0;
    sections.forEach((s, i) => {
      if (threshold >= s.offsetTop) current = i;
    });
    const next = Math.min(Math.max(current + direction, 0), sections.length - 1);
    const target = sections[next];
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    window.dispatchEvent(
      new CustomEvent('sectionjump', { detail: { id: target.id } }),
    );
    const title = target.querySelector('h1, h2, h3');
    announce(
      `Navigated to section: ${title?.textContent?.trim() ?? target.id}`,
      'polite',
    );
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isEditing()) return;

      // Modal focus trap + escape
      if (open) {
        if (e.key === 'Escape') {
          close();
          return;
        }
        if (e.key === 'Tab' && modalRef.current) {
          const els = Array.from(
            modalRef.current.querySelectorAll<HTMLElement>(FOCUSABLES),
          );
          if (!els.length) return;
          const first = els[0];
          const last = els[els.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
          return;
        }
      }

      if (e.key === '?') {
        e.preventDefault();
        open ? close() : openModal();
      } else if (e.key === '/') {
        // Advertised in the help as "Search the skill ledger" — focus the
        // capability search and bring it into view.
        const input = document.getElementById('capsearch-input');
        if (input) {
          e.preventDefault();
          input.scrollIntoView({ behavior: 'smooth', block: 'center' });
          (input as HTMLInputElement).focus();
        }
      } else if (e.key === 'j') {
        e.preventDefault();
        pulseKbd('J');
        jump(1);
      } else if (e.key === 'k') {
        e.preventDefault();
        pulseKbd('K');
        jump(-1);
      } else if (e.key === 'G' || e.key === 'End') {
        e.preventDefault();
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        announce('Navigated to bottom of page', 'polite');
      } else if (e.key === 'g') {
        const now = Date.now();
        if (now - lastG.current < 350) {
          e.preventDefault();
          window.scrollTo({ top: 0, behavior: 'smooth' });
          announce('Navigated to top of page', 'polite');
          lastG.current = 0;
        } else {
          lastG.current = now;
        }
      } else if (e.key === 'Home') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        announce('Navigated to top of page', 'polite');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close, openModal, jump]);

  return (
    <>
      <button
        type="button"
        data-qid="nav:action:shortcuts"
        data-qs-action="NAV_OPEN_SHORTCUTS"
        title="Keyboard shortcuts — press J/K to jump sections, ? for help"
        onClick={() => (open ? close() : openModal())}
        className="machine hidden items-center gap-1.5 rounded border border-line px-2 py-1 text-mute hover:border-accent hover:text-ink md:inline-flex"
      >
        <span className="uppercase tracking-wide">Nav</span>
        <kbd className="hint-kbd rounded border border-line bg-paper px-1.5 py-0.5 text-[0.675rem] font-semibold text-ink">
          J
        </kbd>
        <kbd className="hint-kbd rounded border border-line bg-paper px-1.5 py-0.5 text-[0.675rem] font-semibold text-ink">
          K
        </kbd>
      </button>

      <div
        className={`modal-overlay${open ? ' is-active' : ''}`}
        aria-hidden="true"
        onClick={close}
      />
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcut-modal-title"
        aria-hidden={!open}
        className={`shortcut-modal${open ? ' is-active' : ''}`}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <span aria-hidden="true" className="text-accent">⌨</span>
            <h2 id="shortcut-modal-title" className="machine !text-[0.95rem] font-bold text-ink">
              Keyboard Shortcuts
            </h2>
          </div>
          <button
            type="button"
            data-qid="shortcuts:action:close"
            data-qs-action="SHORTCUTS_CLOSE"
            title="Close shortcuts modal"
            onClick={close}
            className="rounded px-2 text-xl leading-none text-mute hover:text-ink"
          >
            ×
          </button>
        </div>
        <div className="flex flex-col gap-5 p-5">
          {SHORTCUTS.map((group) => (
            <div key={group.category}>
              <h3 className="machine mb-2 uppercase tracking-wider text-mute">
                {group.category}
              </h3>
              <dl className="m-0 flex flex-col gap-1.5">
                {group.items.map((item) => (
                  <div
                    key={item.desc}
                    className="flex items-center justify-between text-[0.8rem]"
                  >
                    <dt className="m-0">
                      {item.keys.map((k, i) => (
                        <span key={k + i}>
                          {i > 0 && <span className="text-mute"> + </span>}
                          <kbd className="machine rounded border border-line bg-paper px-1.5 py-0.5 text-[0.725rem] font-semibold text-ink">
                            {k}
                          </kbd>
                        </span>
                      ))}
                    </dt>
                    <dd className="machine m-0 text-mute">{item.desc}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
        <div className="machine border-t border-line px-5 py-3 text-center text-mute">
          Press ? or Esc anytime to dismiss
        </div>
      </div>
    </>
  );
}
