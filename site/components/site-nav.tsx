const LINKS = [
  { id: 'work', label: 'Work' },
  { id: 'index', label: 'Skill index' },
  { id: 'contact', label: 'Contact' },
];

export function SiteNav() {
  return (
    <header className="border-b border-line">
      <nav className="mx-auto flex max-w-[1080px] flex-wrap items-baseline gap-x-7 gap-y-1 px-6 py-5">
        <a
          href="#top"
          data-qid="nav:link:home"
          data-qs-action="NAV_GOTO_TOP"
          title="Back to top"
          className="mr-auto font-display text-xl no-underline"
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
            className="text-[15px] text-mute no-underline hover:text-ink"
          >
            {l.label}
          </a>
        ))}
        <a
          href="https://github.com/grahama1970/agent-skills/blob/main/RESUME.md"
          data-qid="nav:link:resume"
          data-qs-action="NAV_OPEN_RESUME"
          title="Open RESUME.md on GitHub"
          className="text-[15px] text-mute no-underline hover:text-ink"
        >
          Résumé
        </a>
        <a
          href="mailto:graham@grahama.co"
          data-qid="nav:link:email"
          data-qs-action="NAV_EMAIL"
          title="Email graham@grahama.co"
          className="text-[15px] text-accent no-underline underline-offset-4 hover:underline"
        >
          Email
        </a>
      </nav>
    </header>
  );
}
