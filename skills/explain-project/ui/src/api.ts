import type {
  BootstrapResponse,
  CockpitState,
} from './types'

export type EventType =
  | 'explainer.select'
  | 'question.manual'
  | 'question.live_evidence'
  | 'step.next'
  | 'step.previous'
  | 'source.reveal.request'
  | 'debugger.prepare.request'
  | 'adapter.receipt'

async function readJson<T>(
  response: Response,
): Promise<T> {
  const body = (await response.json()) as T

  if (!response.ok) {
    throw new Error(
      `cockpit API ${response.status}: ${JSON.stringify(body)}`,
    )
  }

  return body
}

export async function fetchBootstrap(): Promise<BootstrapResponse> {
  return readJson<BootstrapResponse>(
    await fetch(
      '/api/cockpit/bootstrap',
      { cache: 'no-store' },
    ),
  )
}

export async function postCockpitEvent(
  state: CockpitState,
  type: EventType,
  payload: Record<string, unknown> = {},
): Promise<CockpitState> {
  const response = await fetch(
    '/api/cockpit/event',
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        schema: 'explain_project.cockpit_event.v1',
        event_id: crypto.randomUUID(),
        type,
        expected_revision: state.revision,
        payload,
      }),
    },
  )

  return readJson<CockpitState>(response)
}

export async function importExplainer(
  record: unknown,
): Promise<BootstrapResponse> {
  const response = await fetch(
    '/api/cockpit/explainers',
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
      },
      body: JSON.stringify({ record }),
    },
  )

  return readJson<BootstrapResponse>(response)
}
