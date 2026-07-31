import api from './index'

export const sdkApi = {
  list: (params?: any) => api.get('/sdks', { params }),
  get: (id: number) => api.get(`/sdks/${id}`),
  create: (data: any) => api.post('/sdks', data),
  update: (id: number, data: any) => api.put(`/sdks/${id}`, data),
  fingerprints: (id: number) => api.get(`/sdks/${id}/fingerprints`),
  addFingerprint: (id: number, data: any) => api.post(`/sdks/${id}/fingerprints`, data),
}
