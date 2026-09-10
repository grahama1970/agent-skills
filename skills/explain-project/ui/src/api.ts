import type {
  BootstrapResponse,
  CockpitState,
  ServiceHealthResponse,
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

export class CockpitApiError extends Error {
  constructor(readonly status: number, body: unknown) {
    super(`cockpit API ${status}: ${JSON.stringify(body)}`)
  }
}

async function readJson<T>(
  response: Response,
): Promise<T> {
  const body = (await response.json()) as T

  if (!response.ok) {
    throw new CockpitApiError(response.status, body)
  }

  return body
}

export async function fetchBootstrap(): Promise<BootstrapResponse> {
  return readJson<BootstrapResponse>(
    await fetch(
      '/api/cockpit/bootstrap',
      { cache: 'no-store', signal: AbortSignal.timeout(5000) },
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
      signal: AbortSignal.timeout(5000),
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
      signal: AbortSignal.timeout(5000),
      body: JSON.stringify({ record }),
    },
  )

  return readJson<BootstrapResponse>(response)
}

export async function fetchServices(
  tabId?: string,
): Promise<ServiceHealthResponse> {
  const query = tabId ? `?tab_id=${encodeURIComponent(tabId)}` : ''
  const response = await fetch(
    `/api/cockpit/services${query}`,
    { cache: 'no-store', signal: AbortSignal.timeout(6000) },
  )
  if (!response.ok) {
    throw new CockpitApiError(response.status, await response.json())
  }
  return response.json() as Promise<ServiceHealthResponse>
}
