// 引擎管理API
import api from './index'

export const engineApi = {
  list: () => api.get('/engines'),
  types: () => api.get('/engines/types'),
  executions: (params?: any) => api.get('/engines/executions', { params }),
  getExecution: (id: number) => api.get(`/engines/executions/${id}`),
  stats: () => api.get('/engines/stats'),
  healthCheck: (engineType: string) => api.post(`/engines/${engineType}/health-check`),
}
