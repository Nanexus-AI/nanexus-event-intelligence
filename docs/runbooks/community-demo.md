# Community 一键 Demo

## English

This demo runs the complete flow without a camera or Home Assistant. It uses
synthetic test events matching the Frigate 0.17 format. The fixture contains no
camera images, video or other media:

```text
Fixture → Frigate Adapter → Canonical Observation → PostgreSQL/Outbox/Redis
→ Community Rule/Decision → local Webhook → Action/Notification → UI → Replay
```

It makes no cloud calls, reads no real Frigate/HA endpoint and does not modify
`.env`. The local webhook records only redacted structured logs and returns a
deterministic request ID. The v0.1.0 UI and API provide no built-in
authentication or authorization. Compose publishes ports 5173 and 8000 on the
host, so run the demo only on a trusted local network and never expose those
ports directly to the public Internet.

This path uses development containers and source mounts for trusted-LAN
evaluation; it is not a production deployment profile. It requires a running
Docker daemon, Docker Compose v2 or legacy `docker-compose`, POSIX Make, free
host ports 5173/8000 and loopback ports 5432/6379. The first build needs outbound
access to download container images and dependencies. From a checkout or
extracted source archive, run:

```bash
cp .env.example .env
make setup-check
make demo
```

The Makefile selects the available Compose command. `make demo` builds images,
starts PostgreSQL, Redis and the local webhook, applies Alembic migrations, starts API/UI/pipeline, ingests the fixture,
waits for closed-loop convergence and performs a side-effect-free Replay.

```json
{"status":"community-demo-complete","closed_loop":{"observations":6,"processed":6,"decisions":6,"notifications_succeeded":6},"replay":{"event_count":6,"production_side_effects":false}}
```

Open UI at <http://localhost:5173>, events API at <http://localhost:8000/api/v1/events> and the provisional
interactive API reference at
<http://localhost:8000/docs>. The UI switches between English and Simplified
Chinese and remembers the browser-local choice. Localization never rewrites
camera names, zones, labels, configuration or other upstream data.

Re-running `make demo` creates no additional Observation, Decision or
Notification. The demo webhook is Compose-internal and uses an explicitly
non-production secret; Replay forbids production side effects. Existing named
volumes are preserved and demo records are isolated by Source Instance. Use a
separate Compose project/volume for a clean acceptance environment rather than
deleting a volume that may contain user data.

Stop with `make demo-down`; containers and networks are removed but named-volume
data remains. For troubleshooting, inspect pipeline-worker and demo-webhook
logs, resolve port conflicts and PostgreSQL migration failures, inspect pending
and DLQ state instead of deleting audit rows, and never bypass fixture hash or
`contains_secrets=false` validation.

## 中文

## 目标

无需摄像头或 Home Assistant，使用符合 Frigate 0.17 格式的合成测试事件数据跑通完整
流程。测试数据不包含摄像机截图、视频或其他媒体文件：

```text
Fixture → Frigate Adapter → Canonical Observation → PostgreSQL/Outbox/Redis
→ Community Rule/Decision → 本地 Webhook → Action/Notification → UI → Replay
```

Demo 不调用云服务，不读取真实 Frigate/HA 地址，也不会修改 `.env`。本地 Demo webhook 只记录脱敏结构化日志并返回确定性 request ID。v0.1.0 UI 和 API 不提供内置身份认证或权限控制；Compose 会在主机上发布 5173 和 8000 端口，因此只能在可信局域网运行，禁止把这些端口直接暴露到公网。

## 运行

该路径使用 development 容器和源码挂载，只用于可信局域网评估，不是生产部署配置。
主机需要正在运行的 Docker、Docker Compose v2 或旧版 `docker-compose`、POSIX Make、
可用的 5173/8000 端口和仅绑定本机的 5432/6379 端口。首次构建需要联网下载镜像和依赖。
在检出的仓库或解压后的源码目录中执行：

```bash
cp .env.example .env
make setup-check
make demo
```

命令会构建镜像、启动 PostgreSQL/Redis、本地 webhook，执行 Alembic Migration，启动 API/UI/pipeline，写入 fixture，等待闭环收敛并执行无副作用 Replay。成功时输出：

```json
{"status":"community-demo-complete","closed_loop":{"observations":6,"processed":6,"decisions":6,"notifications_succeeded":6},"replay":{"event_count":6,"production_side_effects":false}}
```

然后访问：

- UI：<http://localhost:5173>
- API：<http://localhost:8000/api/v1/events>
- 暂定接口的交互式 API 参考：<http://localhost:8000/docs>

Web UI 顶部可选择 `English` 或 `简体中文`，切换立即生效并保存在当前浏览器。首次访问按浏览器语言选择，无法识别时默认英语。该设置只影响系统界面文案、日期和时间格式，不翻译或改写用户配置、摄像头名称、区域、标签及其他上游数据。

事件来源显示为 `community-demo-frigate`，全新 Demo 数据的摄像头显示为 `Community Demo Entrance`。可查看 Raw/Canonical、Decision reason trace、成功通知，并提交人工反馈。

## 重复性与安全

再次执行 `make demo` 不新增 Observation、Decision 或 Notification；输出中的 `ingest.persisted` 为 0，闭环数量和 Replay digest 保持不变。Demo 通知只指向 Compose 内部 `demo-webhook`，共享密钥固定为非生产示例值。Replay 明确禁止生产副作用。

当前 Demo 使用项目的持久卷，因此不会删除用户已有本地开发数据；Demo 数据通过独立 Source Instance 隔离。若需要全新环境验收，应使用独立 Compose project/volume，不要删除包含用户数据的现有 volume。

## 停止

```bash
make demo-down
```

该命令停止并移除 Demo/开发容器和网络，但保留命名 volume 中的数据。恢复普通开发配置可执行 `make dev`。

## 排障

- 超时：使用 `docker compose ... logs pipeline-worker demo-webhook` 检查日志；旧版环境将 `docker compose` 替换为 `docker-compose`；
- 端口冲突：停止占用 5173/8000 的其他服务；
- Migration 失败：确认 PostgreSQL 健康且 `.env` 的本地开发数据库配置有效；
- 通知数不足：检查 notification consumer group pending/DLQ，不要直接删除审计行；
- fixture integrity 失败：不要绕过 hash/`contains_secrets=false` 校验。
