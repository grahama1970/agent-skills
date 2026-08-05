'use client';

import { useRegisterAction } from '@/lib/use-register-action';

export interface Project {
  slug: string;
  name: string;
  blurb: string;
  href: string;
}

export function ProjectCard({ project }: { project: Project }) {
  useRegisterAction(`projects:card:${project.slug}`, {
    app: 'grahama-labs-site',
    action: `PROJECTS_OPEN_${project.slug.toUpperCase().replace(/-/g, '_')}`,
    label: project.name,
    description: `Open the ${project.name} README on GitHub`,
  });

  return (
    <a
      href={project.href}
      data-qid={`projects:card:${project.slug}`}
      data-qs-action={`PROJECTS_OPEN_${project.slug.toUpperCase().replace(/-/g, '_')}`}
      title={`Open ${project.name} on GitHub`}
      className="block rounded-md border border-line bg-panel px-6 py-5 no-underline transition-colors hover:border-accent"
    >
      <h3 className="mb-2 font-mono text-[15px] font-semibold tracking-wide text-accent">
        {project.name}
      </h3>
      <p className="text-[15.5px] text-mute">{project.blurb}</p>
    </a>
  );
}
