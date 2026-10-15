import { reactive } from 'vue'
import { loginApi, logoutApi, meApi } from '../api/auth'
import { clearToken, getToken, setToken } from '../utils/authToken'

export const authState = reactive({
  checked: false,
  authenticated: false,
  user: null,
})

export async function ensureAuth(force = false) {
  if (authState.checked && !force) return authState.authenticated
  if (!getToken()) {
    authState.checked = true
    authState.authenticated = false
    authState.user = null
    return false
  }
  try {
    const resp = await meApi()
    authState.checked = true
    authState.authenticated = Boolean(resp.data.authenticated)
    authState.user = resp.data.user || null
    if (!authState.authenticated) clearToken()
    return authState.authenticated
  } catch {
    clearAuthState()
    authState.checked = true
    return false
  }
}

export async function login(username, password) {
  const resp = await loginApi({ username, password })
  if (!resp.data.success) {
    throw new Error(resp.data.message || '登录失败')
  }
  setToken(resp.data.token)
  authState.checked = true
  authState.authenticated = true
  authState.user = resp.data.user
  return resp.data.user
}

export async function logout() {
  try {
    await logoutApi()
  } catch {
    // Token may already be expired; local cleanup is still required.
  }
  clearAuthState()
}

export function clearAuthState() {
  clearToken()
  authState.authenticated = false
  authState.user = null
}
