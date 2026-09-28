import api from './index'

export const permissionApi = {
  list: (params?: any) => api.get('/permissions', { params }),
  meta: () => api.get('/permissions/meta'),
  get: (id: number) => api.get(`/permissions/${id}`),
  create: (data: any) => api.post('/permissions', data),
  update: (id: number, data: any) => api.put(`/permissions/${id}`, data),
  remove: (id: number) => api.delete(`/permissions/${id}`),
}
