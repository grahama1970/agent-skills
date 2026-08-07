/**
 * GraphModal, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'

export function GraphModal({ signals, sourceKind, label, onClose }: {
  signals: MemoryConnectionSignal[]
  sourceKind: string
  label: string
  onClose: () => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!containerRef.current || signals.length === 0) return
    const w = containerRef.current.clientWidth || 600
    const h = containerRef.current.clientHeight || 400
    const nodes = [
      { id: 'source', label: sourceKind, group: 1 },
      ...signals.map((s, i) => ({ id: s.id, label: s.tomKind, group: 2, color: s.color })),
      { id: 'target', label: 'Story', group: 3 },
    ]
    const links = [
      ...signals.map((s) => ({ source: 'source', target: s.id })),
      ...signals.map((s) => ({ source: s.id, target: 'target' })),
    ]
    const svg = d3.select(containerRef.current).append('svg').attr('width', w).attr('height', h)
    const g = svg.append('g')
    const zoom = d3.zoom().on('zoom', (event: any) => g.attr('transform', event.transform))
    svg.call(zoom)
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(w / 2, h / 2))
    const link = g.append('g').selectAll('line').data(links).join('line')
      .attr('stroke', 'rgba(255,255,255,0.15)').attr('stroke-width', 1.5)
    const node = g.append('g').selectAll('circle').data(nodes).join('circle')
      .attr('r', 20).attr('fill', (d: any) => d.color || '#4a9eff').attr('stroke', 'rgba(255,255,255,0.2)').attr('stroke-width', 1)
      .call(d3.drag()
        .on('start', (event: any, d: any) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event: any, d: any) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event: any, d: any) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
      )
    const label_g = g.append('g').selectAll('text').data(nodes).join('text')
      .text((d: any) => d.label).attr('text-anchor', 'middle').attr('dy', 35)
      .attr('fill', '#9ca3af').attr('font-size', 10)
    simulation.on('tick', () => {
      link.attr('x1', (d: any) => d.source.x).attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x).attr('y2', (d: any) => d.target.y)
      node.attr('cx', (d: any) => d.x).attr('cy', (d: any) => d.y)
      label_g.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y)
    })
    return () => { svg.remove() }
  }, [signals, sourceKind])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: '80vw', height: '80vh', cursor: 'default' }}>
        <div style={{ color: '#64748b', fontSize: 10, textAlign: 'center', marginBottom: 8, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Semantic connections &mdash; {label.slice(0, 60)}
        </div>
        <div ref={containerRef} style={{ width: '100%', height: '100%', borderRadius: 12, overflow: 'hidden', background: 'rgba(0,0,0,0.3)' }} />
      </div>
    </div>
  )
}
