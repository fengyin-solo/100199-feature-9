import { defineStore } from 'pinia'

import { currentUserId, fetchJson, setCurrentUserId } from '@/api/client'

export type Role = 'admin' | 'maintenance'

export type UserInfo = {
  id: string
  name: string
  role: Role
  team: string | null
  title: string
  note?: string
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    users: [] as UserInfo[],
    currentId: currentUserId(),
    shiftLabel: '白班 08:00-20:00',
    scope: '风电场机组运维平台',
  }),
  getters: {
    currentUser(state): UserInfo | undefined {
      return state.users.find((user) => user.id === state.currentId)
    },
    operator(): string {
      return this.currentUser?.name ?? '值班管理员'
    },
    roleLabel(): string {
      const user = this.currentUser
      if (!user) {
        return '值班管理员 · 全部班组只读'
      }
      return user.role === 'admin'
        ? `${user.title} · 全部班组只读`
        : `${user.title} · ${user.team}`
    },
  },
  actions: {
    async loadUsers() {
      try {
        const payload = await fetchJson<{ items: UserInfo[] }>('/api/users')
        this.users = payload.items
      } catch {
        // 用户清单拉不到时保留默认值班管理员身份，不阻塞页面渲染。
        this.users = []
      }
    },
    switchUser(id: string) {
      this.currentId = id
      setCurrentUserId(id)
    },
    setShift(label: string) {
      this.shiftLabel = label
    },
  },
})
