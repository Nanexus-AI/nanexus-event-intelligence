# Frigate 0.17 fixtures

## English

The Community release includes the `vehicle-lifecycle` fixture: synthetic test
events matching the Frigate 0.17 message format. Its values, identifiers, camera
name, zones and media path are synthetic.

Only `messages.jsonl` and `metadata.json` are included. There are no camera
images, thumbnails, clips, video or other media files. Fields such as
`has_snapshot`, `has_clip` and the `synthetic.webp` path simulate message
structure and do not reference published or remotely accessible media.

Never add Frigate configuration, MQTT credentials, camera URLs, identifiable
media or unreviewed raw payloads to a Community fixture.

## 中文

Community 版本包含 `vehicle-lifecycle` fixture：一组符合 Frigate 0.17 消息格式的合成
测试事件。其数值、标识符、摄像机名称、区域和媒体路径均为合成内容。

发布内容只有 `messages.jsonl` 和 `metadata.json`，不包含摄像机截图、缩略图、clip、
视频或其他媒体文件。`has_snapshot`、`has_clip` 和 `synthetic.webp` 路径只用于模拟
消息结构，不指向随项目发布或可远程访问的媒体。

不要向 Community fixture 添加 Frigate 配置、MQTT 凭据、摄像机 URL、可识别身份的媒体
或未经审查的原始 payload。
