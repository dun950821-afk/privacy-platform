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
  evidence: (id: number, params?: any) => api.get(`/tasks/${id}/evidence`, { params }),
  reportOverview: (id: number) => api.get(`/tasks/${id}/report-overview`),
}
