# 真实 Frigate Live Demo

## English

The Live Demo reads LAN Frigate MQTT settings from `.env` and sends events
through the Reference Adapter, Canonical Model, rule Decision and UI. The page
polls every three seconds: newest events rise to the top, live-follow opens new
alerts, manual selection of an older event is preserved, and the current detail,
Decision and notification status continue to refresh. This is near-real-time
polling, not a hard real-time guarantee.

## Evaluation scope and prerequisites

This path uses development containers and source mounts for trusted-LAN
evaluation; it is not a production deployment profile. The host needs a running
Docker daemon, Docker Compose v2 or legacy `docker-compose`, POSIX Make, free
host ports 5173/8000 and loopback ports 5432/6379. The first build needs outbound
access to download images and dependencies. From a checkout or extracted source
archive, run:

```bash
cp .env.example .env
make setup-check
```

The Makefile selects the available Compose command. Before starting Live Demo,
edit the untracked `.env` with the settings below.

The untracked `.env` needs at least:

```dotenv
FRIGATE_MQTT_HOST=<broker-host>
FRIGATE_MQTT_PORT=1883
FRIGATE_MQTT_USERNAME=<username-if-required>
FRIGATE_MQTT_PASSWORD=<password-if-required>
FRIGATE_MQTT_TOPIC_PREFIX=frigate
FRIGATE_SOURCE_NAME=frigate-primary
FRIGATE_SOURCE_VERSION=0.17.1-416a9b7
```

Never copy real addresses or passwords into `.env.example`, documentation,
screenshots or Git. Start with `make live-demo`, then open
<http://localhost:5173> locally or `http://<LAN-host-IP>:5173` from another
trusted LAN device. The same-origin `/api` proxy prevents a remote browser from
calling its own localhost. Do not expose ports 5173 or 8000 publicly. The
v0.1.0 Community UI provides no built-in authentication or authorization.

`frigate_mqtt_connected topics=4` confirms connection, not that an alert has
occurred. Real events should appear under `frigate-primary`, followed by a
Decision. Zero Notifications is the safe default unless delivery is explicitly
enabled. Inspect logs with:

```bash
docker compose -f compose.yaml --profile frigate logs -f frigate-ingest-worker pipeline-worker
```

With legacy Compose, replace `docker compose` with `docker-compose`.

Run `make live-demo-down` to stop only live ingest while retaining API, UI and
local data. Use `make down` for a complete stop.

## 中文

## 效果

Live Demo 使用 `.env` 中配置的局域网 Frigate MQTT，实时经过 Reference Adapter、Canonical Model、规则 Decision 和 UI。页面每 3 秒刷新一次：

- 最新事件自动置顶；
- 正在跟随最新事件时，新报警会自动打开；
- 手动查看旧事件时不会被抢走选择；
- 当前详情会继续刷新，Decision 和通知状态生成后自动出现；
- 筛选和人工反馈仍可使用。

这属于接近实时的轮询版本，通常在事件入库后的数秒内可见，不承诺硬实时延迟。

## 评估范围与环境要求

该路径使用 development 容器和源码挂载，只用于可信局域网评估，不是生产部署配置。
主机需要正在运行的 Docker、Docker Compose v2 或旧版 `docker-compose`、POSIX Make、
可用的 5173/8000 端口和仅绑定本机的 5432/6379 端口。首次构建需要联网下载镜像和依赖。
在检出的仓库或解压后的源码目录中执行：

```bash
cp .env.example .env
make setup-check
```

Makefile 会自动选择可用的 Compose 命令。启动 Live Demo 前，按下列内容修改未跟踪的
`.env`。

## 前置配置

未跟踪的 `.env` 至少需要：

```dotenv
FRIGATE_MQTT_HOST=<broker-host>
FRIGATE_MQTT_PORT=1883
FRIGATE_MQTT_USERNAME=<username-if-required>
FRIGATE_MQTT_PASSWORD=<password-if-required>
FRIGATE_MQTT_TOPIC_PREFIX=frigate
FRIGATE_SOURCE_NAME=frigate-primary
FRIGATE_SOURCE_VERSION=0.17.1-416a9b7
```

不要把真实地址或密码复制到 `.env.example`、文档、截图或 Git。

## 启动

```bash
make live-demo
```

该命令会停止本地 fixture Demo webhook，构建服务、执行 Migration，并以普通 `.env` 配置重建 API、Web、pipeline 和 Frigate ingest worker。

本机打开：<http://localhost:5173>。局域网其他设备打开：

```text
http://<运行本项目这台电脑的局域网IP>:5173
```

Web 使用同源 `/api` 代理，因此远程浏览器不会错误访问自己的 `localhost:8000`。不要把 5173/8000 暴露到公网；v0.1.0 Community UI 不提供内置身份认证或权限控制。

## 判断连接和事件

连接成功日志包含：

```text
frigate_mqtt_connected topics=4
```

只看到连接成功不等于已经发生报警。真实事件到达后，UI 应出现 `frigate-primary` 来源，随后自动显示 Decision。若通知未显式启用，Notification 为 0 是安全默认行为，不影响实时分析。

查看日志：

```bash
docker compose -f compose.yaml --profile frigate logs -f frigate-ingest-worker pipeline-worker
```

使用旧版 Compose 时，将 `docker compose` 替换为 `docker-compose`。

## 停止实时接入

```bash
make live-demo-down
```

这只停止 Frigate ingest worker，保留 API/UI 和本地数据。完整停止使用 `make down`。
