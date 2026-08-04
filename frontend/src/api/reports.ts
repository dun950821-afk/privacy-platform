import api from './index'

export const reportApi = {
  list: (page = 1, pageSize = 20) =>
    api.get('/reports', { params: { page, page_size: pageSize } }),
  generate: (taskId: number) => api.post(`/reports/${taskId}/generate`),
  get: (taskId: number) => api.get(`/reports/${taskId}`),
  /** 文件流下载 */
  download: (taskId: number) =>
    api.get(`/reports/${taskId}/download`, { responseType: 'blob' }),
}
