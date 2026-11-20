<template>
  <section class="page" data-module="funnel_analyze">
    <header class="page-head">
      <div>
        <h2>漏斗分析</h2>
        <p class="page-desc">
          按稳定步骤标识（step_id）维护多步骤转化漏斗；结果按数据版本存放，切换与回滚只移动活动版本，
          历史报告与路径归因始终读取同一版本。
        </p>
      </div>
    </header>

    <div class="analysis-summary">
      <article v-for="m in summaryMetrics" :key="m.label" class="analysis-card" data-testid="kpi-card">
        <span style="font-size:12px;color:var(--muted)">{{ m.label }}</span>
        <strong class="stat-value">{{ m.value }}</strong>
      </article>
    </div>

    <form class="analysis-form" @submit.prevent="runAnalysis">
      <label>
        <span>漏斗编号</span>
        <select v-model="selectedFunnel">
          <option v-for="item in funnels" :key="item.funnel_id" :value="item.funnel_id">
            {{ item.funnel_id }} · {{ item.funnel_name }}
          </option>
        </select>
      </label>
      <label>
        <span>数据版本</span>
        <input v-model="targetVersion" placeholder="留空则生成新版本" />
      </label>
      <button class="btn primary" type="submit" data-testid="run-analysis" :disabled="loading">
        {{ loading ? '计算中…' : '运行分析' }}
      </button>
      <button class="btn" type="button" :disabled="loading" @click="loadActive">读取活动版本</button>
    </form>

    <div v-if="chartData.length" class="analysis-chart">
      <div
        v-for="(bar, i) in chartData"
        :key="i"
        class="analysis-bar"
        :style="{ height: barHeight(bar.value) + 'px' }"
        :title="`${bar.label}：${bar.value}`"
      >
        <span>{{ bar.label }}</span>
      </div>
    </div>

    <table class="data-table" v-if="steps.length">
      <thead>
        <tr>
          <th>步序</th>
          <th>步骤标识</th>
          <th>事件编号</th>
          <th>步骤名称</th>
          <th>人数</th>
          <th>转化率</th>
          <th>分组归因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="step in steps" :key="step.step_id" :data-testid="`step-${step.step_id}`">
          <td>{{ step.step_index }}</td>
          <td>{{ step.step_id }}</td>
          <td>{{ step.event_id }}</td>
          <td>{{ step.step_name || '—' }}</td>
          <td>{{ step.count ?? '不可用（历史仅事件合计）' }}</td>
          <td>{{ step.rate == null ? '—' : (step.rate * 100).toFixed(2) + '%' }}</td>
          <td>{{ attributionText(step) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!steps.length && !loading" style="text-align:center;color:var(--muted)">
      请选择漏斗后运行分析
    </p>

    <div v-if="eventTotals.length" class="version-panel">
      <h3>历史事件合计（不拆分到步骤）</h3>
      <table class="data-table">
        <thead><tr><th>事件编号</th><th>分组值</th><th>事件合计人数</th><th>可归因步骤</th><th>口径</th></tr></thead>
        <tbody>
          <tr v-for="(row, i) in eventTotals" :key="i">
            <td>{{ row.event_id }}</td>
            <td>{{ row.group_value }}</td>
            <td>{{ row.count }}</td>
            <td>{{ (row.event_step_ids || []).join(' / ') || '—' }}</td>
            <td>仅事件合计，不能当作单步转化人数</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="version-panel" v-if="result">
      <h3>结果版本</h3>
      <p class="page-desc">
        数据版本 {{ result.data_version }} · 漏斗修订 {{ result.funnel_revision || '—' }} ·
        {{ result.schema_version === 'v1' ? '历史报告（v1）' : '第 2 版本结果' }}
      </p>
      <div class="version-actions">
        <span v-for="version in versions" :key="version">
          <button class="link" type="button" @click="switchVersion(version)">切换到 {{ version }}</button>
          <button class="link" type="button" @click="rollbackVersion(version)">回滚到 {{ version }}</button>
        </span>
      </div>
      <p v-if="message" class="page-desc">{{ message }}</p>
    </div>

    <footer class="page-foot">
      <span>{{ steps.length }} 个步骤</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type FunnelRow = { id: number; funnel_id: string; funnel_name: string; step_events?: string[] }
type StepRow = {
  step_id: string
  step_index: number
  event_id: string
  step_name?: string
  count?: number | null
  rate?: number | null
  count_source?: string
  group_attribution_available?: boolean
  group_results?: unknown[]
}
type EventGroupTotal = {
  event_id?: string
  group_value?: string
  count?: number | null
  event_step_ids?: string[]
}
type FunnelResult = {
  funnel_id: string
  funnel_name: string
  schema_version?: string
  data_version?: string
  funnel_revision?: string
  steps?: StepRow[]
  event_group_totals?: EventGroupTotal[]
}

const ENDPOINT = '/api/funnel-analyze'
const loading = ref(false)
const errorMessage = ref('')
const message = ref('')
const funnels = ref<FunnelRow[]>([])
const selectedFunnel = ref('FN-001')
const targetVersion = ref('')
const result = ref<FunnelResult | null>(null)
const versions = ref<string[]>([])

const steps = computed<StepRow[]>(() => result.value?.steps ?? [])
const eventTotals = computed<EventGroupTotal[]>(() => result.value?.event_group_totals ?? [])
const chartData = computed(() =>
  steps.value.map((step) => ({
    label: `第${step.step_index}步`,
    value: typeof step.count === 'number' ? step.count : 0,
  })),
)
const summaryMetrics = computed(() => [
  { label: '漏斗总数', value: funnels.value.length },
  { label: '当前步骤数', value: steps.value.length },
  { label: '活动版本', value: result.value?.data_version ?? '—' },
  { label: '历史分组合计', value: eventTotals.value.length },
])

function barHeight(value: number) {
  const max = Math.max(...chartData.value.map((item) => item.value), 1)
  return Math.max(10, (value / max) * 140)
}

function attributionText(step: StepRow) {
  if (step.group_attribution_available) {
    return `${step.group_results?.length ?? 0} 组（按 ${step.step_id} 归因）`
  }
  return step.count_source === 'unavailable_legacy_event_total_only'
    ? '不可用（历史仅事件合计）'
    : '无分组归因'
}

async function loadFunnels() {
  try {
    const data = await fetchJson<{ items: FunnelRow[] }>(ENDPOINT)
    funnels.value = data.items ?? []
    if (funnels.value.length && !funnels.value.some((item) => item.funnel_id === selectedFunnel.value)) {
      selectedFunnel.value = funnels.value[0].funnel_id
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '漏斗列表加载失败'
  }
}

async function loadVersions() {
  try {
    const data = await fetchJson<{ versions: string[] }>(`${ENDPOINT}/${selectedFunnel.value}/versions`)
    versions.value = data.versions ?? []
  } catch {
    versions.value = []
  }
}

async function loadActive() {
  loading.value = true
  errorMessage.value = ''
  try {
    result.value = await fetchJson<FunnelResult>(`${ENDPOINT}/${selectedFunnel.value}/result`)
    await loadVersions()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '结果读取失败'
    result.value = null
  } finally {
    loading.value = false
  }
}

async function runAnalysis() {
  loading.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    const query = targetVersion.value ? `?data_version=${encodeURIComponent(targetVersion.value)}` : ''
    const response = await request(`${ENDPOINT}/${selectedFunnel.value}/run${query}`, { method: 'POST' })
    if (!response.ok) throw new Error(`计算失败（${response.status}）`)
    const data = await response.json()
    result.value = data.entry as FunnelResult
    await loadVersions()
    message.value = `已生成结果版本 ${result.value?.data_version}`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '计算失败'
  } finally {
    loading.value = false
  }
}

async function switchVersion(version: string) {
  await changeVersion('switch', version)
}

async function rollbackVersion(version: string) {
  await changeVersion('rollback', version)
}

async function changeVersion(action: 'switch' | 'rollback', version: string) {
  errorMessage.value = ''
  message.value = ''
  try {
    const response = await request(
      `${ENDPOINT}/${selectedFunnel.value}/${action}?version=${encodeURIComponent(version)}`,
      { method: 'POST' },
    )
    if (!response.ok) throw new Error(`版本操作失败（${response.status}）`)
    const data = await response.json()
    message.value = `${action === 'switch' ? '已切换' : '已回滚'}到 ${data.entry?.active_version ?? version}`
    await loadActive()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '版本操作失败'
  }
}

onMounted(async () => {
  await loadFunnels()
  await loadActive()
})
</script>

<style scoped>
.version-panel { margin-top: 16px; }
.version-actions { display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; }
</style>
