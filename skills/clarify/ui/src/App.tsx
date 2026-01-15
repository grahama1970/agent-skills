import { useEffect, useMemo, useState } from 'react'
import { FormProvider, useForm } from 'react-hook-form'
import { fetchSession, submitResponses } from './lib/api'
import type { ClarifyQuestion, ClarifySessionPayload } from './types'
import QuestionCard from './components/QuestionCard'
import './App.css'

const buildDefaults = (questions: ClarifyQuestion[]) => {
  return questions.reduce<Record<string, any>>((acc, question) => {
    if (question.kind === 'multi-choice') {
      acc[question.id] = { selected: [], note: '' }
    } else if (question.kind === 'single-choice') {
      acc[question.id] = { selected: '', note: '' }
    } else {
      acc[question.id] = { value: '', note: '' }
    }
    return acc
  }, {})
}

function App() {
  const [session, setSession] = useState<ClarifySessionPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    fetchSession()
      .then((payload) => {
        if (active) {
          setSession(payload)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message)
          setLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [])

  const formDefaults = useMemo(() => buildDefaults(session?.questions ?? []), [session])
  const methods = useForm<Record<string, any>>({ defaultValues: formDefaults })

  useEffect(() => {
    methods.reset(formDefaults)
  }, [formDefaults, methods])

  const onSubmit = methods.handleSubmit(async (values) => {
    if (!session) return
    setSubmitError(null)
    try {
      const responses = session.questions.map((question) => {
        const entry = values[question.id] ?? {}
        const payload: any = {
          id: question.id,
          kind: question.kind,
        }
        if (question.kind === 'single-choice') {
          if (entry.selected) {
            payload.selectedOptions = [entry.selected]
          }
        } else if (question.kind === 'multi-choice') {
          payload.selectedOptions = Array.isArray(entry.selected) ? entry.selected : []
        } else {
          payload.value = entry.value ?? ''
        }
        if (entry.note) {
          payload.note = entry.note
        }
        return payload
      })
      await submitResponses({
        responses,
        submittedAt: new Date().toISOString(),
      })
      setSubmitted(true)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to submit responses')
    }
  })

  if (loading) {
    return <div className="app-shell"><p>Loading clarifications...</p></div>
  }

  if (error) {
    return (
      <div className="app-shell">
        <p className="error">{error}</p>
      </div>
    )
  }

  if (!session) {
    return null
  }

  if (submitted) {
    return (
      <div className="app-shell">
        <h1>Responses captured</h1>
        <p>You can close this tab. The contract loop will continue automatically.</p>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Step {session.step}</p>
          <h1>Clarify attempt {session.attempt}</h1>
          <p className="subtitle">Answer the questions below to unblock the contract loop.</p>
        </div>
      </header>
      <FormProvider {...methods}>
        <form className="clarify-form" onSubmit={onSubmit}>
          {session.questions.map((question) => (
            <QuestionCard key={question.id} question={question} control={methods.control} disabled={methods.formState.isSubmitting} />
          ))}
          {submitError && <p className="error">{submitError}</p>}
          <div className="actions">
            <button type="submit" disabled={methods.formState.isSubmitting}>
              {methods.formState.isSubmitting ? 'Submitting…' : 'Submit responses'}
            </button>
          </div>
        </form>
      </FormProvider>
    </div>
  )
}

export default App
