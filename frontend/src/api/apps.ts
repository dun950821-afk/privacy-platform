import api from './index'

export const appApi = {
  list: (params?: any) => api.get('/apps', { params }),
  get: (id: number) => api.get(`/apps/${id}`),
  create: (data: any) => api.post('/apps', data),
  update: (id: number, data: any) => api.put(`/apps/${id}`, data),
  delete: (id: number) => api.delete(`/apps/${id}`),
  versions: (id: number) => api.get(`/apps/${id}/versions`),
  getVersion: (id: number, vid: number) => api.get(`/apps/${id}/versions/${vid}`),
  uploadVersion: (id: number, formData: FormData) =>
    api.post(`/apps/${id}/versions/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }),
  quickUpload: (formData: FormData) =>
    api.post('/apps/quick-upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    }),
  policies: (id: number) => api.get(`/apps/${id}/privacy-policies`),
  getPolicy: (id: number, pid: number) => api.get(`/apps/${id}/privacy-policies/${pid}`),
  createPolicy: (id: number, data: any) => api.post(`/apps/${id}/privacy-policies`, data),
  sdks: (id: number) => api.get(`/apps/${id}/sdks`),
}
