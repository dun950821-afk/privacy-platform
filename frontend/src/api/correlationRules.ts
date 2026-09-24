import api from './index'

/** 受控词表：条件字段与操作符由后端校验器固定，前端只提供这些选项 */
export interface CorrelationRuleCondition {
  observation_type: string
  field: string
  operator: string
  value?: string
}

export interface CorrelationRuleContent {
  schema_version: string
  match: { logic: string; conditions: CorrelationRuleCondition[] }
  produce: {
    finding_code: string
    title: string
    category: string
    severity?: string
    confidence?: string
    recommendation?: string
  }
  standards: { masvs: string[]; maswe: string[]; mastg: string[]; cwe: string[] }
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
  would_match: boolean
  matched_observation_ids: number[]
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
