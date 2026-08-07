/**
 * MediaModal, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { nvis } from '../styles'
import { X } from 'lucide-react'

export function MediaModal({ url, mediaType, onClose }: { url: string; mediaType?: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  const isVideo = ['mp4','mov','avi','webm'].includes(mediaType || '')
  const isAudio = ['wav','mp3','ogg'].includes(mediaType || '')
  return createPortal(
    <div
      onClick={onClose}
      data-qid="dream:memory:media-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Memory media preview"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.58)', backdropFilter: 'blur(5px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'zoom-out', padding: 24,
      }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        onClick={(e: any) => e.stopPropagation()}
        style={nvis.memoryInspectorModal}
      >
        <button
          type="button"
          data-qid="dream:memory:media-modal-close"
          data-qs-action="DREAM_MEMORY_CLOSE_MEDIA"
          title="Close memory media preview"
          aria-label="Close memory media preview"
          onClick={onClose}
          style={nvis.modalCloseBtn}
        >
          <X size={17} />
        </button>
        {isVideo ? (
          <video src={url} controls autoPlay style={nvis.memoryInspectorMedia} />
        ) : isAudio ? (
          <div style={nvis.memoryInspectorAudio}>
            <audio src={url} controls autoPlay style={{ width: '100%' }} />
          </div>
        ) : (
          <img src={url} alt="" style={nvis.memoryInspectorMedia} />
        )}
      </motion.div>
    </div>,
    document.body
  )
}
