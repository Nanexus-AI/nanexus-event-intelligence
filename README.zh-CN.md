# Nanexus Event Intelligence

[English](./README.md) | 简体中文

把原始 NVR 事件转化为可复核、可解释、可处置的本地智能。

Nanexus Event Intelligence 是面向安防摄像系统的本地优先事件处理与处置层。它保留
来源事实，把相关活动组织成清晰的时间线，解释每一次规则判断，并让使用者始终掌握
人工反馈和对外通知的控制权。

Frigate 是首个 Reference Source Adapter。核心使用来源中立的 Canonical Model，后续
NVR/VMS 集成可以沿用同一套契约。

> **v0.1.0 安全边界：** 当前 UI 和 API 不提供内置身份认证或权限控制。只能将本项目
> 部署在可信局域网内，禁止把 5173 或 8000 端口直接暴露到公网。身份认证和公网部署
> 不属于本次发布范围。

## 为什么需要这个项目

摄像系统会产生大量事件、目标更新、Review 和媒体引用。真正困难的并不是再收到一条
告警，而是理解发生了什么、系统为什么作出某个判断，以及这个判断是否真的有用。

### 🧱 v0.1.0 的意义

v0.1.0 建立了摄像事件层之上的统一基础：保留来源事实，把不同事件规范化为
版本化的 Canonical Model，并让 Decision 和人工反馈可以解释、复核与审计。未来的
分析、自动化和智能应用可以建立在这套一致基础之上，而不必各自重复理解不同来源的
专有事件。

同一边界也使核心不依赖某一个 NVR/VMS 产品。Frigate 是首个已经实现的 Reference
Source Adapter，但不会对核心形成产品特定约束。未来可以通过新的 Adapter 接入其他
来源系统，把各自的原生事件转换到同一套 Canonical 基础，同时避免把来源协议和数据
格式带入上层智能。

Nanexus Event Intelligence 在事件来源和处置渠道之间提供透明的一层：

- 保留原始来源事实用于审计，而不是用摘要替换事实；
- 把厂商专有事件规范化为来源中立的 Canonical Model；
- 归并 Review 告警和 tracked Object，同时保留完整生命周期；
- 展示每个 Decision 的证据和规则判断过程；
- 保存人工反馈，为后续评估提供数据；
- 在没有生产副作用的前提下确定性回放历史事件；
- 默认保持本地处理，只有操作者明确启用时才使用对外渠道。

## ✨ 当前可以完成什么

### 查看完整事件故事

接入 Frigate MQTT 事件，同时保留 Raw 和 Canonical 表达；把相关 Object 归入父 Review，
并按顺序查看包含标签、区域、持续时间和证据可用性的生命周期时间线。

### 理解每一次判断

以影子模式运行确定性的 Community 规则，查看 outcome、命中规则、策略版本、reason
trace 和支撑事实。影子 `suppress` 结果不会静音既有的高风险真实通知。

### 建立人工反馈闭环

把事件标记为重要、不重要、误报或不确定。反馈带版本和审计记录，不会静默改写过去
的 Decision。

### 显式启用通知

只在需要时开启兼容 generic/Home Assistant 的 webhook。投递使用稳定幂等键、有界
重试、持久化状态和 DLQ；通知默认关闭。

### 重现和比较系统行为

导出带完整性校验的 Replay Bundle，并按即时、倍速、单步或固定逻辑时钟运行。
Replay 默认无副作用，并能生成确定性的规则结果摘要。

### 保持媒体和来源访问在本地

通过受限制的同源代理按需获取 Frigate 快照。媒体不会被复制到 Nanexus 数据库、日志
或 Git，来源凭据也不会发送给浏览器。

## 🚀 体验 Community Demo

评估环境需要正在运行的 Docker、Docker Compose v2 或旧版 `docker-compose` 命令、
POSIX Make，以及本机可用的 5173 和 8000 端口。首次构建需要联网下载镜像和依赖。
Demo 使用符合 Frigate 0.17 格式的合成测试事件数据和 Compose 内部 webhook，不需要摄像头、
Home Assistant 或云服务。测试数据不包含摄像机截图、视频或其他媒体文件。

```bash
# 在检出的仓库或解压后的源码目录中执行
cp .env.example .env
make setup-check
make demo
```

命令报告 `community-demo-complete` 后打开：

- Web UI：<http://localhost:5173>
- 事件 API：<http://localhost:8000/api/v1/events>
- 暂定接口的交互式 API 参考：<http://localhost:8000/docs>

Demo 会运行完整链路：

```text
Fixture → Frigate Adapter → Canonical Observation → PostgreSQL/Outbox/Redis
→ Community Rule/Decision → 本地 Webhook → Notification → UI → Replay
```

再次运行 `make demo` 可以验证幂等性，随后停止：

```bash
make demo-down
```

预期结果、数据保留行为和排障方式见
[Community Demo 操作手册](./docs/runbooks/community-demo.md)。

## 连接真实 Frigate

在可信局域网中评估时，复制环境模板并按实时接入手册操作：

```bash
cp .env.example .env
make setup-check
make live-demo
```

真实地址和凭据只能写入未跟踪的 `.env`。连接真实系统前请阅读
[Live Demo 操作手册](./docs/runbooks/live-demo.md)、
[Frigate HTTP Client 操作手册](./docs/runbooks/frigate-http-client.md)和
[Media Demo 操作手册](./docs/runbooks/media-demo.md)。

## 🧭 架构概览

```text
Source Adapter → Canonical Event → Persistence / Reliable Pipeline
                               → Rules / Explainable Decisions
                               → UI / Feedback / Notification / Replay
```

来源专有的 client、topic、payload 和 URL 只能停留在对应 Adapter 内。核心模块只消费
Canonical Contract。Community 不依赖私有包、许可证服务或云服务即可构建、测试和运行。

## 🔒 当前边界

- v0.1.0 仅面向可信局域网评估，不提供身份认证或 RBAC。
- Frigate 是当前唯一完成的 Source Adapter。
- 当前规则是确定性、版本化的 Community Policy，不是可在线编辑的生产 DSL。
- Webhook 必须显式启用，接收方需要按幂等键去重。
- 视频 clip、媒体保留管理、用户级授权和生产部署硬化不属于 v0.1.0 范围。
- 当前不宣称已经量化降低误报；该结论需要真实试点评估数据支持。
- v0.1.0 主要面向部署、评估和核心功能使用，并已包含 API 实现及相关集成代码。详细
  API 与扩展开发文档计划随 v0.2.0 提供，暂定在 v0.1.0 发布后 1～2 周内发布；在接口
  被明确标记为稳定之前，应将其视为可能调整的早期接口。

## v0.1.0 文档

- [Community Demo](./docs/runbooks/community-demo.md)
- [真实 Frigate Demo](./docs/runbooks/live-demo.md)
- [媒体访问](./docs/runbooks/media-demo.md)
- [Frigate HTTP 连接](./docs/runbooks/frigate-http-client.md)
- [安全政策](./SECURITY.md)
- [参与贡献](./CONTRIBUTING.md)
- [Changelog](./CHANGELOG.md)

## 独立性、许可证和商标

Frigate 名称仅用于说明兼容性。本项目是独立项目，与 Frigate 项目及其维护者不存在
隶属、赞助或官方背书关系。

Nanexus Event Intelligence 依据 [Apache License 2.0](./LICENSE)发布。第三方归属和
商标说明见 [NOTICE](./NOTICE)。安全漏洞请按 [SECURITY.md](./SECURITY.md)私密报告。
