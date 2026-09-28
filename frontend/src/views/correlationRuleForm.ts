/**
 * 关联规则编辑器的「表单 ⇄ 规则内容」映射。
 *
 * 单独成文件是因为这段映射最危险的地方不在界面，而在**保存**：表单是结构化重建，
 * 只认识自己那几个字段。一旦某种形态没被映射到，保存就会把它静默改写成另一种形态——
 * 规则看起来还在，实际已经失效。抽出来才能直接对真实规则内容跑往返校验。
 */
import type { CorrelationRuleContent, CorrelationJoinItem } from '../api/correlationRules'

/** 与后端 rule_evaluator 的长度上限保持一致（platform_findings 为定长列，超长会在写库时截断报错） */
export const MAX_FINDING_CODE_LEN = 64
export const MAX_TITLE_LEN = 200
export const MAX_CATEGORY_LEN = 60
export const MAX_RECOMMENDATION_LEN = 2000

/** 2.0 的 join 只支持这些连接键（与后端 ALLOWED_JOIN_KEYS 一致） */
export const JOIN_KEYS = ['data_category']
/** 2.0 的作用范围（与后端 ALLOWED_SCOPE_KEYS 一致） */
export const SCOPE_KEYS = ['app_version_id']

export interface ConditionForm {
  observation_type: string
  field: string
  operator: string
  value: string
}

/** where 与 join.where 都是「字段 = 值」的筛选，编辑器里统一成行 */
export interface WhereRow { key: string; value: string }
export interface JoinForm { type: string; on: string[]; where: WhereRow[] }

export type RuleMode = 'match' | 'join'

export interface RuleForm {
  mode: RuleMode
  logic: string
  conditions: ConditionForm[]
  anchorType: string
  anchorWhere: WhereRow[]
  joins: JoinForm[]
  action: string
  produce: {
    finding_code: string
    title: string
    category: string
    severity: string
    confidence: string
    recommendation: string
  }
  standards: { masvs: string[]; maswe: string[]; mastg: string[]; cwe: string[] }
}

export function emptyCondition(): ConditionForm {
  return { observation_type: '', field: 'subject', operator: 'equals', value: '' }
}

export function emptyJoin(): JoinForm {
  return { type: '', on: [...JOIN_KEYS], where: [] }
}

export function emptyForm(): RuleForm {
  return {
    mode: 'match',
    logic: 'all',
    conditions: [emptyCondition()],
    anchorType: '',
    anchorWhere: [],
    joins: [emptyJoin()],
    action: 'enrich',
    produce: {
      finding_code: '', title: '', category: 'privacy',
      severity: 'medium', confidence: 'possible', recommendation: '',
    },
    standards: { masvs: [], maswe: [], mastg: [], cwe: [] },
  }
}

/** where 对象 ⇄ 编辑行；空键的行丢弃（否则会保存出 "" 这个非法字段名） */
export function whereToRows(where: Record<string, unknown> | undefined): WhereRow[] {
  return Object.entries(where || {}).map(([key, value]) => ({ key, value: String(value) }))
}

export function rowsToWhere(rows: WhereRow[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const row of rows) {
    const key = row.key.trim()
    if (key) out[key] = row.value
  }
  return out
}

export function parseContent(content: CorrelationRuleContent | null | undefined): RuleForm {
  const next = emptyForm()
  if (!content) return next
  if (content.schema_version === '2.0') {
    // 2.0 的形态：anchor / where / join / action，没有 produce 与 standards
    next.mode = 'join'
    next.anchorType = content.anchor?.type ?? ''
    next.anchorWhere = whereToRows(content.where)
    next.joins = (content.join || []).map(item => ({
      type: item.type ?? '',
      on: [...(item.on || [])],
      where: whereToRows(item.where),
    }))
    next.action = content.action ?? 'enrich'
    return next
  }
  const match = (content.match ?? {}) as NonNullable<CorrelationRuleContent['match']>
  next.logic = match.logic === 'any' ? 'any' : 'all'
  next.conditions = (match.conditions || []).map(c => ({
    observation_type: c.observation_type ?? '',
    // 词表外的字段原样保留，避免保存时静默改写存量规则
    field: c.field ?? 'subject',
    operator: c.operator ?? 'equals',
    value: c.value == null ? '' : String(c.value),
  }))
  const produce = (content.produce ?? {}) as NonNullable<CorrelationRuleContent['produce']>
  next.produce = {
    finding_code: produce.finding_code ?? '',
    title: produce.title ?? '',
    category: produce.category ?? '',
    severity: produce.severity ?? 'medium',
    confidence: produce.confidence ?? 'possible',
    recommendation: produce.recommendation ?? '',
  }
  const standards = (content.standards ?? {}) as NonNullable<CorrelationRuleContent['standards']>
  next.standards = {
    masvs: [...(standards.masvs || [])],
    maswe: [...(standards.maswe || [])],
    mastg: [...(standards.mastg || [])],
    cwe: [...(standards.cwe || [])],
  }
  return next
}

export function buildContent(f: RuleForm): CorrelationRuleContent {
  if (f.mode === 'join') {
    const join: CorrelationJoinItem[] = f.joins.map(item => {
      const where = rowsToWhere(item.where)
      return {
        type: item.type.trim(),
        on: [...item.on],
        ...(Object.keys(where).length ? { where } : {}),
      }
    })
    const where = rowsToWhere(f.anchorWhere)
    return {
      schema_version: '2.0',
      anchor: { type: f.anchorType.trim() },
      ...(Object.keys(where).length ? { where } : {}),
      join,
      scope: [...SCOPE_KEYS],
      action: f.action,
    }
  }
  return {
    schema_version: '1.0',
    match: {
      logic: f.logic,
      conditions: f.conditions.map(c => ({
        observation_type: c.observation_type.trim(),
        field: c.field,
        operator: c.operator,
        value: c.operator === 'exists' ? '' : String(c.value ?? ''),
      })),
    },
    produce: {
      finding_code: f.produce.finding_code.trim(),
      title: f.produce.title.trim(),
      category: f.produce.category.trim(),
      severity: f.produce.severity,
      confidence: f.produce.confidence,
      recommendation: f.produce.recommendation,
    },
    standards: {
      masvs: [...f.standards.masvs],
      maswe: [...f.standards.maswe],
      mastg: [...f.standards.mastg],
      cwe: [...f.standards.cwe],
    },
  }
}

export interface ModeRules { severity: string[]; confidence: string[] }

/** 保存前的本地校验，与后端校验器保持同一套约束 */
export function validateForm(f: RuleForm): string | null {
  if (f.mode === 'join') {
    if (!f.anchorType.trim()) return '请填写锚点观察类型'
    if (!f.joins.length) return '至少需要一个连接'
    for (let i = 0; i < f.joins.length; i++) {
      const j = f.joins[i]
      if (!j.type.trim()) return `第 ${i + 1} 个连接缺少证据观察类型`
      if (!j.on.length) return `第 ${i + 1} 个连接至少要选一个连接键`
    }
    if (f.action !== 'enrich') return '当前仅支持 enrich（证据增强）'
    return null
  }
  if (!f.conditions.length) return '至少需要一个匹配条件'
  for (let i = 0; i < f.conditions.length; i++) {
    const c = f.conditions[i]
    if (!c.observation_type.trim()) return `第 ${i + 1} 个条件缺少观察类型`
    if (!c.field) return `第 ${i + 1} 个条件缺少字段`
    if (!c.operator) return `第 ${i + 1} 个条件缺少操作符`
    if (c.operator !== 'exists' && !String(c.value ?? '').trim()) return `第 ${i + 1} 个条件缺少匹配值`
  }
  const p = f.produce
  const code = p.finding_code.trim()
  if (!/^[A-Z][A-Z0-9_]{2,}$/.test(code)) {
    return '问题编号需以大写字母开头，由大写字母/数字/下划线组成（至少 3 位）'
  }
  if (code.length > MAX_FINDING_CODE_LEN) return `问题编号最长 ${MAX_FINDING_CODE_LEN} 个字符`
  if (!p.title.trim()) return '请填写产出标题'
  if (p.title.length > MAX_TITLE_LEN) return `产出标题最长 ${MAX_TITLE_LEN} 个字符`
  if (!p.category.trim()) return '请填写产出类别'
  if (p.category.length > MAX_CATEGORY_LEN) return `产出类别最长 ${MAX_CATEGORY_LEN} 个字符`
  if (p.recommendation.length > MAX_RECOMMENDATION_LEN) return `整改建议最长 ${MAX_RECOMMENDATION_LEN} 个字符`
  return null
}
