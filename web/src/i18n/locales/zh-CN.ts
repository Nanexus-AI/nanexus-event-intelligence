const zhCN = {
  app: { title: '事件检查台', summary: '从 Canonical Event 到人工反馈，每个判断都保留来源与证据。' },
  language: { label: '语言', english: 'English', chinese: '简体中文' },
  backend: { online: '后端在线', offline: '后端离线' },
  filters: { ariaLabel: '事件筛选', type: '类型', all: '全部', originalObject: '原始 Object', label: '标签' },
  status: { eventCount_one: '{{count}} 条事件', eventCount_other: '{{count}} 条事件', refreshed: '{{time}} 刷新', connecting: '正在连接' },
  list: { ariaLabel: '事件列表', empty: '暂无符合条件的事件', partialHistory: '历史不完整', annotated: '已标注', noZone: '无区域', observationCount_one: '{{count}} 次状态', observationCount_other: '{{count}} 次状态' },
  detail: { ariaLabel: '事件详情', empty: '选择一个事件查看详情', lifecycle: '生命周期', duration: '持续 {{value}}', relatedObjects: '关联对象', source: '来源', externalId: '外部 ID', internalId: '内部 ID', rule: '规则', objectsAndEvidence: '对象与证据', objects: '对象 {{count}}', evidence: '证据 {{count}}', canonicalData: 'Canonical 数据', rawData: '原始来源数据', rawUnavailable: '原始消息不可用' },
  feedback: { question: '这条事件是否有价值？', important: '重要', notImportant: '不重要', falsePositive: '误报', uncertain: '不确定' },
  outcome: { send: '建议发送', escalate: '建议升级提醒', suppress: '建议抑制', no_action: '建议不处理', enrich: '建议补充分析', hold: '建议暂缓' },
  timeline: { appeared: '目标 {{id}} 出现', disappeared: '目标 {{id}} 消失', enteredZone: '进入区域：{{zones}}', updated: '状态更新' },
  duration: { seconds: '{{seconds}} 秒', minutesSeconds: '{{minutes}} 分 {{seconds}} 秒' },
  snapshot: { unavailable: '暂时无法加载快照', missing: '该事件没有快照', generating: '快照正在生成，请稍后重试', expired: '快照已过期或被删除', frigateUnavailable: '暂时无法连接 Frigate', alt: '事件现场快照', loading: '正在加载快照…', reload: '重新加载快照' },
  errors: { load: '加载失败', save: '保存失败' },
  decision: { heading: '规则建议 · 影子评估', explanation: '这是一条规则建议，用于和人工标注对照评估；它本身不代表通知已经发送。', hasNotification: '本事件已有实际通知记录，详情见下方', noNotification: '本事件没有实际通知记录；通知功能需由部署者显式启用', trace: '查看规则判断过程', notificationRecords: '实际通知记录', attempts_one: '尝试 {{count}} 次', attempts_other: '尝试 {{count}} 次' },
} as const
export default zhCN
