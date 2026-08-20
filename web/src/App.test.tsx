import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import App from './App'

const summary = { id: 'event-1', occurred_at: '2026-08-17T12:00:00Z', event_kind: 'review', lifecycle: 'started', labels: ['person'], zones: ['porch'], partial_history: false, source_name: 'pilot', camera_name: '前门', feedback_verdict: null, first_occurred_at: '2026-08-17T12:00:00Z', last_occurred_at: '2026-08-17T12:00:27Z', observation_count: 3 }
const detail = { ...summary, source_instance_id: 'source-1', source_type: 'frigate', source_version: '0.17.1', camera_id: 'camera-1', source_namespace: 'review', source_entity_id: 'review-1', source_revision: '1', dedupe_key: 'key', schema_version: '1.0', observed_at: '2026-08-17T12:00:00Z', processed_at: null, start_at: null, end_at: null, extensions: {}, raw_message: { channel: 'frigate/reviews', schema_version: 'frigate-0.17', payload: { type: 'new' }, quarantined: false, quarantine_reason: null }, objects: [{ id: 'object-1', object_key: 'person-1', label: 'person', confidence: 0.92, stationary: false }], evidence: [{ id: 'evidence-1', media_type: 'snapshot', source_ref: 'local', privacy_class: 'local_only', availability: 'available' }], decisions: [{ id: 'decision-1', outcome: 'escalate', policy_id: 'community.basic-alerts', policy_version: '1.0.0', revision: 1, reasons: ['人员进入入口或周界区域，影子升级'], rule_trace: { matched_rule_id: 'person.priority-zone', trace: [{ rule_id: 'person.priority-zone', matched: true, explanation: 'matched' }] } }], notifications: [{ id: "notification-1", decision_id: "decision-1", channel: "community_webhook", stage: "escalated", delivery_status: "succeeded", external_message_id: "external-1", attempts: 1, last_error: null, created_at: "2026-08-17T12:00:01Z" }], feedback: null, timeline: [{ id: 'event-start', lifecycle: 'started', occurred_at: '2026-08-17T12:00:00Z', labels: ['person'], zones: [], partial_history: false, source_namespace: 'frigate.event', source_entity_id: 'person-1' }, { id: 'event-update', lifecycle: 'updated', occurred_at: '2026-08-17T12:00:10Z', labels: ['person'], zones: ['porch'], partial_history: false, source_namespace: 'frigate.event', source_entity_id: 'person-1' }, { id: 'event-1', lifecycle: 'ended', occurred_at: '2026-08-17T12:00:27Z', labels: ['person'], zones: ['porch'], partial_history: false, source_namespace: 'frigate.event', source_entity_id: 'person-1' }], related_entity_ids: ['person-1'] }

beforeEach(() => {
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:snapshot') })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
})

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

function mockApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/health')) return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    if (init?.method === 'POST') return new Response(JSON.stringify({ verdict: 'important' }), { status: 201 })
    if (url.endsWith('/media/snapshot')) return new Response(new Blob(['jpeg'], { type: 'image/jpeg' }), { status: 200 })
    if (url.endsWith('/events/event-1')) return new Response(JSON.stringify(detail), { status: 200 })
    if (url.includes('/events')) return new Response(JSON.stringify({ items: [summary], total: 1, limit: 30, offset: 0 }), { status: 200 })
    return new Response(null, { status: 404 })
  })
}

test('shows event list, canonical detail and evidence', async () => {
  mockApi()
  render(<App />)
  expect((await screen.findAllByText('前门')).length).toBeGreaterThan(0)
  expect(await screen.findByText('对象 1')).toBeInTheDocument()
  expect(screen.getByText(/snapshot · available/)).toBeInTheDocument()
  expect(screen.getByText('后端在线')).toBeInTheDocument()
  expect(screen.getAllByText(/27 秒/).length).toBeGreaterThan(0)
  expect(screen.getByText('进入区域：porch')).toBeInTheDocument()
  expect(screen.getByText('目标 person-1 出现')).toBeInTheDocument()
  expect(screen.getByText('目标 person-1 消失')).toBeInTheDocument()
  expect(screen.getByText('person-1')).toBeInTheDocument()
  expect(screen.getByText(/3 次状态/)).toBeInTheDocument()
  expect(screen.getByText(/建议升级提醒/)).toBeInTheDocument()
  expect(screen.getByText('规则建议 · 影子评估')).toBeInTheDocument()
  expect(screen.getByText('本事件已有实际通知记录，详情见下方')).toBeInTheDocument()
  expect(screen.getByText('实际通知记录')).toBeInTheDocument()
  expect(await screen.findByRole('img', { name: '事件现场快照' })).toHaveAttribute('src', 'blob:snapshot')
  expect(screen.getAllByText(/person.priority-zone/).length).toBeGreaterThan(0)
})

test('explains a missing snapshot and retries it', async () => {
  let snapshotAttempts = 0
  const fetchMock = mockApi()
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/health')) return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    if (url.endsWith('/media/snapshot')) {
      snapshotAttempts += 1
      if (snapshotAttempts === 1) return new Response(JSON.stringify({ detail: 'snapshot is not associated' }), { status: 404, headers: { 'Content-Type': 'application/json' } })
      return new Response(new Blob(['jpeg'], { type: 'image/jpeg' }), { status: 200 })
    }
    if (init?.method === 'POST') return new Response(JSON.stringify({ verdict: 'important' }), { status: 201 })
    if (url.endsWith('/events/event-1')) return new Response(JSON.stringify(detail), { status: 200 })
    if (url.includes('/events')) return new Response(JSON.stringify({ items: [summary], total: 1, limit: 30, offset: 0 }), { status: 200 })
    return new Response(null, { status: 404 })
  })
  render(<App />)
  expect(await screen.findByText('该事件没有快照')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重新加载快照' }))
  expect(await screen.findByRole('img', { name: '事件现场快照' })).toBeInTheDocument()
  expect(snapshotAttempts).toBe(2)
})

test('submits feedback in one click', async () => {
  const fetchMock = mockApi()
  render(<App />)
  const button = await screen.findByRole('button', { name: '重要' })
  fireEvent.click(button)
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/feedback'), expect.objectContaining({ method: 'POST' })))
})

test('automatically refreshes live events every three seconds', async () => {
  vi.useFakeTimers()
  const fetchMock = mockApi()
  render(<App />)
  await vi.advanceTimersByTimeAsync(3100)
  const listCalls = fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/api/v1/events'))
  expect(listCalls.length).toBeGreaterThanOrEqual(2)
})
