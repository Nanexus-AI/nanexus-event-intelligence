export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''

export type EventSummary = {
  id: string
  occurred_at: string
  event_kind: string
  lifecycle: string
  labels: string[]
  zones: string[]
  partial_history: boolean
  source_name: string
  camera_name: string | null
  feedback_verdict: string | null
  first_occurred_at: string
  last_occurred_at: string
  observation_count: number
}

export type EventList = { items: EventSummary[]; total: number; limit: number; offset: number }

export type EventDetail = EventSummary & {
  source_instance_id: string
  source_type: string
  source_version: string | null
  camera_id: string | null
  source_namespace: string
  source_entity_id: string
  source_revision: string
  dedupe_key: string
  schema_version: string
  observed_at: string
  processed_at: string | null
  start_at: string | null
  end_at: string | null
  extensions: Record<string, unknown>
  raw_message: null | { channel: string; schema_version: string; payload: Record<string, unknown>; quarantined: boolean; quarantine_reason: string | null }
  objects: Array<{ id: string; object_key: string; label: string; confidence: number | null; stationary: boolean | null }>
  evidence: Array<{ id: string; media_type: string; source_ref: string; privacy_class: string; availability: string }>
  decisions: Array<{ id: string; outcome: string; policy_id: string; policy_version: string; revision: number; reasons: string[]; rule_trace: { matched_rule_id?: string | null; trace?: Array<{ rule_id: string; matched: boolean; explanation: string }> } }>
  notifications: Array<{ id: string; decision_id: string; channel: string; stage: string; delivery_status: string; external_message_id: string | null; attempts: number; last_error: string | null; created_at: string }>
  feedback: null | { verdict: string; reason: string | null; created_at: string }
  timeline: Array<{ id: string; lifecycle: string; occurred_at: string; labels: string[]; zones: string[]; partial_history: boolean; source_namespace: string; source_entity_id: string }>
  related_entity_ids: string[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export const eventSnapshotUrl = (id: string) => apiBaseUrl + "/api/v1/events/" + id + "/media/snapshot"

export const loadEvents = (query = '') => request<EventList>(`/api/v1/events${query}`)
export const loadEvent = (id: string) => request<EventDetail>(`/api/v1/events/${id}`)
export const saveFeedback = (id: string, verdict: string) =>
  request(`/api/v1/events/${id}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verdict }),
  })
