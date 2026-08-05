'use client';

export function ThemeToggle() {
  const toggle = () => {
    const root = document.documentElement;
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    const apply = () => {
      root.dataset.theme = next;
      localStorage.setItem('theme', next);
    };
    const vt = (
      document as Document & { startViewTransition?: (cb: () => void) => void }
    ).startViewTransition;
    if (vt && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
      vt.call(document, apply);
    } else {
      apply();
    }
  };
  return (
    <button
      type="button"
      data-qid="nav:action:theme"
      data-qs-action="NAV_TOGGLE_THEME"
      title="Toggle light / dark theme"
      onClick={toggle}
      className="machine border border-line px-2 py-1 text-mute hover:border-accent hover:text-ink"
    >
      ☾/☀
    </button>
  );
}
