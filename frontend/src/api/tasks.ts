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
  // 单条结论详情：含关联 observation（`observations[].id` 交给 EngineReportViewer）
  platformFinding: (id: number, fid: number) =>
    api.get(`/tasks/${id}/platform-findings/${fid}`, { silent: true }),
  // App 全部网络端点，按 host 聚合（含归属 attribution）
  endpoints: (id: number) => api.get(`/tasks/${id}/endpoints`, { silent: true }),
  // 「安全加固」块：MobSF 的 appsec / 清单问题 / 密钥 / 证书 / 依赖五段原始数据
  securityFindings: (id: number) => api.get(`/tasks/${id}/security-findings`, { silent: true }),
  // 复检记录：items=本任务的结论被复检，as_retest=本任务自己是复检任务（两个方向）
  retestRecords: (id: number) => api.get(`/tasks/${id}/retest-records`, { silent: true }),
  // 整改闭环字段：triage_status / assigned_to / due_date（只改这三个，非法值后端返 400）
  updateFindingStatus: (id: number, fid: number, data: any) =>
    api.put(`/tasks/${id}/platform-findings/${fid}/status`, data, { silent: true }),
  observations: (id: number, params?: any) => api.get(`/tasks/${id}/observations`, { params }),
  // 合规画像：各引擎结果按「收集主体 / 权限」归并后的统一视图
  complianceProfile: (id: number) => api.get(`/tasks/${id}/compliance-profile`),
  // 引擎为单条命中生成的报告（AppShark 的逐条 HTML）——后端解析成结构化代码后返回，
  // 不把引擎生成的 HTML 交给浏览器渲染（内容来自被检 APK，属不可信输入）
  engineReport: (id: number, observationId: number) =>
    api.get(`/tasks/${id}/observations/${observationId}/engine-report`),
  artifacts: (id: number) => api.get(`/tasks/${id}/artifacts`),
  evidence: (id: number, params?: any) => api.get(`/tasks/${id}/evidence`, { params }),
  reportOverview: (id: number) => api.get(`/tasks/${id}/report-overview`),
}
