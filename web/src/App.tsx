import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { EventDetail, EventSummary, apiBaseUrl, eventSnapshotUrl, loadEvent, loadEvents, saveFeedback } from './api'
import { Language, setLanguage } from './i18n'

const verdicts = ['important', 'notImportant', 'falsePositive', 'uncertain'] as const
const verdictValues = { important: 'important', notImportant: 'not_important', falsePositive: 'false_positive', uncertain: 'uncertain' } as const
const locale = (language: string) => language.startsWith('zh') ? 'zh-CN' : 'en'
const time = (value: string, language: string) => new Intl.DateTimeFormat(locale(language), { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
const clock = (value: string, language: string) => new Intl.DateTimeFormat(locale(language), { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(value))
const duration = (start: string, end: string, t: TFunction) => {
  const seconds = Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000))
  if (seconds < 60) return t('duration.seconds', { seconds })
  return t('duration.minutesSeconds', { minutes: Math.floor(seconds / 60), seconds: seconds % 60 })
}
const timelineText = (item: EventDetail['timeline'][number], index: number, items: EventDetail['timeline'], t: TFunction) => {
  if (item.lifecycle === 'started') return t('timeline.appeared', { id: item.source_entity_id })
  if (item.lifecycle === 'ended') return t('timeline.disappeared', { id: item.source_entity_id })
  const previous = items.slice(0, index).reverse().find((candidate) => candidate.source_entity_id === item.source_entity_id)
  const previousZones = new Set(previous?.zones ?? [])
  const entered = item.zones.filter((zone) => !previousZones.has(zone))
  return entered.length ? t('timeline.enteredZone', { zones: entered.join(', ') }) : t('timeline.updated')
}

type SnapshotState = { kind: 'loading' } | { kind: 'ready'; url: string } | { kind: 'error'; message: string }
function EventSnapshot({ eventId, occurredAt }: { eventId: string; occurredAt: string }) {
  const { t } = useTranslation()
  const [attempt, setAttempt] = useState(0)
  const [snapshot, setSnapshot] = useState<SnapshotState>({ kind: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    setSnapshot({ kind: 'loading' })
    void fetch(eventSnapshotUrl(eventId), { signal: controller.signal }).then(async (response) => {
      if (response.ok) {
        objectUrl = URL.createObjectURL(await response.blob())
        setSnapshot({ kind: 'ready', url: objectUrl })
        return
      }
      const body = await response.json().catch(() => null) as { detail?: string } | null
      const detail = body?.detail ?? ''
      let message = t('snapshot.unavailable')
      if (response.status === 404 && (detail === 'snapshot is not associated' || detail === 'snapshot is not supported')) message = t('snapshot.missing')
      else if (response.status === 404) {
        const age = Date.now() - new Date(occurredAt).getTime()
        message = age >= 0 && age < 60_000 ? t('snapshot.generating') : t('snapshot.expired')
      } else if (response.status === 502 || response.status === 503) message = t('snapshot.frigateUnavailable')
      setSnapshot({ kind: 'error', message })
    }).catch((reason: unknown) => {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setSnapshot({ kind: 'error', message: t('snapshot.frigateUnavailable') })
    })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [attempt, eventId, occurredAt, t])
  if (snapshot.kind === 'ready') return <img className="event-snapshot" src={snapshot.url} alt={t('snapshot.alt')} />
  return <div className="media-placeholder" role="status"><span>{snapshot.kind === 'loading' ? t('snapshot.loading') : snapshot.message}</span>{snapshot.kind === 'error' && <button type="button" onClick={() => setAttempt((value) => value + 1)}>{t('snapshot.reload')}</button>}</div>
}

export default function App() {
  const { t, i18n } = useTranslation()
  const language = locale(i18n.resolvedLanguage ?? i18n.language)
  const [online, setOnline] = useState(false)
  const [events, setEvents] = useState<EventSummary[]>([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<EventDetail | null>(null)
  const [kind, setKind] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const selectedId = useRef<string | null>(null)
  const newestId = useRef<string | null>(null)
  const refreshing = useRef(false)
  const refresh = useCallback(async () => {
    if (refreshing.current) return
    refreshing.current = true
    try {
      const params = new URLSearchParams()
      if (kind) params.set('event_kind', kind)
      if (label) params.set('label', label)
      const result = await loadEvents(params.size ? `?${params}` : '')
      const latest = result.items[0]?.id ?? null
      const followLatest = selectedId.current === null || selectedId.current === newestId.current
      setEvents(result.items); setTotal(result.total)
      if (latest && followLatest) { selectedId.current = latest; setSelected(await loadEvent(latest)) }
      else if (selectedId.current) setSelected(await loadEvent(selectedId.current))
      newestId.current = latest; setLastUpdated(new Date()); setError(null)
    } finally { refreshing.current = false }
  }, [kind, label])
  useEffect(() => {
    fetch(`${apiBaseUrl}/api/v1/health`).then((response) => setOnline(response.ok)).catch(() => setOnline(false))
    const update = () => refresh().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : t('errors.load')))
    update(); const timer = window.setInterval(update, 3000)
    return () => window.clearInterval(timer)
  }, [refresh, t])
  const resetFollow = () => { selectedId.current = null; newestId.current = null; setSelected(null) }
  const choose = async (id: string) => {
    setError(null)
    try { selectedId.current = id; setSelected(await loadEvent(id)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : t('errors.load')) }
  }
  const feedback = async (verdict: string) => {
    if (!selected) return
    setSaving(true)
    try {
      await saveFeedback(selected.id, verdict); selectedId.current = selected.id; setSelected(await loadEvent(selected.id))
      setEvents((items) => items.map((item) => item.id === selected.id ? { ...item, feedback_verdict: verdict } : item))
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('errors.save')) }
    finally { setSaving(false) }
  }
  return <main>
    <header>
      <div><p className="eyebrow">NANEXUS / COMMUNITY</p><h1>{t('app.title')}</h1><p className="summary">{t('app.summary')}</p></div>
      <div className="header-actions">
        <label className="language-select"><span>{t('language.label')}</span><select aria-label={t('language.label')} value={language} onChange={(event) => void setLanguage(event.target.value as Language)}><option value="en">{t('language.english')}</option><option value="zh-CN">{t('language.chinese')}</option></select></label>
        <div className="status"><span className={`indicator ${online ? 'online' : ''}`} />{t(online ? 'backend.online' : 'backend.offline')}</div>
      </div>
    </header>
    <section className="filters" aria-label={t('filters.ariaLabel')}>
      <label>{t('filters.type')}<select value={kind} onChange={(event) => { resetFollow(); setKind(event.target.value) }}><option value="">{t('filters.all')}</option><option value="review">Review</option><option value="object">{t('filters.originalObject')}</option><option value="system">System</option></select></label>
      <label>{t('filters.label')}<input value={label} placeholder="person / car" onChange={(event) => { resetFollow(); setLabel(event.target.value) }} /></label>
      <span className="count">{t('status.eventCount', { count: total })} · {lastUpdated ? t('status.refreshed', { time: lastUpdated.toLocaleTimeString(language) }) : t('status.connecting')}</span>
    </section>
    {error && <div role="alert" className="error">{error}</div>}
    <div className="workspace">
      <aside aria-label={t('list.ariaLabel')}>
        {events.length === 0 && <p className="empty">{t('list.empty')}</p>}
        {events.map((item) => <button key={item.id} className={`event-card ${selected?.id === item.id ? 'active' : ''}`} onClick={() => void choose(item.id)}>
          <span className="event-top"><b>{item.camera_name ?? item.source_name}</b><time>{clock(item.last_occurred_at, language)}</time></span>
          <span className="chips">{item.labels.map((value) => <i key={value}>{value}</i>)}<i>{item.lifecycle}</i>{item.partial_history && <i className="warn">{t('list.partialHistory')}</i>}</span>
          <span className="event-bottom"><span>{clock(item.first_occurred_at, language)}–{clock(item.last_occurred_at, language)} · {duration(item.first_occurred_at, item.last_occurred_at, t)}</span>{item.feedback_verdict && <em>{t('list.annotated')}</em>}</span>
          <span className="event-bottom">{item.event_kind} · {item.zones.join(', ') || t('list.noZone')} · {t('list.observationCount', { count: item.observation_count })}</span>
        </button>)}
      </aside>
      <article aria-label={t('detail.ariaLabel')}>
        {!selected && <p className="empty">{t('detail.empty')}</p>}
        {selected && <>
          <div className="detail-title"><div><p className="eyebrow">{selected.event_kind} / {selected.lifecycle}</p><h2>{selected.camera_name ?? selected.source_name}</h2></div><time>{time(selected.occurred_at, language)}</time></div>
          <EventSnapshot key={selected.id} eventId={selected.id} occurredAt={selected.occurred_at} />
          <section className="lifecycle"><div><strong>{t('detail.lifecycle')}</strong><span>{clock(selected.first_occurred_at, language)}–{clock(selected.last_occurred_at, language)} · {t('detail.duration', { value: duration(selected.first_occurred_at, selected.last_occurred_at, t) })}</span></div>{selected.related_entity_ids.length > 0 && <p className="related-objects">{t('detail.relatedObjects')} {selected.related_entity_ids.map((id) => <code key={id}>{id}</code>)}</p>}<ol>{selected.timeline.map((item, index, items) => <li key={item.id} className={item.lifecycle}><time>{clock(item.occurred_at, language)}</time><b>{timelineText(item, index, items, t)}</b><small>{item.zones.join(', ') || t('list.noZone')} · {item.source_entity_id}</small></li>)}</ol></section>
          <section className="feedback"><strong>{t('feedback.question')}</strong><div>{verdicts.map((key) => <button key={key} disabled={saving} className={selected.feedback?.verdict === verdictValues[key] ? 'chosen' : ''} onClick={() => void feedback(verdictValues[key])}>{t(`feedback.${key}`)}</button>)}</div></section>
          <dl><div><dt>{t('detail.source')}</dt><dd>{selected.source_name} · {selected.source_type} {selected.source_version}</dd></div><div><dt>{t('detail.externalId')}</dt><dd>{selected.source_namespace}:{selected.source_entity_id}</dd></div><div><dt>{t('detail.internalId')}</dt><dd>{selected.id}</dd></div><div><dt>Revision</dt><dd>{selected.source_revision} / schema {selected.schema_version}</dd></div></dl>
          {selected.decisions[0] && <section className="decision-card"><span>{t('decision.heading')}</span><p className="decision-explainer">{t('decision.explanation')}</p><strong>{t(`outcome.${selected.decisions[0].outcome}`, { defaultValue: selected.decisions[0].outcome })}<small> ({selected.decisions[0].outcome})</small></strong><p>{selected.decisions[0].reasons.join(language === 'zh-CN' ? '；' : '; ')}</p><p className={`delivery-state ${(selected.notifications ?? []).length > 0 ? 'delivered' : ''}`}>{t((selected.notifications ?? []).length > 0 ? 'decision.hasNotification' : 'decision.noNotification')}</p><small>{t('detail.rule')}: {selected.decisions[0].policy_id}@{selected.decisions[0].policy_version} · {selected.decisions[0].rule_trace.matched_rule_id ?? 'default'}</small><details><summary>{t('decision.trace')}</summary><pre>{JSON.stringify(selected.decisions[0].rule_trace.trace ?? [], null, 2)}</pre></details></section>}
          {(selected.notifications ?? []).length > 0 && <section className="decision-card notification-card"><span>{t('decision.notificationRecords')}</span>{selected.notifications.map((item) => <p key={item.id}><strong>{item.delivery_status}</strong> · {item.channel} / {item.stage} · {t('decision.attempts', { count: item.attempts })}{item.last_error && ` · ${item.last_error}`}</p>)}</section>}
          <h3>{t('detail.objectsAndEvidence')}</h3><div className="evidence-grid"><div><b>{t('detail.objects', { count: selected.objects.length })}</b>{selected.objects.map((item) => <p key={item.id}>{item.label} · {item.confidence == null ? '—' : `${Math.round(item.confidence * 100)}%`}</p>)}</div><div><b>{t('detail.evidence', { count: selected.evidence.length })}</b>{selected.evidence.map((item) => <p key={item.id}>{item.media_type} · {item.availability} · {item.privacy_class}</p>)}</div></div>
          <details><summary>{t('detail.canonicalData')}</summary><pre>{JSON.stringify({ labels: selected.labels, zones: selected.zones, extensions: selected.extensions, decisions: selected.decisions }, null, 2)}</pre></details>
          <details><summary>{t('detail.rawData')}</summary><pre>{selected.raw_message ? JSON.stringify(selected.raw_message, null, 2) : t('detail.rawUnavailable')}</pre></details>
        </>}
      </article>
    </div>
  </main>
}
