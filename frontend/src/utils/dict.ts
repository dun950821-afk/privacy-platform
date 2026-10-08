/** 全局枚举字典：中文 label + el-tag 类型，所有页面统一使用 */

export type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

export interface DictItem {
  label: string
  type: TagType
}

type Dict = Record<string, DictItem>

/** 大小写不敏感查找 */
export function dictItem(map: Dict, value?: string | null): DictItem {
  if (!value) return { label: '-', type: 'info' }
  const hit = map[value] ?? map[value.toLowerCase()] ?? map[value.toUpperCase()]
  return hit ?? { label: value, type: 'info' }
}

export function dictLabel(map: Dict, value?: string | null): string {
  return dictItem(map, value).label
}

/** 检测任务状态 */
export const TASK_STATUS: Dict = {
  draft: { label: '草稿', type: 'info' },
  queued: { label: '排队中', type: 'info' },
  running_static: { label: '静态检测中', type: 'primary' },
  waiting_dynamic: { label: '等待动态检测', type: 'warning' },
  running_dynamic: { label: '动态检测中', type: 'primary' },
  analyzing: { label: '分析中', type: 'primary' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  canceled: { label: '已取消', type: 'info' },
}

/**
 * 分析有效性：正交于任务状态。
 * status 回答「引擎跑完了吗」，这里回答「结果算不算数」。UNKNOWN 表示无法判定，
 * **不得**显示成「已覆盖」——缺数据不等于没问题。
 */
export const ANALYSIS_COVERAGE: Dict = {
  FULL: { label: '分析有效', type: 'success' },
  DEGRADED: { label: '分析未覆盖应用代码', type: 'danger' },
  UNKNOWN: { label: '分析有效性未判定', type: 'info' },
}

/** 子任务 / 引擎执行 / 场景 状态 */
export const EXEC_STATUS: Dict = {
  pending: { label: '待执行', type: 'info' },
  prepare: { label: '准备中', type: 'info' },
  running: { label: '运行中', type: 'primary' },
  completed: { label: '已完成', type: 'success' },
  success: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  canceled: { label: '已取消', type: 'info' },
  skipped: { label: '已跳过', type: 'info' },
}

/** 问题严重度 */
export const SEVERITY: Dict = {
  critical: { label: '严重', type: 'danger' },
  high: { label: '高危', type: 'danger' },
  medium: { label: '中危', type: 'warning' },
  low: { label: '低危', type: 'info' },
}

/**
 * 结论整改状态（platform_findings.triage_status）。
 * 取值与后端校验白名单逐字一致（`tasks.py: FINDING_TRIAGE_STATUSES`）——
 * 这是新的四态词表，与上面 FINDING_STATUS 的旧词表是两回事，别混用。
 */
export const TRIAGE_STATUS: Dict = {
  // 词面与后端模型注释同源（`models/__init__.py`：needs_review（待审阅）），
  // 也与 task-8 简报 §三 的「待审阅 / 整改中 / 已修复 / 已忽略」逐字一致。
  needs_review: { label: '待审阅', type: 'warning' },
  fixing: { label: '整改中', type: 'primary' },
  fixed: { label: '已修复', type: 'success' },
  ignored: { label: '已忽略', type: 'info' },
}

/** 问题状态 */
export const FINDING_STATUS: Dict = {
  open: { label: '待处理', type: 'danger' },
  assigned: { label: '已分派', type: 'warning' },
  fixing: { label: '整改中', type: 'warning' },
  pending_retest: { label: '待复测', type: 'primary' },
  retest: { label: '复测中', type: 'primary' },
  closed: { label: '已关闭', type: 'success' },
  ignored: { label: '已忽略', type: 'info' },
}

/** 问题置信度：由证据来源数量与独立性决定（设计文档 §8） */
export const CONFIDENCE: Dict = {
  high: { label: '高', type: 'danger' },
  medium_high: { label: '中高', type: 'warning' },
  medium: { label: '中', type: 'info' },
  // 历史取值：v1 关联规则产出的结论（如 Finding #45 / #53）仍是这套词表，
  // 保留映射以免历史结论在界面显示成原始英文
  confirmed: { label: '已确认', type: 'danger' },
  probable: { label: '大概率', type: 'warning' },
  possible: { label: '疑似', type: 'info' },
}

/** 组件类型 */
export const COMPONENT_KIND: Dict = {
  SDK: { label: 'SDK', type: 'primary' },
  OPEN_SOURCE_LIBRARY: { label: '开源库', type: 'info' },
  FRAMEWORK: { label: '框架', type: 'info' },
  SYSTEM_COMPONENT: { label: '系统组件', type: 'info' },
  VENDOR_COMPONENT: { label: '厂商组件', type: 'warning' },
  APP_MODULE: { label: '应用模块', type: 'info' },
  TOOLING: { label: '工具', type: 'info' },
  UNKNOWN: { label: '未知', type: 'info' },
}

/** 敏感度 */
export const SENSITIVITY: Dict = {
  LOW: { label: '低', type: 'success' },
  MEDIUM: { label: '中', type: 'warning' },
  HIGH: { label: '高', type: 'danger' },
  CRITICAL: { label: '极高', type: 'danger' },
  UNKNOWN: { label: '未知', type: 'info' },
}

/** 核验状态 */
export const VERIFICATION_STATUS: Dict = {
  VERIFIED: { label: '已核验', type: 'success' },
  PARTIAL: { label: '部分核验', type: 'warning' },
  UNVERIFIED: { label: '未核验', type: 'info' },
  PENDING: { label: '待核验', type: 'info' },
  PENDING_VENDOR_CONFIRM: { label: '待厂商确认', type: 'warning' },
}

/** 命中状态 */
export const HIT_STATUS: Dict = {
  CONFIRMED: { label: '确认命中', type: 'success' },
  PROBABLE: { label: '大概率', type: 'warning' },
  CANDIDATE: { label: '候选', type: 'info' },
  REJECTED: { label: '已排除', type: 'info' },
  WHITELISTED: { label: '白名单', type: 'success' },
}

/** 权限风险等级 */
export const RISK_LEVEL: Dict = {
  LOW: { label: '低', type: 'info' },
  MEDIUM: { label: '中', type: 'warning' },
  HIGH: { label: '高', type: 'danger' },
  CRITICAL: { label: '严重', type: 'danger' },
}

/**
 * 权限类型配色。
 * 取值本身由后端 `/permissions/meta` 给出（受控词表），这里只负责颜色；
 * dictItem 对未收录的值会回退成原文 + info，后端加了新类型也不会渲染崩。
 */
export const PERMISSION_TYPE: Dict = {
  '危险权限': { label: '危险权限', type: 'danger' },
  '危险权限（受限）': { label: '危险权限（受限）', type: 'danger' },
  '普通权限': { label: '普通权限', type: 'info' },
  '签名权限': { label: '签名权限', type: 'warning' },
  '特殊权限': { label: '特殊权限', type: 'warning' },
  // 主级别 signature、但带 appop 标志的（SYSTEM_ALERT_WINDOW / WRITE_SETTINGS 等）：
  // 普通 App 能在系统设置页申请到，所以它不在「不可达」那一档（见 permission_taxonomy）。
  // 配色跟随 `特殊权限`，区别由 label 承载。
  '特殊权限（AppOps 可授权）': { label: '特殊权限（AppOps 可授权）', type: 'warning' },
  '已弃用权限': { label: '已弃用权限', type: 'info' },
  '三方声明权限': { label: '三方声明权限', type: 'primary' },
  '未标注': { label: '未标注', type: 'info' },
}

/** 场景类型 */
export const SCENARIO_TYPE: Dict = {
  first_launch: { label: '首次启动(同意前)', type: 'primary' },
  rejected: { label: '拒绝授权', type: 'warning' },
  consented: { label: '同意授权后', type: 'success' },
  function_trigger: { label: '功能触发', type: 'primary' },
  revoked: { label: '撤回同意', type: 'warning' },
  account_cancel: { label: '账号注销', type: 'info' },
}

/** 同意状态 */
export const CONSENT_STATUS: Dict = {
  NOT_PRESENTED: { label: '未展示', type: 'info' },
  NOT_AGREED: { label: '未同意', type: 'warning' },
  REJECTED: { label: '已拒绝', type: 'danger' },
  CONSENTED: { label: '已同意', type: 'success' },
  REVOKED: { label: '已撤回', type: 'warning' },
}

/** 事件类型 */
export const EVENT_TYPE: Dict = {
  sensitive_api_call: { label: '敏感API调用', type: 'danger' },
  network_request: { label: '网络请求', type: 'primary' },
  permission_request: { label: '权限请求', type: 'warning' },
  page_view: { label: '页面浏览', type: 'info' },
  static_data_flow: { label: '静态数据流', type: 'primary' },
  static_sensitive_api: { label: '静态敏感API', type: 'warning' },
  consent_state_change: { label: '同意状态变更', type: 'warning' },
  sdk_init: { label: 'SDK初始化', type: 'primary' },
  static_basic_info: { label: '基础信息', type: 'info' },
  static_permission: { label: '声明权限', type: 'primary' },
  static_sensitive_permission: { label: '敏感权限', type: 'danger' },
  static_component: { label: '应用组件', type: 'primary' },
}

/** 检测类型 */
export const DETECTION_TYPE: Dict = {
  full: { label: '完整检测', type: 'primary' },
  static_only: { label: '仅静态检测', type: 'info' },
  consent_pre: { label: '同意前专项', type: 'warning' },
  sdk_audit: { label: 'SDK审计', type: 'primary' },
  version_diff: { label: '版本对比', type: 'info' },
}

/** 用户角色 */
export const USER_ROLE: Dict = {
  platform_admin: { label: '平台管理员', type: 'danger' },
  project_admin: { label: '项目管理员', type: 'primary' },
  tester: { label: '测试工程师', type: 'primary' },
  developer: { label: '开发工程师', type: 'info' },
  auditor: { label: '审计员', type: 'warning' },
  viewer: { label: '只读用户', type: 'info' },
}

/** 用户状态 */
export const USER_STATUS: Dict = {
  active: { label: '启用', type: 'success' },
  disabled: { label: '禁用', type: 'danger' },
  locked: { label: '锁定', type: 'warning' },
}

/** 节点/设备状态 */
export const NODE_STATUS: Dict = {
  online: { label: '在线', type: 'success' },
  offline: { label: '离线', type: 'info' },
  busy: { label: '忙碌', type: 'warning' },
  idle: { label: '空闲', type: 'success' },
  error: { label: '异常', type: 'danger' },
}

/** 规则状态 */
export const RULE_STATUS: Dict = {
  active: { label: '启用', type: 'success' },
  disabled: { label: '停用', type: 'info' },
  draft: { label: '草稿', type: 'warning' },
  published: { label: '已发布', type: 'success' },
  archived: { label: '已归档', type: 'info' },
}

/** 规则分类 */
export const RULE_CATEGORY: Dict = {
  consent: { label: '同意管理', type: 'primary' },
  sdk: { label: '第三方SDK', type: 'primary' },
  permission: { label: '权限合规', type: 'warning' },
  network: { label: '网络传输', type: 'primary' },
  policy: { label: '隐私政策', type: 'info' },
  right: { label: '用户权利', type: 'info' },
  security: { label: '安全加固', type: 'warning' },
  account: { label: '账号管理', type: 'info' },
}

/** 通用是/否 */
export const BOOL_TAG: Dict = {
  true: { label: '是', type: 'success' },
  false: { label: '否', type: 'info' },
}

/** 权限所属平台 */
export const PLATFORM: Dict = {
  ANDROID: { label: 'Android', type: 'success' },
  IOS: { label: 'iOS', type: 'primary' },
  HARMONYOS: { label: '鸿蒙', type: 'warning' },
}
