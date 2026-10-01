<template>
  <section class="page" data-module="gearbox">
    <header class="page-head">
      <div>
        <h2>齿轮箱管理</h2>
        <p class="page-desc">
          按作业班组管理换油作业：仅本班组保养人员能提交换油确认与油温异常登记，
          其他班组与值班管理员只能查看；值班管理员可见全部班组。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出齿轮箱清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>所属班组</span>
        <select v-model="teamFilter">
          <option value="">全部班组</option>
          <option v-for="team in teamOptions" :key="team.label" :value="team.label">{{ team.label }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p class="scope-tip" v-if="session.isAdmin">当前身份：值班管理员，可查看全部班组齿轮箱与台账，但不能替班组提交换油作业。</p>
    <p class="scope-tip" v-else>当前身份：{{ session.teamLabel }}保养人员，仅可提交本班组齿轮箱的换油确认与油温异常登记，其他班组只能查看。</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-for="action in actions" :key="action">
              <button
                class="link"
                :class="{ 'link-disabled': !canModify(row) }"
                :title="canModify(row) ? action : denyHint(row)"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无齿轮箱数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条齿轮箱记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <section class="ledger-block">
      <header class="ledger-head">
        <h3>换油台账</h3>
        <div class="ledger-tools">
          <label class="filter-item">
            <span>作业班组</span>
            <select v-model="ledgerTeam" @change="loadLedger">
              <option value="">全部班组</option>
              <option v-for="team in teamOptions" :key="team.label" :value="team.label">{{ team.label }}</option>
            </select>
          </label>
          <span class="ledger-pending">待处理 {{ ledgerPending }} 台</span>
        </div>
      </header>
      <p class="scope-note">
        同一齿轮箱多次换油时，列表与各处展示只取本班组最近一次记录；人员调班后历史记录仍挂在原班组名下。
        待处理数与「运营概览」齿轮箱模块保持一致（当前：概览 {{ overviewPending }} 台 / 台账 {{ ledgerPending }} 台）。
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in ledgerColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in ledgerRows" :key="String(record.id)">
            <td v-for="column in ledgerColumns" :key="column">{{ record[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!ledgerRows.length">
            <td :colspan="ledgerColumns.length" class="empty-state">暂无换油台账记录</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'
import { TEAM_OPTIONS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>
type OilRecord = Record<string, string | number | null>

const ENDPOINT = '/api/gearbox'
const columns = ["齿轮箱编号", "所属班组", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]
const ledgerColumns = ["齿轮箱编号", "所属机组", "换油日期", "油品型号", "下次换油日", "作业班组", "保养人员"]
const actions = ["确认换油", "登记油温异常", "更换齿轮箱"]
const teamOptions = TEAM_OPTIONS

const session = useSessionStore()

const rows = ref<Row[]>([])
const ledgerRows = ref<OilRecord[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const teamFilter = ref('')
const ledgerTeam = ref('')
const ledgerPending = ref(0)
const overviewPending = ref(0)
const stats = ref([
  { label: '待处理（同概览口径）', value: 0 },
  { label: '油温偏高台数', value: 0 },
  { label: '本月换油数', value: 0 },
])

function canModify(row: Row): boolean {
  return session.canModifyTeam(row['所属班组'] == null ? null : String(row['所属班组']))
}

// 跨班组在列表页点击提交时直接挡下，并给出与后端一致口径的原因说明。
function denyHint(row: Row): string {
  const owner = row['所属班组'] == null ? '未指派班组' : String(row['所属班组'])
  if (session.isAdmin) {
    return '值班管理员仅可查看，换油确认与油温异常登记须由本班组保养人员提交'
  }
  return `该齿轮箱归属${owner}，您当前在${session.teamLabel}，跨班组只能查看，须由${owner}保养人员提交`
}

function resetFilters() {
  filters.value = {}
  teamFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  if (!canModify(row)) {
    // 不发请求：跨班组提交在列表页即被挡下。
    errorMessage.value = denyHint(row)
    return
  }

  const values: Record<string, string> = { action }
  if (action === '确认换油') {
    const oilBrand = window.prompt('请输入本次换油使用的油品型号（如 Shell Omala S4 460）')
    if (oilBrand == null) return
    if (!oilBrand.trim()) {
      errorMessage.value = '油品型号未填写，换油确认未提交'
      return
    }
    values['油品型号'] = oilBrand.trim()
    const nextDate = window.prompt('下次换油日（YYYY-MM-DD，留空默认顺延 180 天）', '')
    if (nextDate == null) return
    if (nextDate.trim()) values['下次换油日'] = nextDate.trim()
  } else if (action === '登记油温异常') {
    const oilTemp = window.prompt('请输入当前油温值（如 83.5℃）', '')
    if (oilTemp == null) return
    if (oilTemp.trim()) values['油温值'] = oilTemp.trim()
  } else if (action === '更换齿轮箱' && !window.confirm('确认提交「更换齿轮箱」？')) {
    return
  }

  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 后端再兜一道：身份被篡改或归属变更时，错误原因仍能展示给页面。
      throw new Error(payload?.message || '齿轮箱动作未生效，请稍后重试')
    }
    successMessage.value = payload.message
    await Promise.all([reload(), loadLedger(), loadStats(), loadOverviewPending()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '齿轮箱操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>)
  if (teamFilter.value) query.set('team', teamFilter.value)
  try {
    const payload = await fetchJson<{ items: Row[]; total: number }>(`${ENDPOINT}?${query.toString()}`)
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '齿轮箱列表读取失败'
  }
}

async function loadStats() {
  try {
    const data = await fetchJson<Record<string, number>>(`${ENDPOINT}/stats`)
    stats.value = [
      { label: '待处理（同概览口径）', value: data['待处理'] ?? 0 },
      { label: '油温偏高台数', value: data['油温偏高台数'] ?? 0 },
      { label: '本月换油数', value: data['本月换油数'] ?? 0 },
    ]
  } catch {
    /* 统计失败保留 0，不阻塞列表 */
  }
}

async function loadLedger() {
  const query = new URLSearchParams()
  if (ledgerTeam.value) query.set('team', ledgerTeam.value)
  try {
    const data = await fetchJson<{ items: OilRecord[]; total: number; pending: number }>(
      `${ENDPOINT}/oil-records?${query.toString()}`,
    )
    ledgerRows.value = data.items ?? []
    ledgerPending.value = data.pending ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '换油台账读取失败'
  }
}

async function loadOverviewPending() {
  try {
    const overview = await fetchJson<{
      modules: { name: string; pending: number }[]
    }>('/api/overview')
    overviewPending.value = overview.modules.find((item) => item.name === 'gearbox')?.pending ?? 0
  } catch {
    /* 概览取不到时不影响台账本身展示 */
  }
}

onMounted(async () => {
  await Promise.all([reload(), loadStats(), loadLedger(), loadOverviewPending()])
})
</script>

<style scoped>
.scope-tip {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
}
.link-disabled {
  color: #94a3b8;
  cursor: not-allowed;
  text-decoration: none;
}
.success-text {
  color: #15803d;
}
.ledger-block {
  margin-top: 20px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.ledger-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.ledger-head h3 {
  margin: 0;
  font-size: 15px;
}
.ledger-tools {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}
.ledger-pending {
  font-size: 13px;
  color: #b42318;
  font-weight: 600;
}
.scope-note {
  font-size: 12px;
  color: var(--muted);
  margin: 0 0 10px;
}
</style>
