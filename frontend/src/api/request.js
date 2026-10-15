import axios from 'axios'
import { clearToken, getToken } from '../utils/authToken'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 15000,
})

request.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Token ${token}`
  }
  return config
})

request.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const path = window.location.pathname
    const isAuthRequest = String(error?.config?.url || '').includes('/auth/')
    if ((status === 401 || status === 403) && !isAuthRequest) {
      clearToken()
      if (path !== '/login') {
        const redirect = encodeURIComponent(`${path}${window.location.search}`)
        window.location.href = `/login?redirect=${redirect}`
      }
    }
    return Promise.reject(error)
  },
)

export default request
