'use client';

import { useEffect } from 'react';

const HIGHLIGHT_CLASS = 'target-highlight';
const HIGHLIGHT_MS = 2500;

function targetFromHash(hash: string): HTMLElement | null {
  if (!hash || hash === '#') return null;
  try {
    return document.getElementById(decodeURIComponent(hash.slice(1)));
  } catch {
    return document.getElementById(hash.slice(1));
  }
}

function replayHighlight(target: HTMLElement | null) {
  if (!target) return;
  target.classList.remove(HIGHLIGHT_CLASS);
  void target.offsetWidth;
  target.classList.add(HIGHLIGHT_CLASS);
  window.setTimeout(() => {
    target.classList.remove(HIGHLIGHT_CLASS);
  }, HIGHLIGHT_MS);
}

export function ProjectTargetHighlighter() {
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented) return;
      const link = (event.target as Element | null)?.closest<HTMLAnchorElement>('a[href^="#"]');
      const hash = link?.getAttribute('href');
      if (!hash || hash === '#') return;
      window.requestAnimationFrame(() => replayHighlight(targetFromHash(hash)));
    };
    const onHashChange = () => replayHighlight(targetFromHash(window.location.hash));

    document.addEventListener('click', onClick);
    window.addEventListener('hashchange', onHashChange);
    onHashChange();
    return () => {
      document.removeEventListener('click', onClick);
      window.removeEventListener('hashchange', onHashChange);
    };
  }, []);

  return null;
}
