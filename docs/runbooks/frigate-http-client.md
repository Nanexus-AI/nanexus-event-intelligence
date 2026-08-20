# Frigate HTTP Client 操作手册

## English

The ADAPTER-003 read-only client checks the Frigate version, historical events,
Reviews, snapshots and previews. It does not call write endpoints or print event
IDs, camera names or authentication data.

Use port `5000` only inside a controlled trusted LAN:

```dotenv
FRIGATE_HTTP_BASE_URL=http://192.168.x.x:5000
FRIGATE_HTTP_BEARER_TOKEN=
FRIGATE_HTTP_USERNAME=
FRIGATE_HTTP_PASSWORD=
FRIGATE_HTTP_PROXY_SECRET=
FRIGATE_HTTP_TRUSTED_INTERNAL=true
FRIGATE_HTTP_CA_BUNDLE=
```

Prefer authenticated port `8971` in production or across trust boundaries:

```dotenv
FRIGATE_HTTP_BASE_URL=https://frigate.example.internal:8971
FRIGATE_HTTP_BEARER_TOKEN=
FRIGATE_HTTP_USERNAME=your-user
FRIGATE_HTTP_PASSWORD=your-password
FRIGATE_HTTP_PROXY_SECRET=
FRIGATE_HTTP_TRUSTED_INTERNAL=false
FRIGATE_HTTP_CA_BUNDLE=/absolute/path/to/private-ca.pem
```

Choose exactly one of bearer token, username/password or `X-Proxy-Secret`.
Leave the CA bundle empty for a system-trusted certificate; otherwise provide an
absolute private-CA chain path. Never commit passwords or private keys.

```bash
set -a
source .env
set +a
cd backend
uv run frigate-http-smoke
```

Successful output contains only the Frigate version, completed check categories
and media byte counts. The CLI scans at most 20 recent events. For failures,
verify `.env`, authentication and trust settings; fix CA/service certificates
instead of disabling verification. The client retries timeouts, 429 and common
5xx responses. Default limits are 2 MiB for JSON and 25 MiB for media; confirm
the source is trusted before increasing them.

## 中文

## 目的

使用 ADAPTER-003 的只读 client 检查 Frigate 版本、历史事件、Review、snapshot 和 preview。命令不会调用写接口，也不会输出事件 ID、摄像头名称或认证信息。

## 方式一：可信局域网内部端口

只应在受控局域网内使用 Frigate `5000` 端口。将以下配置写入仓库根目录未跟踪的 `.env`：

```dotenv
FRIGATE_HTTP_BASE_URL=http://192.168.x.x:5000
FRIGATE_HTTP_BEARER_TOKEN=
FRIGATE_HTTP_USERNAME=
FRIGATE_HTTP_PASSWORD=
FRIGATE_HTTP_PROXY_SECRET=
FRIGATE_HTTP_TRUSTED_INTERNAL=true
FRIGATE_HTTP_CA_BUNDLE=
```

## 方式二：认证端口

生产或跨信任边界连接优先使用 Frigate `8971` 认证端口：

```dotenv
FRIGATE_HTTP_BASE_URL=https://frigate.example.internal:8971
FRIGATE_HTTP_BEARER_TOKEN=
FRIGATE_HTTP_USERNAME=your-user
FRIGATE_HTTP_PASSWORD=your-password
FRIGATE_HTTP_PROXY_SECRET=
FRIGATE_HTTP_TRUSTED_INTERNAL=false
FRIGATE_HTTP_CA_BUNDLE=/absolute/path/to/private-ca.pem
```

Bearer token、用户名/密码、`X-Proxy-Secret` 三种认证方式只能选择一种。使用系统已信任的证书时，CA bundle 留空；使用私有 CA 时填写证书链绝对路径。不要把密码或证书私钥提交到 Git。

## 执行只读 smoke

从仓库根目录执行：

```bash
set -a
source .env
set +a
cd backend
uv run frigate-http-smoke
```

成功输出只包含 Frigate 版本、完成的检查类别和读取的媒体字节数。如果近期事件没有 snapshot 或关联 Review，相应类别可能不出现；CLI 最多扫描 20 个近期事件。

## 故障排查

- `FRIGATE_HTTP_BASE_URL is required`：确认从仓库根目录加载了 `.env`；
- 配置拒绝 HTTP 或 5000：仅在确认为可信内网时设置 `FRIGATE_HTTP_TRUSTED_INTERNAL=true`；
- TLS 验证失败：配置正确的 CA bundle 或修复服务证书，不要关闭证书校验；
- 401/403：确认只配置了一种认证模式，并检查 Frigate 用户、token 或代理 secret；
- 404：近期对象可能已被保留策略清理，CLI 会继续扫描其他事件；
- timeout/5xx/429：client 会有限重试；持续失败时检查 Frigate 健康、反向代理和网络；
- 响应过大：提高上限前先确认数据来源可信；默认 JSON 2 MiB、媒体 25 MiB。
