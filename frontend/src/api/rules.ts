import api from './index'

export const ruleApi = {
  list: (params?: any) => api.get('/rules', { params }),
  get: (id: number) => api.get(`/rules/${id}`),
  create: (data: any) => api.post('/rules', data),
  createVersion: (id: number, data: any) => api.post(`/rules/${id}/versions`, data),
  publishVersion: (rid: number, vid: number) =>
    api.post(`/rules/${rid}/versions/${vid}/publish`),
}
