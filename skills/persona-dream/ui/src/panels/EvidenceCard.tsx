/**
 * EvidenceCard, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { nvis } from '../styles'
import { StatusBadge } from './StatusBadge'

export function EvidenceCard({ title, status, children }: { title: string; status: string; children: React.ReactNode }) {
  const tone = statusTone(status)
  const borderColor = tone === 'pass' ? '#00ff88' : tone === 'blocked' ? '#ff4444' : 'rgba(255,255,255,0.13)'
  return (
    <div style={{ ...nvis.evidenceCard, borderColor }}>
      <div style={nvis.evidenceCardHeader}>
        <span style={nvis.evidenceCardTitle}>{title}</span>
        <StatusBadge status={status} />
      </div>
      {children}
    </div>
  )
}
