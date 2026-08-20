# Nanexus Event Intelligence

English | [简体中文](./README.zh-CN.md)

Turn raw NVR events into reviewable, explainable and actionable local intelligence.

Nanexus Event Intelligence is a local-first event processing and response layer
for security-camera systems. It preserves the original source facts, organizes
related activity into a clear timeline, explains every rule decision and keeps
people in control of feedback and outbound notifications.

Frigate is the first Reference Source Adapter. The core uses a vendor-neutral
Canonical Model so additional NVR/VMS integrations can follow the same contracts.

> **v0.1.0 security boundary:** The UI and API do not provide built-in
> authentication or authorization. Deploy the project only on a trusted local
> network, and do not expose ports 5173 or 8000 directly to the public Internet.
> Authentication and public-network deployment are outside the scope of this release.

## Why this project

Camera platforms produce large volumes of events, object updates, reviews and
media references. The difficult part is not receiving another alert; it is
understanding what happened, why the system made a decision and whether that
decision was useful.

### 🧱 Why v0.1.0 matters

v0.1.0 establishes a coherent foundation for intelligence above the
camera-event layer. By preserving source facts, normalizing events into a
versioned Canonical Model and making decisions and feedback auditable, it gives
future analytics, automation and intelligent applications a consistent base to
build on instead of requiring each capability to reinterpret source-specific
events independently.

The same boundary keeps the core independent from any single NVR/VMS product.
Frigate is the first implemented Reference Source Adapter; it does not impose
product-specific constraints on the core. Other source systems can be added
through adapters that translate
their native events into the same canonical foundation, without embedding their
protocols or data formats in upper-layer intelligence.

Nanexus Event Intelligence provides a transparent layer between event sources
and response channels:

- retain raw source facts for audit instead of replacing them with a summary;
- normalize vendor-specific events into a vendor-neutral Canonical Model;
- group Review alerts and tracked Objects without losing their full lifecycle;
- show the evidence and rule trace behind each decision;
- capture human feedback for later evaluation;
- replay historical events deterministically without production side effects;
- keep event processing local unless an operator explicitly enables an outbound channel.

## ✨ What you can do today

### Inspect complete event stories

Ingest Frigate MQTT events, preserve Raw and Canonical representations, group
related Objects beneath their parent Review and inspect an ordered lifecycle
timeline with labels, zones, duration and evidence availability.

### Understand every decision

Run deterministic Community rules in shadow mode and inspect the outcome,
matched rule, policy version, reason trace and supporting facts. A shadow
`suppress` result never silences an existing high-risk notification.

### Close the feedback loop

Mark events as important, not important, false positive or uncertain. Feedback
is revisioned and audited instead of silently rewriting past decisions.

### Deliver notifications explicitly

Enable the generic/Home Assistant-compatible webhook only when needed. Delivery
uses stable idempotency keys, bounded retries, persistent status and a DLQ path.
Notifications are disabled by default.

### Reproduce and compare behavior

Export integrity-checked Replay bundles and run them immediately, at scaled
speed, step-by-step or with a fixed logical clock. Replay is side-effect-free by
default and supports deterministic rule-result digests.

### Keep media and source access local

Fetch Frigate snapshots on demand through a constrained same-origin proxy. Media
is not copied into the Nanexus database, logs or Git, and source credentials are
never sent to the browser.

## 🚀 Try the Community Demo

This evaluation setup needs a running Docker daemon, Docker Compose v2 or the
legacy `docker-compose` command, POSIX Make and available local ports 5173 and
8000. The first build needs outbound access to download images and dependencies.
It uses synthetic test events matching the Frigate 0.17 format and a
Compose-internal webhook; no camera, Home Assistant instance or cloud service
is required. The fixture contains no camera images, video or other media.

```bash
# From a checkout or extracted source archive
cp .env.example .env
make setup-check
make demo
```

When the command reports `community-demo-complete`, open:

- Web UI: <http://localhost:5173>
- Events API: <http://localhost:8000/api/v1/events>
- Provisional interactive API reference: <http://localhost:8000/docs>

The demo exercises the complete path:

```text
Fixture → Frigate Adapter → Canonical Observation → PostgreSQL/Outbox/Redis
→ Community Rule/Decision → local Webhook → Notification → UI → Replay
```

Run `make demo` again to verify idempotency, then stop it with:

```bash
make demo-down
```

See the [Community Demo runbook](./docs/runbooks/community-demo.md) for expected
results, data-preservation behavior and troubleshooting.

## Connect a real Frigate instance

For trusted-LAN evaluation, copy the environment template and follow the live
ingestion guide:

```bash
cp .env.example .env
make setup-check
make live-demo
```

Keep real endpoints and credentials only in the untracked `.env` file. Read the
[Live Demo runbook](./docs/runbooks/live-demo.md),
[Frigate HTTP Client runbook](./docs/runbooks/frigate-http-client.md) and
[Media Demo runbook](./docs/runbooks/media-demo.md) before connecting a real
system.

## 🧭 Architecture at a glance

```text
Source Adapter → Canonical Event → Persistence / Reliable Pipeline
                               → Rules / Explainable Decisions
                               → UI / Feedback / Notification / Replay
```

Source-specific clients, topics, payloads and URLs stay inside their Adapter.
Core modules consume only canonical contracts. Community builds, tests and runs
without a private package, license service or cloud dependency.

## 🔒 Current boundaries

- v0.1.0 is limited to trusted local-network evaluation and provides no authentication or RBAC.
- Frigate is currently the only completed Source Adapter.
- Rules are deterministic, versioned Community policies rather than a production-editable DSL.
- Webhook delivery is opt-in and requires receiver-side idempotency handling.
- Clips, media retention management, user-level authorization and production hardening are outside the v0.1.0 scope.
- The project does not currently claim measured false-positive reduction; that requires pilot evaluation data.
- v0.1.0 focuses on deployment, evaluation and core usage and includes the API
  implementation and related integration code. Detailed API and extension
  documentation is planned for v0.2.0, provisionally within one to two weeks
  after v0.1.0; interfaces should be considered provisional until documented as stable.

## v0.1.0 documentation

- [Community Demo](./docs/runbooks/community-demo.md)
- [Live Frigate Demo](./docs/runbooks/live-demo.md)
- [Media access](./docs/runbooks/media-demo.md)
- [Frigate HTTP connection](./docs/runbooks/frigate-http-client.md)
- [Security policy](./SECURITY.md)
- [Contributing](./CONTRIBUTING.md)
- [Changelog](./CHANGELOG.md)

## Independence, license and trademarks

The Frigate name is used only to describe compatibility. This project is
independent and is not affiliated with, sponsored by or endorsed by the Frigate
project or its maintainers.

Nanexus Event Intelligence is licensed under the
[Apache License 2.0](./LICENSE). See [NOTICE](./NOTICE) for attribution and
trademark information. Report vulnerabilities privately as described in
[SECURITY.md](./SECURITY.md).
