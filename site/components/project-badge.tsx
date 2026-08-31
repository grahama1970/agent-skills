import { CheckCircle2, FileText, ExternalLink, Lock } from 'lucide-react';

export type BadgeType = 'check-script' | 'contract-only' | 'external-repo' | 'private-evidence';

const BADGE_MAP: Record<
  BadgeType,
  { label: string; Icon: typeof CheckCircle2; className: string; title?: string }
> = {
  'check-script': {
    label: 'check script present',
    Icon: CheckCircle2,
    className: 'chip',
    title: 'A tracked sanity.sh exists in the public source. This badge alone does not prove the latest deployment executed it.',
  },
  'contract-only': { label: 'contract only', Icon: FileText, className: 'chip' },
  'external-repo': { label: 'external repo', Icon: ExternalLink, className: 'chip ext' },
  'private-evidence': {
    label: 'private evidence',
    Icon: Lock,
    className: 'evidence-private',
    title: 'Public product overview; the underlying system and its evidence are private.',
  },
};

export function ProjectBadge({ type }: { type: BadgeType }) {
  const config = BADGE_MAP[type];
  if (!config) return null;
  const { Icon } = config;
  return (
    <span
      className={config.className}
      title={config.title}
      aria-label={config.title ? `${config.label}: ${config.title}` : undefined}
    >
      <Icon className="badge-icon" size={12} strokeWidth={2.2} aria-hidden="true" />
      {config.label}
    </span>
  );
}
