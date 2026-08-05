'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { announce } from '@/lib/announce';

const LINKS = [
  { id: 'work', label: 'Work' },
  { id: 'dream', label: 'Dream' },
  { id: 'index', label: 'Skill index' },
  { id: 'about', label: 'About' },
  { id: 'contact', label: 'Contact' },
];

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const prevFocus = useRef<HTMLElement | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    document.body.style.overflow = '';
    announce('Navigation drawer collapsed', 'polite');
    prevFocus.current?.focus();
  }, []);

  const openDrawer = () => {
    prevFocus.current = document.activeElement as HTMLElement;
    setOpen(true);
    document.body.style.overflow = 'hidden';
    announce('Navigation drawer expanded', 'polite');
    requestAnimationFrame(() => {
      drawerRef.current
        ?.querySelector<HTMLElement>('button, a[href]')
        ?.focus();
    });
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close();
        return;
      }
      if (e.key !== 'Tab' || !drawerRef.current) return;
      const focusables = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS),
      ).filter(
        (el) =>
          el.offsetWidth > 0 ||
          el.offsetHeight > 0 ||
          el.getClientRects().length > 0,
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, close]);

  const toggleTheme = () => {
    const root = document.documentElement;
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    localStorage.setItem('theme', next);
    announce(`Color theme changed to ${next} mode`, 'polite');
  };

  const copyEmail = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    try {
      e.preventDefault();
      await navigator.clipboard.writeText('graham@grahama.co');
      announce('Copied email graham@grahama.co to clipboard', 'assertive');
      close();
    } catch {
      window.location.href = 'mailto:graham@grahama.co';
    }
  };

  return (
    <>
      <button
        ref={toggleRef}
        type="button"
        data-qid="nav:action:mobile-menu"
        data-qs-action="NAV_TOGGLE_MOBILE_MENU"
        title="Toggle navigation menu"
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        onClick={() => (open ? close() : openDrawer())}
        className="machine flex items-center gap-2 rounded border border-line px-3 py-1.5 text-ink md:hidden"
      >
        <span aria-hidden="true" className="flex h-[10px] w-[14px] flex-col justify-between">
          <span className="h-[2px] w-full bg-current" />
          <span className="h-[2px] w-full bg-current" />
        </span>
        Menu
      </button>

      <div
        className={`mobile-nav-overlay${open ? ' is-active' : ''}`}
        aria-hidden="true"
        onClick={close}
      />
      <aside
        id="mobile-nav-drawer"
        ref={drawerRef}
        role="dialog"
        aria-label="Mobile navigation"
        aria-hidden={!open}
        className={`mobile-nav-drawer${open ? ' is-active' : ''}`}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="machine flex items-center gap-2 uppercase text-mute">
            <span aria-hidden="true" className="inline-block h-1.5 w-1.5 rounded-full bg-accent" />
            Navigation
          </div>
          <button
            type="button"
            data-qid="drawer:action:close"
            data-qs-action="DRAWER_CLOSE"
            title="Close navigation menu"
            onClick={close}
            className="rounded px-2 text-2xl leading-none text-mute hover:text-ink"
          >
            ×
          </button>
        </div>
        <nav className="grow overflow-y-auto p-5">
          <ul className="flex flex-col gap-2">
            {LINKS.map((l) => (
              <li key={l.id}>
                <a
                  href={`#${l.id}`}
                  data-qid={`drawer:link:${l.id}`}
                  data-qs-action={`NAV_GOTO_${l.id.toUpperCase()}`}
                  title={`Go to ${l.label}`}
                  onClick={close}
                  className="machine block rounded border border-transparent px-3 py-2.5 text-[0.9rem] text-mute hover:bg-fill hover:text-ink"
                >
                  {l.label}
                </a>
              </li>
            ))}
            <li>
              <a
                href="https://github.com/grahama1970/agent-skills/blob/main/RESUME.md"
                data-qid="drawer:link:resume"
                data-qs-action="NAV_OPEN_RESUME"
                title="Open RESUME.md on GitHub"
                className="machine block rounded border border-transparent px-3 py-2.5 text-[0.9rem] text-mute hover:bg-fill hover:text-ink"
              >
                Résumé
              </a>
            </li>
          </ul>
        </nav>
        <div className="border-t border-line p-5">
          <div className="machine mb-3 flex items-center justify-between border-b border-line pb-3 text-mute">
            <span id="mobile-theme-label">Appearance</span>
            <button
              type="button"
              role="switch"
              data-qid="drawer:action:theme"
              data-qs-action="DRAWER_TOGGLE_THEME"
              title="Toggle light / dark theme"
              aria-checked={
                typeof document !== 'undefined' &&
                document.documentElement.dataset.theme === 'dark'
              }
              aria-labelledby="mobile-theme-label"
              onClick={toggleTheme}
              className="theme-toggle-btn"
            >
              <span aria-hidden="true" className="theme-icon">☀</span>
              <span aria-hidden="true" className="theme-icon">☾</span>
              <span className="theme-slider" />
            </button>
          </div>
          <a
            href="mailto:graham@grahama.co"
            data-qid="drawer:action:email"
            data-qs-action="DRAWER_COPY_EMAIL"
            title="Copy graham@grahama.co to clipboard"
            onClick={copyEmail}
            className="machine flex items-center justify-between rounded border border-line px-3.5 py-2.5 text-ink no-underline hover:border-mute"
          >
            <span>graham@grahama.co</span>
            <span className="text-mute">Copy ↗</span>
          </a>
        </div>
      </aside>
    </>
  );
}
