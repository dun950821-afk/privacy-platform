import api from './index'

export const reportApi = {
  generate: (taskId: number) => api.post(`/reports/${taskId}/generate`),
  get: (taskId: number) => api.get(`/reports/${taskId}`),
}
