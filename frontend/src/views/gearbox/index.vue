<template>
  <section class="page" data-module="gearbox">
    <header class="page-head">
      <div>
        <h2>齿轮箱管理</h2>
        <p class="page-desc">
          换油确认与油温异常登记按作业班组划清归属：仅本班组保养人员可提交，其他班组只读，值班管理员可查看全部班组。
          当前身份：{{ session.operator }} · {{ session.roleLabel }}
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" :class="{ ghost: activeTab !== 'list' }" @click="switchTab('list')">换油列表</button>
        <button class="btn" type="button" :class="{ ghost: activeTab !== 'ledger' }" @click="switchTab('ledger')">换油台账</button>
        <button class="btn" type="button" @click="exportRows">导出齿轮箱清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <!-- 换油列表 -->
    <div v-if="activeTab === 'list'">
      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>齿轮箱编号</span>
          <input v-model="keyword" placeholder="按齿轮箱编号检索" />
        </label>
        <label class="filter-item">
          <span>状态</span>
          <select v-model="statusFilter">
            <option value="">全部状态</option>
            <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">{{ display(row, column) }}</td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                :class="{ locked: denyReason(row, action) }"
                type="button"
                :title="denyReason(row, action)"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">暂无齿轮箱数据</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条齿轮箱记录（所有班组均可查看，仅归属班组可改）</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </div>

    <!-- 换油台账 -->
    <div v-else>
      <form class="filter-bar" @submit.prevent="reloadLedger">
        <label class="filter-item">
          <span>动作</span>
          <select v-model="ledgerActionFilter">
            <option value="">全部动作</option>
            <option value="确认换油">确认换油</option>
            <option value="登记油温异常">登记油温异常</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetLedgerFilter">重置条件</button>
        <span class="filter-hint">同一齿轮箱换过两次油时，以本班组最近一次「确认换油」为准；人员调班后历史仍挂原班组。</span>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in ledgerColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in ledger" :key="String(record.id)">
            <td v-for="column in ledgerColumns" :key="column">{{ ledgerCell(record, column) }}</td>
          </tr>
          <tr v-if="!ledger.length">
            <td :colspan="ledgerColumns.length" class="empty-state">暂无换油台账记录</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ ledger.length }} 条台账记录（只追加，不覆盖）</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </div>

    <!-- 提交弹窗 -->
    <div v-if="dialog.action" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3 class="modal-title">{{ dialog.action }} · {{ dialog.row?.['齿轮箱编号'] }}</h3>
        <p class="modal-sub">归属班组：{{ dialog.row?.['作业班组'] }}；提交人：{{ session.operator }}</p>
        <div v-if="dialog.action === '确认换油'" class="modal-form">
          <label>
            <span>换油日期 <em>*</em></span>
            <input v-model="dialog.form.换油日期" type="date" />
          </label>
          <label>
            <span>油品型号 <em>*</em></span>
            <input v-model="dialog.form.油品型号" placeholder="如 Omala S4 GX 320" />
          </label>
          <label>
            <span>下次换油日 <em>*</em></span>
            <input v-model="dialog.form.下次换油日" type="date" />
          </label>
        </div>
        <div v-else-if="dialog.action === '登记油温异常'" class="modal-form">
          <label>
            <span>登记日期 <em>*</em></span>
            <input v-model="dialog.form.登记日期" type="date" />
          </label>
          <label class="modal-wide">
            <span>异常说明 <em>*</em></span>
            <textarea v-model="dialog.form.异常说明" rows="3" placeholder="如实测油温、超限情况"></textarea>
          </label>
        </div>
        <p v-if="dialog.error" class="error-text">{{ dialog.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="dialog.submitting" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" :disabled="dialog.submitting" @click="submitDialog">
            {{ dialog.submitting ? '提交中…' : '提交' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore, type UserInfo } from '@/stores/session'

type Row = Record<string, string | number | null>
type LedgerRecord = Record<string, string | number | null>

const ENDPOINT = '/api/gearbox'
const columns = ['齿轮箱编号', '所属机组', '油温上限', '振动值', '作业班组', '上次换油日', '下次换油日', '油品型号', '齿轮箱状态']
const ledgerColumns = ['齿轮箱编号', '动作', '日期', '油品型号', '下次换油日', '异常说明', '作业班组', '操作人', '登记时间']
const actions = ['确认换油', '登记油温异常', '更换齿轮箱']
const statuses = ['待换油', '运行正常', '油温偏高', '已更换']

const session = useSessionStore()

const rows = ref<Row[]>([])
const ledger = ref<LedgerRecord[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const ledgerActionFilter = ref('')
const activeTab = ref<'list' | 'ledger'>('list')

const stats = ref([
  { label: '待换油齿轮箱（与概览一致）', value: 0 },
  { label: '油温偏高台数', value: 0 },
  { label: '本月换油数', value: 0 },
])

const dialog = reactive<{
  action: string
  row: Row | null
  form: Record<string, string>
  error: string
  submitting: boolean
}>({
  action: '',
  row: null,
  form: {},
  error: '',
  submitting: false,
})

const currentUser = computed<UserInfo | undefined>(() => session.currentUser)
const today = () => new Date().toISOString().slice(0, 10)

function display(row: Row, column: string): string {
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function ledgerCell(record: LedgerRecord, column: string): string {
  const value = record[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

/** 归属判定：管理员只读；保养人员只能操作归属本班组的齿轮箱；更换齿轮箱仅管理员。 */
function denyReason(row: Row, action: string): string {
  const user = currentUser.value
  if (action === '更换齿轮箱') {
    return user?.role === 'admin' ? '' : '更换齿轮箱属于值班管理员处置权限，保养人员请联系值班管理员'
  }
  if (!user) {
    return ''
  }
  if (user.role === 'admin') {
    return '值班管理员可查看全部班组数据，但不能代班组提交'
  }
  const owner = String(row['作业班组'] ?? '')
  if (user.team && user.team === owner) {
    return ''
  }
  return `该齿轮箱归属${owner}，${user.team ?? '本账号'}只能查看不能改动，请由${owner}保养人员提交${action}`
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function resetLedgerFilter() {
  ledgerActionFilter.value = ''
  void reloadLedger()
}

function switchTab(tab: 'list' | 'ledger') {
  activeTab.value = tab
  errorMessage.value = ''
  if (tab === 'ledger') {
    void reloadLedger()
  } else {
    void reload()
  }
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function runAction(action: string, row: Row) {
  errorMessage.value = ''
  // 前端先挡一道，跨班组在列表页直接说明原因；服务端还会再校验一次。
  const reason = denyReason(row, action)
  if (reason) {
    errorMessage.value = reason
    return
  }
  if (action === '更换齿轮箱') {
    void submitSimpleAction(action, row)
    return
  }
  openDialog(action, row)
}

function openDialog(action: string, row: Row) {
  dialog.action = action
  dialog.row = row
  dialog.error = ''
  dialog.submitting = false
  if (action === '确认换油') {
    dialog.form = { 换油日期: today(), 油品型号: String(row['油品型号'] ?? ''), 下次换油日: '' }
  } else {
    dialog.form = { 登记日期: today(), 异常说明: '' }
  }
}

function closeDialog() {
  dialog.action = ''
  dialog.row = null
  dialog.form = {}
  dialog.error = ''
}

async function submitDialog() {
  if (!dialog.row) {
    return
  }
  dialog.submitting = true
  dialog.error = ''
  try {
    const payload: Record<string, string> = { action: dialog.action, ...dialog.form }
    const result = await postAction(Number(dialog.row.id), payload)
    if (!result.ok) {
      dialog.error = result.message
      return
    }
    closeDialog()
    await Promise.all([reload(), reloadLedger()])
  } finally {
    dialog.submitting = false
  }
}

async function submitSimpleAction(action: string, row: Row) {
  const result = await postAction(Number(row.id), { action })
  errorMessage.value = result.ok ? '' : result.message
  if (result.ok) {
    await reload()
  }
}

async function postAction(entryId: number, payload: Record<string, string>): Promise<{ ok: boolean; message: string }> {
  try {
    const response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const data = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !data) {
      return { ok: false, message: '齿轮箱动作未生效，请稍后重试' }
    }
    return { ok: Boolean(data.ok), message: data.message ?? '' }
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : '齿轮箱操作失败' }
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) {
    params.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('齿轮箱列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await reloadStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '齿轮箱列表读取失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const data = (await response.json()) as Record<string, number>
    stats.value[0].value = data.pending ?? 0
    stats.value[1].value = data.abnormal ?? 0
    stats.value[2].value = data.month_changed ?? 0
  } catch {
    // 统计拉取失败时保留上次数值，不影响列表使用。
  }
}

async function reloadLedger() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (ledgerActionFilter.value) {
    params.set('action', ledgerActionFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}/ledger?${params.toString()}`)
    if (!response.ok) {
      throw new Error('换油台账读取失败')
    }
    const payload = await response.json()
    ledger.value = payload.items ?? []
    const data = payload.stats as Record<string, number> | undefined
    if (data) {
      stats.value[0].value = data.pending ?? 0
      stats.value[1].value = data.abnormal ?? 0
      stats.value[2].value = data.month_changed ?? 0
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '换油台账读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadLedger()
})
</script>

<style scoped>
.filter-hint { color: var(--muted); font-size: 12px; }
.link.locked { color: #9aa6b2; cursor: not-allowed; text-decoration: line-through; }
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 460px;
  background: #fff;
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.2);
}
.modal-title { margin: 0; font-size: 16px; }
.modal-sub { margin: 6px 0 14px; color: var(--muted); font-size: 12px; }
.modal-form { display: flex; flex-wrap: wrap; gap: 12px; }
.modal-form label { flex: 1 1 200px; display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.modal-form label.modal-wide { flex-basis: 100%; }
.modal-form input, .modal-form textarea {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font: inherit;
}
.modal-form em { color: #b42318; font-style: normal; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
