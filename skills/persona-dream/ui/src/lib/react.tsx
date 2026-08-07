/**
 * react helpers for the Dream workspace.
 *
 * One of the modules `lib.tsx` was split into; it had reached 7,560 lines,
 * which is past the point where a reader can hold it in their head.
 */
import React, { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { nvis } from '../styles'
import { AlertTriangle } from 'lucide-react'

type PipelineErrorBoundaryProps = { surface?: string; children?: React.ReactNode }

type PipelineErrorBoundaryState = { hasError: boolean; error: unknown }

/**
 * Typed explicitly. It previously extended React.Component with no type
 * parameters, so this.props was Readonly<{}> and this.state.error narrowed to
 * never -- the `surface` prop it is actually passed was invisible to the
 * compiler, and the instanceof check below could not be verified.
 */

export class PipelineErrorBoundary extends React.Component<
  PipelineErrorBoundaryProps,
  PipelineErrorBoundaryState
> {
  state: PipelineErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      const message = this.state.error instanceof Error ? this.state.error.message : String(this.state.error ?? 'Unknown component fault')
      return (
        <div style={nvis.pipelineErrorBoundary}>
          <div style={nvis.pipelineErrorTitle}>
            <AlertTriangle size={18} />
            <span>{String(this.props.surface ?? 'Pipeline')} system fault detected</span>
          </div>
          <p style={nvis.pipelineErrorMessage}>{message}</p>
          <button
            type="button"
            data-qid="dream:pipeline-error-boundary:reboot"
            data-qs-action="DREAM_PIPELINE_ERROR_BOUNDARY_REBOOT"
            style={nvis.pipelineErrorButton}
            title="Reboot this pipeline component"
            onClick={() => this.setState({ hasError: false, error: null })}
          >
            Reboot component
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null)
  const [size, setSize] = useState({ width: 960, height: 620 })

  useEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(520, entry.contentRect.width)
      const height = Math.max(460, entry.contentRect.height)
      setSize({ width, height })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return [ref, size] as const
}

export function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

export { styles } from '../styles/base'
