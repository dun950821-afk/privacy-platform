// 引擎管理API
import api from './index'

export const engineApi = {
  list: () => api.get('/engines'),
  types: () => api.get('/engines/types'),
  executions: (params?: any) => api.get('/engines/executions', { params }),
  getExecution: (id: number) => api.get(`/engines/executions/${id}`),
  stats: () => api.get('/engines/stats'),
  healthCheck: (engineType: string) => api.post(`/engines/${engineType}/health-check`),
  getConfig: (engineType: string) => api.get(`/engines/${engineType}/config`),
  retryExecution: (executionId: number) => api.post(`/engines/executions/${executionId}/retry`),
  saveConfig: (engineType: string, payload: any) => api.put(`/engines/${engineType}/config`, payload),
  resetConfig: (engineType: string) => api.post(`/engines/${engineType}/config/reset`),
}
