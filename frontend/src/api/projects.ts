import api from './index'

export const projectApi = {
  list: (page = 1, pageSize = 20) =>
    api.get('/projects', { params: { page, page_size: pageSize } }),
  get: (id: number) => api.get(`/projects/${id}`),
  create: (data: any) => api.post('/projects', data),
  update: (id: number, data: any) => api.put(`/projects/${id}`, data),
  delete: (id: number) => api.delete(`/projects/${id}`),
  members: (id: number) => api.get(`/projects/${id}/members`),
  addMember: (id: number, data: any) => api.post(`/projects/${id}/members`, data),
  removeMember: (id: number, uid: number) => api.delete(`/projects/${id}/members/${uid}`),
  dashboard: (id: number) => api.get(`/projects/${id}/dashboard`),
}
