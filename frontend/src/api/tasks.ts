import api from './index'

export const taskApi = {
  list: (params?: any) => api.get('/tasks', { params }),
  get: (id: number) => api.get(`/tasks/${id}`),
  create: (data: any) => api.post('/tasks', data),
  submit: (id: number) => api.post(`/tasks/${id}/submit`),
  cancel: (id: number) => api.post(`/tasks/${id}/cancel`),
  retry: (id: number) => api.post(`/tasks/${id}/retry`),
  events: (id: number, params?: any) => api.get(`/tasks/${id}/events`, { params }),
  scenarios: (id: number) => api.get(`/tasks/${id}/scenarios`),
  updateScenario: (tid: number, sid: number, data: any) =>
    api.put(`/tasks/${tid}/scenarios/${sid}`, data),
  findings: (id: number) => api.get(`/tasks/${id}/findings`),
  platformFindings: (id: number) => api.get(`/tasks/${id}/platform-findings`),
  observations: (id: number, params?: any) => api.get(`/tasks/${id}/observations`, { params }),
  // 引擎为单条命中生成的报告（AppShark 的逐条 HTML）——后端解析成结构化代码后返回，
  // 不把引擎生成的 HTML 交给浏览器渲染（内容来自被检 APK，属不可信输入）
  engineReport: (id: number, observationId: number) =>
    api.get(`/tasks/${id}/observations/${observationId}/engine-report`),
  artifacts: (id: number) => api.get(`/tasks/${id}/artifacts`),
  evidence: (id: number, params?: any) => api.get(`/tasks/${id}/evidence`, { params }),
  reportOverview: (id: number) => api.get(`/tasks/${id}/report-overview`),
}
