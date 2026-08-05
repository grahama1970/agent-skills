'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRegisterAction } from '@/lib/use-register-action';

interface Entry {
  slug: string;
  label: string;
  hint: string;
  href: string;
}

const GH = 'https://github.com/grahama1970/agent-skills';

const INDEX: Entry[] = [
  { slug: 'section-build', label: 'what we build', hint: 'capabilities', href: '#build' },
  { slug: 'section-receipts', label: 'receipts — why trust it', hint: 'verification discipline', href: '#receipts' },
  { slug: 'section-projects', label: 'live experiments', hint: 'ten running systems', href: '#projects' },
  { slug: 'section-contact', label: 'contact', hint: 'engagements & roles', href: '#contact' },
  { slug: 'repo', label: 'agent-skills repository', hint: '330 skills, public code', href: GH },
  { slug: 'resume', label: 'resume', hint: 'RESUME.md — working evidence', href: `${GH}/blob/main/RESUME.md` },
  { slug: 'tau', label: "t'au — agent harness", hint: 'DAG contracts, verdicts, receipts', href: `${GH}/blob/main/skills/tau/README.md` },
  { slug: 'battle', label: 'battle — fuzzing arena', hint: 'red/blue genetic fuzzing', href: `${GH}/blob/main/skills/battle/README.md` },
  { slug: 'surf', label: 'surf — browser control', hint: 'authenticated Chrome for agents', href: `${GH}/blob/main/skills/surf/README.md` },
  { slug: 'persona-dream', label: 'persona-dream — memories to movies', hint: 'receipt-backed dream packets', href: `${GH}/blob/main/skills/persona-dream/README.md` },
  { slug: 'extractor', label: 'extractor — evidence trees', hint: 'documents to hierarchy', href: `${GH}/blob/main/skills/extractor/README.md` },
  { slug: 'dogpile', label: 'dogpile — deep research', hint: 'arXiv, GitHub, YouTube, web', href: `${GH}/blob/main/skills/dogpile/README.md` },
  { slug: 'watch', label: 'watch — video understanding', hint: 'frame-by-frame for agents', href: `${GH}/blob/main/skills/watch/README.md` },
  { slug: 'scillm', label: 'scillm — model orchestration', hint: 'one-shot, exec, subagent, DAG', href: `${GH}/blob/main/skills/scillm/README.md` },
  { slug: 'debugger', label: 'debugger — live state for agents', hint: 'observe before patching', href: `${GH}/blob/main/skills/debugger/README.md` },
  { slug: 'sparta', label: 'sparta explorer — space-cyber workbench', hint: 'evidence to human review', href: 'https://github.com/grahama1970/sparta-public' },
  { slug: 'email', label: 'email graham', hint: 'graham@grahama.co', href: 'mailto:graham@grahama.co' },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useRegisterAction('palette:action:open', {
    app: 'grahama-labs-site',
    action: 'PALETTE_OPEN',
    label: 'Ask the archive',
    description: 'Open the command palette to search projects and sections',
  });

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return INDEX;
    return INDEX.filter((e) =>
      `${e.label} ${e.hint}`.toLowerCase().includes(q),
    );
  }, [query]);

  const openPalette = useCallback(() => {
    setOpen(true);
    setQuery('');
    setActive(0);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openPalette();
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [openPalette]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const go = (entry: Entry) => {
    setOpen(false);
    if (entry.href.startsWith('#')) {
      document.querySelector(entry.href)?.scrollIntoView({ block: 'start' });
    } else {
      window.location.href = entry.href;
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={openPalette}
        data-qid="palette:action:open"
        data-qs-action="PALETTE_OPEN"
        title="Ask the archive — search projects and sections (Ctrl+K)"
        className="mt-6 inline-flex items-center gap-2 rounded border border-line bg-panel px-4 py-2 font-mono text-[13px] text-mute transition-colors hover:border-accent hover:text-ink"
      >
        <span className="text-accent">›</span> ask the archive
        <kbd className="ml-2 rounded border border-line px-1.5 py-0.5 text-[11px]">ctrl K</kbd>
      </button>

      {open && (
        <div
          className="palette-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Ask the archive"
            className="palette-panel mx-auto mt-[12vh] w-[min(640px,92vw)] overflow-hidden rounded-md border border-line bg-panel shadow-2xl"
          >
            <div className="flex items-center gap-2 border-b border-line px-4">
              <span className="font-mono text-accent">›</span>
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActive(0);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setActive((a) => Math.min(a + 1, results.length - 1));
                  }
                  if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setActive((a) => Math.max(a - 1, 0));
                  }
                  if (e.key === 'Enter' && results[active]) go(results[active]);
                }}
                data-qid="palette:input:query"
                data-qs-action="PALETTE_QUERY"
                title="Search the archive"
                placeholder="search projects, receipts, contact…"
                className="w-full bg-transparent py-3.5 font-mono text-[14px] text-ink outline-none placeholder:text-mute"
              />
              <kbd className="rounded border border-line px-1.5 py-0.5 font-mono text-[11px] text-mute">esc</kbd>
            </div>
            <ul className="max-h-[46vh] overflow-y-auto py-1.5" role="listbox">
              {results.length === 0 && (
                <li className="px-4 py-3 font-mono text-[13px] text-mute">
                  no matches — try “tau”, “receipts”, or “email”
                </li>
              )}
              {results.map((r, i) => (
                <li key={r.slug} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    data-qid={`palette:result:${r.slug}`}
                    data-qs-action={`PALETTE_GO_${r.slug.toUpperCase().replace(/-/g, '_')}`}
                    title={`Go to ${r.label}`}
                    onClick={() => go(r)}
                    onMouseEnter={() => setActive(i)}
                    className={`flex w-full items-baseline justify-between gap-4 px-4 py-2 text-left font-mono text-[13.5px] ${
                      i === active ? 'bg-ground text-accent' : 'text-ink'
                    }`}
                  >
                    <span>{r.label}</span>
                    <span className="shrink-0 text-[12px] text-mute">{r.hint}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
