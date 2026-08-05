'use client';

import { useEffect, useRef, useState } from 'react';
import { MobileNav } from '@/components/mobile-nav';
import { ThemeToggle } from '@/components/theme-toggle';
import { announce } from '@/lib/announce';

const LINKS = [
  { id: 'work', label: 'Work' },
  { id: 'dream', label: 'Dream' },
  { id: 'index', label: 'Skill index' },
  { id: 'about', label: 'About' },
  { id: 'contact', label: 'Contact' },
];

export function SiteNav() {
  const [active, setActive] = useState('');
  const [shrunk, setShrunk] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const spy = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 },
    );
    document.querySelectorAll('section[id]').forEach((s) => spy.observe(s));

    // Zero-delay shrink: sentinel exits the viewport top past 24px of scroll.
    const sentinel = sentinelRef.current;
    const shrink = new IntersectionObserver(
      ([entry]) => setShrunk(!entry.isIntersecting),
      { threshold: 0 },
    );
    if (sentinel) shrink.observe(sentinel);

    return () => {
      spy.disconnect();
      shrink.disconnect();
    };
  }, []);

  const copyEmail = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    try {
      e.preventDefault();
      await navigator.clipboard.writeText('graham@grahama.co');
      announce('Copied email graham@grahama.co to clipboard', 'assertive');
    } catch {
      window.location.href = 'mailto:graham@grahama.co';
    }
  };

  return (
    <>
      <div
        ref={sentinelRef}
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 24,
          left: 0,
          width: '100%',
          height: 1,
          pointerEvents: 'none',
          visibility: 'hidden',
        }}
      />
      <header className={`glass-nav relative border-b border-line${shrunk ? ' is-shrunk' : ''}`}>
        <div className="scroll-gauge" aria-hidden="true" />
        <nav
          aria-label="Main navigation"
          className="nav-inner mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-1 gap-y-1 px-6 md:px-10"
        >
          <a
            href="#top"
            data-qid="nav:link:home"
            data-qs-action="NAV_GOTO_TOP"
            title="Back to top"
            className="mr-auto inline-flex items-baseline gap-2 font-display text-xl text-ink no-underline"
          >
            <span aria-hidden="true" className="text-accent">◈</span>
            grahama.co
          </a>
          <div className="hidden items-center gap-1 md:flex">
            {LINKS.map((l) => (
              <a
                key={l.id}
                href={`#${l.id}`}
                data-qid={`nav:link:${l.id}`}
                data-qs-action={`NAV_GOTO_${l.id.toUpperCase()}`}
                title={`Go to ${l.label}`}
                aria-current={active === l.id ? 'page' : undefined}
                className={`nav-link${active === l.id ? ' is-active' : ''}`}
              >
                {l.label}
              </a>
            ))}
            <a
              href="https://github.com/grahama1970/agent-skills/blob/main/RESUME.md"
              data-qid="nav:link:resume"
              data-qs-action="NAV_OPEN_RESUME"
              title="Open RESUME.md on GitHub"
              className="nav-link"
            >
              Résumé
            </a>
            <a
              href="mailto:graham@grahama.co"
              data-qid="nav:link:email"
              data-qs-action="NAV_COPY_EMAIL"
              title="Copy graham@grahama.co to clipboard"
              onClick={copyEmail}
              className="nav-link border-line bg-fill text-ink"
            >
              graham@grahama.co
            </a>
            <ThemeToggle />
          </div>
          <MobileNav active={active} />
        </nav>
      </header>
    </>
  );
}
