/** 统一请求封装：拼后端地址、带上当前操作人、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const USER_STORAGE_KEY = 'om.currentUserId'

export function currentUserId(): string {
  return localStorage.getItem(USER_STORAGE_KEY) ?? 'u0'
}

export function setCurrentUserId(id: string) {
  localStorage.setItem(USER_STORAGE_KEY, id)
}

function authHeaders(init?: RequestInit): HeadersInit {
  return { 'Content-Type': 'application/json', 'X-User-Id': currentUserId(), ...(init?.headers ?? {}) }
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: authHeaders(init),
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
