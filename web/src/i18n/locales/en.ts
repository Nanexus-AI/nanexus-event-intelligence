const en = {
  app: { title: 'Event Inspector', summary: 'From Canonical Event to human feedback, every decision retains its source and evidence.' },
  language: { label: 'Language', english: 'English', chinese: '简体中文' },
  backend: { online: 'Backend online', offline: 'Backend offline' },
  filters: { ariaLabel: 'Event filters', type: 'Type', all: 'All', originalObject: 'Raw Object', label: 'Label' },
  status: { eventCount_one: '{{count}} event', eventCount_other: '{{count}} events', refreshed: '{{time}} refreshed', connecting: 'Connecting' },
  list: { ariaLabel: 'Event list', empty: 'No matching events', partialHistory: 'Partial history', annotated: 'Annotated', noZone: 'No zone', observationCount_one: '{{count}} update', observationCount_other: '{{count}} updates' },
  detail: { ariaLabel: 'Event details', empty: 'Select an event to view details', lifecycle: 'Lifecycle', duration: 'Duration {{value}}', relatedObjects: 'Related objects', source: 'Source', externalId: 'External ID', internalId: 'Internal ID', rule: 'Rule', objectsAndEvidence: 'Objects and evidence', objects: 'Objects {{count}}', evidence: 'Evidence {{count}}', canonicalData: 'Canonical data', rawData: 'Raw source data', rawUnavailable: 'Raw message unavailable' },
  feedback: { question: 'Is this event useful?', important: 'Important', notImportant: 'Not important', falsePositive: 'False positive', uncertain: 'Uncertain' },
  outcome: { send: 'Recommend sending', escalate: 'Recommend escalation', suppress: 'Recommend suppression', no_action: 'Recommend no action', enrich: 'Recommend further analysis', hold: 'Recommend holding' },
  timeline: { appeared: 'Object {{id}} appeared', disappeared: 'Object {{id}} disappeared', enteredZone: 'Entered zone: {{zones}}', updated: 'Status updated' },
  duration: { seconds: '{{seconds}} sec', minutesSeconds: '{{minutes}} min {{seconds}} sec' },
  snapshot: { unavailable: 'Snapshot is temporarily unavailable', missing: 'This event has no snapshot', generating: 'Snapshot is being generated. Try again shortly.', expired: 'Snapshot expired or was deleted', frigateUnavailable: 'Unable to connect to Frigate', alt: 'Event snapshot', loading: 'Loading snapshot…', reload: 'Reload snapshot' },
  errors: { load: 'Failed to load', save: 'Failed to save' },
  decision: { heading: 'Rule recommendation · Shadow evaluation', explanation: 'This rule recommendation is provided for comparison with human feedback; it does not mean a notification was sent.', hasNotification: 'This event has notification records; see details below', noNotification: 'This event has no notification records; notifications must be explicitly enabled by the deployer.', trace: 'View rule evaluation', notificationRecords: 'Notification records', attempts_one: '{{count}} attempt', attempts_other: '{{count}} attempts' },
} as const
export default en
