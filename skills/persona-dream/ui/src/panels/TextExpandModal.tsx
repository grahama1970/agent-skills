/**
 * TextExpandModal, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { X } from 'lucide-react'

export function TextExpandModal({ text, onClose }: { text: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  return createPortal(
    <div onClick={onClose} role="dialog" aria-modal="true" aria-label="Full memory text" style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.58)', backdropFilter: 'blur(5px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'zoom-out', padding: 24,
    }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        onClick={(e: any) => e.stopPropagation()}
        style={{
          width: 'min(640px, calc(100vw - 48px))',
          maxHeight: '80vh', overflow: 'auto',
          background: '#0c0c0c', borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.1)',
          padding: 28, cursor: 'default',
        }}
      >
        <button type="button" onClick={onClose} style={{
          float: 'right', width: 28, height: 28,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: 'none', background: 'transparent', color: '#64748b',
          cursor: 'pointer', borderRadius: 6,
        }}>
          <X size={16} />
        </button>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>{text}</p>
      </motion.div>
    </div>,
    document.body
  )
}
