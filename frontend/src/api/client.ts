/** 统一请求封装：拼后端地址、带当前操作员身份、抛网络错误、给页脚留一句可读的说明。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

function identityHeaders(): Record<string, string> {
  // 齿轮箱按班组鉴权依赖这三个头；store 在 client 被实际调用时早已挂载。
  const session = useSessionStore()
  return {
    'X-Operator-Role': session.role,
    'X-Operator-Team': session.teamCode,
    // HTTP 头只能是 ASCII，姓名做百分号编码，后端 unquote 还原。
    'X-Operator-Name': encodeURIComponent(session.operator),
  }
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...identityHeaders(), ...(init?.headers ?? {}) },
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
