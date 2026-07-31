import api from './index'

export const findingApi = {
  list: (params?: any) => api.get('/findings', { params }),
  get: (id: number) => api.get(`/findings/${id}`),
  update: (id: number, data: any) => api.put(`/findings/${id}`, data),
  assign: (id: number, data: any) => api.post(`/findings/${id}/assign`, data),
  close: (id: number, data: any) => api.post(`/findings/${id}/close`, data),
  evidence: (id: number) => api.get(`/findings/${id}/evidence`),
  events: (id: number) => api.get(`/findings/${id}/events`),
  remediations: (id: number) => api.get(`/findings/${id}/remediations`),
  createRemediation: (id: number, data: any) => api.post(`/findings/${id}/remediations`, data),
}
