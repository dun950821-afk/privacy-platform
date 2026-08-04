import api from './index'

export interface AppsharkRuleSummary {
  key: string
  name: string
  mode: string
  detail: string
  category: string
  category_detail: string
  level: string
  source_count: number
  sink_count: number
}

export interface AppsharkRuleFile {
  filename: string
  enabled: boolean
  rule_count: number
  rules: AppsharkRuleSummary[]
  parse_error?: string
}

export const appsharkRuleApi = {
  list: () => api.get<any, { code: number; data: AppsharkRuleFile[] }>('/appshark-rules'),
  get: (filename: string) =>
    api.get<any, { code: number; data: { filename: string; enabled: boolean; content: any } }>(
      `/appshark-rules/${filename}`),
  create: (data: { filename: string; content: any }) => api.post('/appshark-rules', data),
  update: (filename: string, content: any) =>
    api.put(`/appshark-rules/${filename}`, { filename, content }),
  remove: (filename: string) => api.delete(`/appshark-rules/${filename}`),
  toggle: (filename: string) => api.post(`/appshark-rules/${filename}/toggle`),
}
