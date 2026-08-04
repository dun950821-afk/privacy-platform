import axios from 'axios'
import type { AxiosError, AxiosRequestConfig } from 'axios'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'

declare module 'axios' {
  interface AxiosRequestConfig {
    /** 跳过全局错误提示 */
    silent?: boolean
    _retried?: boolean
  }
}

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const userStore = useUserStore()
  if (userStore.token) {
    config.headers.Authorization = `Bearer ${userStore.token}`
  }
  return config
})

/** 并发的 401 只触发一次刷新 */
let refreshing: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const userStore = useUserStore()
  if (!userStore.refreshToken) return false
  try {
    const resp = await axios.post('/api/v1/auth/refresh', {
      refresh_token: userStore.refreshToken,
    })
    if (resp.data?.code === 0 && resp.data.data?.access_token) {
      userStore.setToken(resp.data.data.access_token)
      return true
    }
  } catch {
    /* 刷新失败按未登录处理 */
  }
  return false
}

function toLogin() {
  const userStore = useUserStore()
  userStore.logout()
  window.location.href = '/login'
}

api.interceptors.response.use(
  (response) => {
    const data = response.data
    if (data?.code !== undefined && data.code !== 0) {
      if (!response.config.silent) {
        ElMessage.error(data.message || '请求失败')
      }
      return Promise.reject(data)
    }
    return data
  },
  async (error: AxiosError) => {
    const config = error.config as AxiosRequestConfig | undefined
    const url = config?.url || ''
    // 401: 尝试刷新 token 并重放原请求（登录/刷新接口本身除外）
    if (error.response?.status === 401 && config && !config._retried && !url.includes('/auth/')) {
      config._retried = true
      refreshing = refreshing ?? tryRefresh().finally(() => { refreshing = null })
      if (await refreshing) {
        return api(config)
      }
      toLogin()
      return Promise.reject(error)
    }
    if (error.response?.status === 401 && url.includes('/auth/refresh')) {
      toLogin()
      return Promise.reject(error)
    }
    const body = error.response?.data as any
    const msg = body?.detail || body?.message || '网络错误，请稍后重试'
    if (!config?.silent) {
      ElMessage.error(typeof msg === 'string' ? msg : '请求失败')
    }
    return Promise.reject(error)
  }
)

export default api
