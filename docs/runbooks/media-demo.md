# MEDIA-DEMO-001：事件快照演示

## English

The Media Demo displays Frigate event snapshots in Live Demo details. Frigate
retains the media; the backend fetches it on demand for the browser and does not
copy it into the database or local storage.

1. Configure `FRIGATE_HTTP_*` as described in
   `docs/runbooks/frigate-http-client.md`. Trust clear-text HTTP/5000 only on a
   verified trusted network.
2. Run `make live-demo`.
3. Open `http://<host-LAN-IP>:5173` from the trusted LAN and choose an event with
   a snapshot.
4. The page requests `/api/v1/events/{observation_id}/media/snapshot`. A failure
   shows an unavailable state without blocking events, Decisions or feedback.

Review events resolve the related tracked-object event ID through Canonical
`extensions.links`; the browser never receives Frigate addresses, credentials or
raw media URLs.

The backend pins the origin, rejects redirects, limits response size and enforces
timeouts and authentication. Only JPEG, PNG and WebP are accepted; responses use
`private, no-store`, `nosniff` and a restrictive CSP. Media is never written to
the Nanexus database, logs or Git. The v0.1.0 endpoint provides no user authentication or authorization and must
remain on a trusted LAN. Keep real endpoints and credentials only in local
`.env`.

For 503 errors, check configuration and mutually exclusive authentication. A 404
can mean the event has no snapshot, a Review lacks a linked detection or Frigate
retention removed the media. Inspect the same-origin request and backend logs,
but never paste authentication data into an issue. Clips, thumbnail caching,
retention management, downloads, access auditing and per-user authorization are
outside the current scope.

## 中文

## 目标

在 Live Demo 的事件详情中直接显示 Frigate 事件快照。媒体仍由 Frigate 保存，系统只在浏览器请求时通过后端按需拉取，不复制到数据库或本地磁盘。

## 使用

1. 按 `docs/runbooks/frigate-http-client.md` 配置 `FRIGATE_HTTP_*`。内网 HTTP/5000 只有在确认网络可信后才设置 `FRIGATE_HTTP_TRUSTED_INTERNAL=true`。
2. 运行 `make live-demo`。
3. 从可信局域网打开 `http://<运行本项目的主机 IP>:5173`，选择一条有快照的事件。
4. 页面会自动请求 `/api/v1/events/{observation_id}/media/snapshot`；失败时显示“快照暂不可用”，不会阻塞事件、Decision 或反馈功能。

Review 事件会通过 Canonical `extensions.links` 解析关联的 tracked-object event ID；前端不会拿到 Frigate 地址、认证信息或原始媒体 URL。

## 安全与数据边界

- 后端沿用 Frigate HTTP Client 的 origin 钉扎、禁止 redirect、响应大小限制、超时和认证规则。
- 只接受 JPEG、PNG、WebP；响应带 `private, no-store`、`nosniff` 和限制性 CSP。
- 媒体不写入 Nanexus 数据库、日志或 Git；Canonical Evidence 仅保存延迟获取引用和可用性元数据。
- v0.1.0 端点不提供用户身份认证或权限控制，只能用于可信局域网，禁止暴露公网。
- 真实地址和凭据只写本机 `.env`，不得写入文档、截图、fixture 或提交。

## 故障排查

- `503 Frigate media access is not configured`：检查 `.env` 中 `FRIGATE_HTTP_BASE_URL`。
- `503 ... configuration is invalid`：检查是否同时配置了多种认证，或 CA 路径不合法。
- `404 snapshot is not available`：事件可能没有快照，Review 可能没有关联 detection，或 Frigate 已按保留策略删除媒体。
- 页面有事件但图片失败：从浏览器网络面板查看同源 snapshot 请求；同时检查 backend 日志，不要把认证信息贴入 issue。

## 当前不包含

视频 clip、缩略图缓存、媒体保留管理、媒体下载、访问审计和用户级授权均不在本任务范围内。
