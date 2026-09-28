import api from './index'

/** 受控词表：条件字段与操作符由后端校验器固定，前端只提供这些选项 */
export interface CorrelationRuleCondition {
  observation_type: string
  field: string
  operator: string
  value?: string
}

/** 2.0：按共享语义键连接的证据侧。规则内不出现具体数据类目名。 */
export interface CorrelationJoinItem {
  type: string
  on: string[]
  where?: Record<string, string | boolean | number>
}

/**
 * 两套 DSL 由 schema_version 区分：
 * - '1.0' 字面匹配：match + produce + standards
 * - '2.0' 共享键增强：anchor + where + join + scope + action
 */
export interface CorrelationRuleContent {
  schema_version: string
  match?: { logic: string; conditions: CorrelationRuleCondition[] }
  anchor?: { type: string }
  where?: Record<string, string | boolean | number>
  join?: CorrelationJoinItem[]
  scope?: string[]
  action?: string
  produce?: {
    finding_code: string
    title: string
    category: string
    severity?: string
    confidence?: string
    recommendation?: string
  }
  standards?: { masvs: string[]; maswe: string[]; mastg: string[]; cwe: string[] }
}

export interface CorrelationRuleVersion {
  id: number
  version: string
  status: string
  changelog: string | null
  created_at: string | null
}

export interface CorrelationRuleSummary {
  id: number
  rule_key: string
  name: string
  description: string | null
  status: string
  current_version_id: number | null
  current_version: string | null
  current_content: CorrelationRuleContent | null
  hit_count: number
  updated_at: string | null
}

export interface CorrelationRuleDetail extends CorrelationRuleSummary {
  versions: CorrelationRuleVersion[]
}

export interface CorrelationRulePreviewResult {
  rule_key: string
  /** create：命中后新建结论；enrich：只给已有结论补证据，不新建 */
  action?: string
  would_match: boolean
  matched_observation_ids: number[]
  evidence_observation_ids?: number[]
  finding_code: string | null
  existing_findings: string[]
  writes: boolean
}

export const correlationRuleApi = {
  list: () => api.get<any, { code: number; data: CorrelationRuleSummary[] }>('/correlation-rules'),
  get: (id: number) =>
    api.get<any, { code: number; data: CorrelationRuleDetail }>(`/correlation-rules/${id}`),
  create: (data: { rule_key: string; name: string; description?: string; content: CorrelationRuleContent }) =>
    api.post<any, { code: number; data: { id: number; version_id: number } }>('/correlation-rules', data),
  saveVersion: (id: number, data: { version: string; content: CorrelationRuleContent; changelog?: string }) =>
    api.put<any, { code: number; data: { id: number; version: string } }>(`/correlation-rules/${id}/versions`, data),
  publish: (id: number, vid: number) =>
    api.post<any, { code: number; data: { id: number; status: string } }>(
      `/correlation-rules/${id}/versions/${vid}/publish`),
  disable: (id: number) =>
    api.post<any, { code: number; data: { id: number; status: string } }>(`/correlation-rules/${id}/disable`),
  preview: (id: number, taskId: number) =>
    api.post<any, { code: number; data: CorrelationRulePreviewResult }>(
      `/correlation-rules/${id}/preview`, { task_id: taskId }),
}
