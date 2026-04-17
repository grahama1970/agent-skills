// TaxonomyChip — pill-shaped badge with heart/mind prefix icon

// Taxonomy color palette
const HEART = {
  bg: 'rgba(139,92,246,0.15)',
  text: '#a78bfa', // lightened from #8b5cf6 for WCAG AA contrast on dark bg
  border: 'rgba(139,92,246,0.3)',
  icon: '\u2665', // heart
} as const

const MIND = {
  bg: 'rgba(74,158,255,0.10)',
  text: '#7ab8ff', // lightened from #4a9eff for WCAG AA contrast on tinted bg
  border: 'rgba(74,158,255,0.25)',
  icon: '\u25C6', // diamond
} as const

function palette(tag: string) {
  return tag.startsWith('heart:') ? HEART : MIND
}

/** Single taxonomy chip — pill-shaped badge with heart/mind prefix icon. */
export function TaxonomyChip({ tag }: { tag: string }) {
  const p = palette(tag)
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        fontSize: 10,
        fontWeight: 500,
        lineHeight: '16px',
        paddingLeft: 8,
        paddingRight: 8,
        paddingTop: 2,
        paddingBottom: 2,
        borderRadius: 9999,
        color: p.text,
        backgroundColor: p.bg,
        border: `1px solid ${p.border}`,
        whiteSpace: 'nowrap' as const,
      }}
    >
      <span style={{ fontSize: 9 }}>{p.icon}</span>
      {tag}
    </span>
  )
}

/** Flex-wrap list of taxonomy chips. */
export function TaxonomyChipList({ tags }: { tags: string[] }) {
  if (!tags || tags.length === 0) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {tags.map((tag) => (
        <TaxonomyChip key={tag} tag={tag} />
      ))}
    </div>
  )
}
