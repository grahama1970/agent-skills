export type ClarifyOption = {
  id: string
  label: string
  description?: string
}

export type ClarifyQuestion = {
  id: string
  prompt: string
  kind: 'text' | 'textarea' | 'single-choice' | 'multi-choice'
  options: ClarifyOption[]
  docs_link?: string
  artifact_paths?: string[]
  visual_assets?: string[]
  required?: boolean
  allow_multiple?: boolean
}

export type ClarifySessionPayload = {
  step: string
  attempt: number
  questions: ClarifyQuestion[]
}

type PrimitiveAnswer = string | string[] | undefined

export type FormAnswer = {
  value?: PrimitiveAnswer
  notes?: string
}

export type SubmitResponse = {
  responses: Array<{
    id: string
    kind: ClarifyQuestion['kind']
    selectedOptions?: string[]
    value?: string
    note?: string
  }>
  submittedAt: string
}
