'use client';

import { useEffect, useState } from 'react';
import { ThemeToggle } from '@/components/theme-toggle';

const LINKS = [
  { id: 'work', label: 'Work' },
  { id: 'dream', label: 'Dream' },
  { id: 'index', label: 'Skill index' },
  { id: 'about', label: 'About' },
  { id: 'contact', label: 'Contact' },
];

export function SiteNav() {
  const [active, setActive] = useState('');

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: '-20% 0px -70% 0px', threshold: 0 },
    );
    document
      .querySelectorAll('section[id]')
      .forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []);

  return (
    <header className="glass-nav relative border-b border-line">
      <div className="scroll-gauge" aria-hidden="true" />
      <nav className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-1 gap-y-1 px-6 py-3 md:px-10">
        <a
          href="#top"
          data-qid="nav:link:home"
          data-qs-action="NAV_GOTO_TOP"
          title="Back to top"
          className="mr-auto font-display text-xl text-ink no-underline"
        >
          grahama.co
        </a>
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
          data-qs-action="NAV_EMAIL"
          title="Email graham@grahama.co"
          className="nav-link text-accent"
        >
          Email
        </a>
        <ThemeToggle />
      </nav>
    </header>
  );
}
