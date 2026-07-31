import api from './index'

export const systemApi = {
  dashboard: () => api.get('/system/dashboard'),
  users: () => api.get('/system/users'),
  createUser: (data: any) => api.post('/system/users', data),
  updateUser: (id: number, data: any) => api.put(`/system/users/${id}`, data),
  deleteUser: (id: number) => api.delete(`/system/users/${id}`),
  nodes: () => api.get('/system/nodes'),
  devices: () => api.get('/system/devices'),
  auditLogs: (page = 1, pageSize = 50) =>
    api.get('/system/audit-logs', { params: { page, page_size: pageSize } }),
  dict: (dictType?: string) => api.get('/system/dict', { params: { dict_type: dictType } }),
}
