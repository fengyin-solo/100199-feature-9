import { defineStore } from 'pinia'

// 角色口径与后端 app/identity.py 保持一致：
// - admin 值班管理员：可见全部班组，但换油确认/油温异常只能看不能提交
// - maintainer 保养人员：只能提交本班组齿轮箱的换油作业，别班组的只能查看
export type Role = 'admin' | 'maintainer'

export const TEAM_OPTIONS = [
  { code: 'team1', label: '一班' },
  { code: 'team2', label: '二班' },
  { code: 'team3', label: '三班' },
] as const

export type TeamCode = (typeof TEAM_OPTIONS)[number]['code']

const TEAM_LABEL: Record<TeamCode, string> = {
  team1: '一班',
  team2: '二班',
  team3: '三班',
}

interface SessionState {
  role: Role
  teamCode: TeamCode
  operator: string
  shiftLabel: string
  scope: string
}

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    role: 'admin',
    teamCode: 'team1',
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '风电场机组运维平台',
  }),
  getters: {
    teamLabel: (state) => TEAM_LABEL[state.teamCode],
    isAdmin: (state) => state.role === 'admin',
    // 仅本班组保养人员具备提交资格；具体到某台齿轮箱还要比对它的归属班组。
    canSubmit: (state) => state.role === 'maintainer',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    switchIdentity(role: Role, teamCode: TeamCode, name: string) {
      this.role = role
      this.teamCode = teamCode
      this.operator = name.trim() || (role === 'admin' ? '值班管理员' : '保养人员')
    },
    canModifyTeam(ownerTeam: string | null | undefined): boolean {
      return this.role === 'maintainer' && ownerTeam === TEAM_LABEL[this.teamCode]
    },
  },
})
