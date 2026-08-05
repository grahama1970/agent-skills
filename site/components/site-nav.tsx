'use client';

import { useRegisterAction } from '@/lib/use-register-action';

const SECTIONS = [
  { id: 'build', label: '/ what we build', action: 'NAV_GOTO_BUILD' },
  { id: 'receipts', label: '/ receipts', action: 'NAV_GOTO_RECEIPTS' },
  { id: 'projects', label: '/ projects', action: 'NAV_GOTO_PROJECTS' },
  { id: 'contact', label: '/ contact', action: 'NAV_GOTO_CONTACT' },
];

export function SiteNav() {
  useRegisterAction('nav:link:build', {
    app: 'grahama-labs-site',
    action: 'NAV_GOTO_BUILD',
    label: 'What we build',
    description: 'Scroll to the capabilities section',
  });
  useRegisterAction('nav:link:receipts', {
    app: 'grahama-labs-site',
    action: 'NAV_GOTO_RECEIPTS',
    label: 'Receipts',
    description: 'Scroll to the verification section',
  });
  useRegisterAction('nav:link:projects', {
    app: 'grahama-labs-site',
    action: 'NAV_GOTO_PROJECTS',
    label: 'Projects',
    description: 'Scroll to the live experiments section',
  });
  useRegisterAction('nav:link:contact', {
    app: 'grahama-labs-site',
    action: 'NAV_GOTO_CONTACT',
    label: 'Contact',
    description: 'Scroll to the contact section',
  });

  return (
    <nav className="fixed inset-y-0 left-0 z-10 hidden w-[200px] flex-col gap-2 border-r border-line p-7 md:flex">
      <a
        href="#top"
        data-qid="nav:link:home"
        data-qs-action="NAV_GOTO_TOP"
        title="Back to top"
        className="mb-7 font-mono text-[15px] tracking-wider text-ink no-underline"
      >
        grahama<b className="font-semibold text-accent">.labs</b>
      </a>
      {SECTIONS.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          data-qid={`nav:link:${s.id}`}
          data-qs-action={s.action}
          title={`Go to ${s.id} section`}
          className="py-0.5 font-mono text-[12.5px] tracking-wide text-mute no-underline hover:text-accent"
        >
          {s.label}
        </a>
      ))}
      <div className="mt-auto font-mono text-[11px] text-mute">est. in the loop</div>
    </nav>
  );
}
