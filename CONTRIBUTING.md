# Contributing to Nanexus Event Intelligence

Contributions that improve reliability, compatibility, documentation and the
Community experience are welcome. This guide explains how to report a problem,
propose an improvement and prepare a focused pull request.

## Before opening an issue

1. Search existing issues to avoid duplicates.
2. Confirm the behavior still occurs on the latest Community version.
3. Remove credentials, private addresses, camera names, event IDs, media and
   personal data from every description, log and attachment.
4. Choose the matching form:
   - **Bug report** for reproducible incorrect behavior;
   - **Feature request** for a user problem or proposed capability;
   - **Documentation issue** for unclear, missing or incorrect documentation.

Do not open a public issue for a suspected vulnerability. Follow
[SECURITY.md](./SECURITY.md) and report it privately to the listed security
contact.

## Reporting a bug

Use the Bug Report form and include:

- the Nanexus version or commit;
- operating system, architecture and container/runtime versions;
- the affected component;
- minimal, repeatable steps;
- expected and actual behavior;
- sanitized logs or screenshots only when they are necessary.

A useful report lets another contributor reproduce the problem without access to
your cameras, network or private configuration.

## Proposing a feature

Describe the user problem before describing a solution. Explain who benefits,
the current workaround, the smallest useful outcome and any privacy, security or
compatibility impact.

Features should preserve the public architecture boundaries: source-specific
protocols stay in their Adapter, core behavior consumes canonical contracts, and
Community remains useful without a private service or package.

## Documentation improvements

Documentation-only pull requests are welcome. When reporting a documentation
problem, link the affected page or section, explain what was confusing and
suggest corrected wording when possible. The English and Chinese public README
must remain equivalent.

## Preparing a pull request

1. Fork the Community repository and create a focused branch.
2. Keep unrelated refactoring out of the change.
3. Add or update tests for behavior changes.
4. Update public contracts and documentation when behavior or configuration changes.
5. Run the required checks from the repository root:

```bash
make install
make check
make community-tree-check
```

6. In the pull request, explain the problem, approach, verification and any known
   limitation or follow-up.

Submitting a pull request does not guarantee acceptance or merging. Maintainers
may accept, request changes, defer or close a contribution based on project
direction, public scope, architectural consistency, security, quality,
maintenance cost and release planning.

Accepted contributions retain their authorship and original contribution reference.

## Privacy and test data

Never submit real camera media, unredacted event payloads, credentials, tokens,
private hostnames or addresses, personal information, faces or license plates.
Use synthetic data or a reviewed redacted fixture. If safe reproduction is not
possible, describe the structure and behavior without uploading the source data.

## Code and language conventions

Keep source comments, docstrings, identifiers and operational log templates in
English. Put user-visible UI text in the localization catalogs. Preserve user and
upstream data exactly as received; localization must not rewrite persisted audit
history.

## Contribution license

By contributing, you represent that you have the right to submit the work and
agree that your contribution is provided under the project's
[Apache License 2.0](./LICENSE).

## Community conduct

Be respectful, specific and constructive. Discuss the technical work rather than
the person. Assume good intent, welcome clarification and avoid publishing
someone else's private data. Maintainers may close abusive, unsafe, duplicate or
out-of-scope submissions.

---

# 参与 Nanexus Event Intelligence

欢迎改进可靠性、兼容性、文档和 Community 使用体验的贡献。本指南说明如何报告问题、
提出改进建议和准备范围清晰的 Pull Request。

## 创建 Issue 之前

1. 搜索已有 Issue，避免重复提交；
2. 确认问题在最新 Community 版本中仍然存在；
3. 从描述、日志和附件中删除凭据、私有地址、摄像头名称、事件 ID、媒体及个人数据；
4. 选择对应表单：
   - **Bug Report**：可重复的错误行为；
   - **Feature Request**：用户问题或新能力建议；
   - **Documentation Issue**：缺失、错误或不清楚的文档。

疑似安全漏洞不得创建公开 Issue。请按照 [SECURITY.md](./SECURITY.md)中的方式，向
列出的安全联系人私密报告。

## 报告 Bug

使用 Bug Report 表单并提供：

- Nanexus 版本或 commit；
- 操作系统、CPU 架构和容器/运行时版本；
- 受影响组件；
- 最小且可以重复的操作步骤；
- 预期行为与实际行为；
- 只有确有必要时才提供经过脱敏的日志或截图。

高质量报告应当让其他贡献者无需访问你的摄像头、网络或私有配置即可复现问题。

## 提出功能建议

先说明用户遇到的问题，再说明建议的解决方案。请描述受益人、当前替代办法、最小可用
结果，以及隐私、安全和兼容性影响。

功能建议应保持公共架构边界：来源专有协议停留在 Adapter 内，核心只使用 Canonical
Contract，Community 不依赖私有服务或包也能独立提供价值。

## 改进文档

欢迎仅修改文档的 Pull Request。报告文档问题时，请链接具体页面或章节，说明哪里容易
误解，并尽可能提供建议措辞。英文和中文公共 README 必须保持含义一致。

## 准备 Pull Request

1. Fork Community 仓库并创建范围清晰的分支；
2. 不要混入无关重构；
3. 行为变化需要新增或更新测试；
4. 行为或配置变化需要同步更新公共契约和文档；
5. 在仓库根目录运行：

```bash
make install
make check
make community-tree-check
```

6. 在 Pull Request 中说明问题、实现方式、验证结果、已知限制和后续事项。

提交 Pull Request 不代表项目必须接受或合并该贡献。维护者将根据项目方向、公共范围、
架构一致性、安全性、质量、维护成本和发布计划，决定接受、要求修改、暂缓或关闭贡献。

被接受的贡献会保留作者归属和原始贡献引用。

## 隐私和测试数据

禁止提交真实摄像头媒体、未脱敏事件 payload、凭据、token、私有主机名或地址、个人
信息、人脸或车牌。请使用合成数据或经过审核的脱敏 fixture。如果无法安全提供复现
数据，应只描述结构和行为，不上传原始内容。

## 代码和语言约定

源码注释、docstring、标识符和运维日志模板使用英文；用户可见 UI 文案进入本地化资源；
用户及上游数据保持原样，本地化不得改写已持久化的审计历史。

## 贡献许可证

提交贡献即表示你有权提供相关内容，并同意贡献按照项目的
[Apache License 2.0](./LICENSE)提供。

## 社区交流

交流应保持尊重、具体和建设性，讨论技术工作而不是针对个人。优先善意理解，欢迎澄清，
不得公开他人的私有数据。维护者可以关闭攻击性、不安全、重复或超出范围的提交。
