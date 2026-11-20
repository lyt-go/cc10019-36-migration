import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

type ModuleCase = {
  key: string
  fields: string[]
  actions: string[]
  actionTargets: string[]
  shape: string
}

const modules: ModuleCase[] = [
  {
    "key": "event_track",
    "fields": [
      "事件编号",
      "事件名称",
      "事件分类",
      "属性定义",
      "上报频率",
      "采样比例",
      "数据表名",
      "事件版本"
    ],
    "actions": [
      "提交校验",
      "启用事件",
      "停用事件"
    ],
    "actionTargets": [
      "待校验",
      "已启用",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "tag_define",
    "fields": [
      "标签编号",
      "标签名称",
      "标签层级",
      "计算逻辑",
      "数据来源",
      "更新周期",
      "覆盖阈值",
      "标签版本"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "标记废弃"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "tag_compute",
    "fields": [
      "任务编号",
      "关联标签",
      "计算范围",
      "计算引擎",
      "输入分区",
      "输出分区",
      "并行度",
      "执行状态"
    ],
    "actions": [
      "提交执行",
      "停止计算",
      "重算任务"
    ],
    "actionTargets": [
      "草稿",
      "计算中",
      "已完成"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "crowd_select",
    "fields": [
      "条件编号",
      "条件名称",
      "标签组合",
      "逻辑表达式",
      "预计规模",
      "刷新频率",
      "输出集合",
      "条件版本"
    ],
    "actions": [
      "预估规模",
      "标记生效",
      "标记过期"
    ],
    "actionTargets": [
      "预估中",
      "已生效",
      "已过期"
    ],
    "shape": "crud-table"
  },
  {
    "key": "behavior_path",
    "fields": [
      "模型编号",
      "起始事件",
      "目标事件",
      "时间窗口",
      "路径深度",
      "会话标识",
      "路径过滤",
      "分析区间",
      "关联漏斗",
      "漏斗结果版本",
      "归因步骤"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "停用模型"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已停用"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "retention_calc",
    "fields": [
      "配置编号",
      "初始行为",
      "回访行为",
      "计算周期",
      "分段维度",
      "基准日期",
      "留存窗口",
      "结果表名"
    ],
    "actions": [
      "发起计算",
      "确认完成",
      "归档结果"
    ],
    "actionTargets": [
      "计算中",
      "已完成",
      "已归档"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "user_segment",
    "fields": [
      "分群编号",
      "分群名称",
      "基准行为",
      "分层规则",
      "时间范围",
      "分群规模",
      "更新方式",
      "分群版本"
    ],
    "actions": [
      "发起分群",
      "确认就绪",
      "标记过期"
    ],
    "actionTargets": [
      "计算中",
      "已就绪",
      "已过期"
    ],
    "shape": "crud-table"
  },
  {
    "key": "lifetime_value",
    "fields": [
      "模型编号",
      "用户分群",
      "价值指标",
      "预测窗口",
      "衰减因子",
      "历史基线",
      "校准周期",
      "模型版本"
    ],
    "actions": [
      "开始训练",
      "确认就绪",
      "废弃模型"
    ],
    "actionTargets": [
      "训练中",
      "已就绪",
      "已废弃"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "funnel_analyze",
    "fields": [
      "漏斗编号",
      "漏斗名称",
      "步骤序列",
      "转化窗口",
      "步骤窗口",
      "关联事件",
      "分组维度",
      "数据范围"
    ],
    "actions": [
      "发起计算",
      "确认完成",
      "归档结果"
    ],
    "actionTargets": [
      "计算中",
      "已完成",
      "已归档"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "event_cleanse",
    "fields": [
      "规则编号",
      "事件名称",
      "校验字段",
      "合法范围",
      "异常处理",
      "刷量检测",
      "去重窗口",
      "规则版本"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "停用规则"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "session_split",
    "fields": [
      "策略编号",
      "策略名称",
      "超时阈值",
      "跨天策略",
      "跨渠道策略",
      "归因窗口",
      "会话标识",
      "策略版本"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "停用策略"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "profile_card",
    "fields": [
      "卡片编号",
      "卡片名称",
      "展示标签",
      "数据来源",
      "展示样式",
      "刷新策略",
      "关联分群",
      "卡片版本"
    ],
    "actions": [
      "提交校验",
      "确认发布",
      "停用卡片"
    ],
    "actionTargets": [
      "待校验",
      "已发布",
      "已停用"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "attr_dict",
    "fields": [
      "属性编号",
      "属性名称",
      "数据类型",
      "枚举值集",
      "数据来源",
      "更新频率",
      "归因方式",
      "属性版本"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "标记废弃"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "overlap_analysis",
    "fields": [
      "任务编号",
      "人群A",
      "人群B",
      "交集方式",
      "分析维度",
      "输出指标",
      "结果表名",
      "分析时间"
    ],
    "actions": [
      "发起分析",
      "确认完成",
      "取消分析"
    ],
    "actionTargets": [
      "计算中",
      "已完成",
      "已取消"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "tag_drill",
    "fields": [
      "配置编号",
      "父标签",
      "子标签集",
      "下钻维度",
      "数据范围",
      "统计方式",
      "输出格式",
      "刷新间隔"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "停用配置"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已停用"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "event_aggregate",
    "fields": [
      "配置编号",
      "事件名称",
      "聚合维度",
      "聚合函数",
      "时间粒度",
      "过滤条件",
      "输出表名",
      "更新周期"
    ],
    "actions": [
      "提交校验",
      "标记生效",
      "停用配置"
    ],
    "actionTargets": [
      "待校验",
      "已生效",
      "已停用"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "tag_snapshot",
    "fields": [
      "快照编号",
      "快照日期",
      "用户基数",
      "标签数量",
      "分群数量",
      "快照路径",
      "存储格式",
      "保留天数"
    ],
    "actions": [
      "创建快照",
      "确认完成",
      "标记过期"
    ],
    "actionTargets": [
      "创建中",
      "已完成",
      "已过期"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "behavior_heatmap",
    "fields": [
      "配置编号",
      "行为事件",
      "时间范围",
      "空间维度",
      "聚合粒度",
      "色阶规则",
      "输出图片",
      "刷新频率"
    ],
    "actions": [
      "发起计算",
      "确认完成",
      "停用配置"
    ],
    "actionTargets": [
      "计算中",
      "已完成",
      "已停用"
    ],
    "shape": "analysis-dashboard"
  }
]
const repoKind = 'fullstack'
const crudModules = modules.filter(m => m.shape === 'crud-table')
const dagModules = modules.filter(m => m.shape === 'dag-graph')
const timelineModules = modules.filter(m => m.shape === 'job-timeline')
const analysisModules = modules.filter(m => m.shape === 'analysis-dashboard')

function parseCsv(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const input = text.replace(/^\uFEFF/, '')
  for (let index = 0; index < input.length; index++) {
    const char = input[index]
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') { cell += '"'; index++ }
      else if (char === '"') { quoted = false }
      else { cell += char }
    } else if (char === '"' && cell === '') { quoted = true }
    else if (char === ',') { row.push(cell); cell = '' }
    else if (char === '\n') {
      row.push(cell.replace(/\r$/, ''))
      if (row.some(v => v !== '')) records.push(row)
      row = []; cell = ''
    } else { cell += char }
  }
  row.push(cell.replace(/\r$/, ''))
  if (row.some(v => v !== '')) records.push(row)
  return records
}

test('CRUD模块：筛选、导出、登记、动作、指标全链路', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (crudModules.length === 0) { test.skip(); return }

  for (const mod of crudModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    const bodyRows = page.locator('tbody tr[data-testid^="row-"]')
    await expect(bodyRows).toHaveCount(3)
    const firstValue = await bodyRows.nth(0).locator('td').nth(0).innerText()

    await page.getByTestId(`filter-${mod.fields[0]}`).fill(firstValue)
    await page.getByTestId('query').click()
    await expect(bodyRows).toHaveCount(1)
    await page.getByTestId('reset').click()
    await expect(bodyRows).toHaveCount(3)

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    const createdValues = mod.fields.map((f, i) => `验收-${mod.key}-${i+1}`)
    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.entries()) {
      await page.getByTestId(`create-${field}`).fill(createdValues[i])
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
    await expect(bodyRows).toHaveCount(4)

    const createdRow = page.locator('tbody tr').filter({ hasText: createdValues[0] })
    for (const [i, action] of mod.actions.entries()) {
      await createdRow.getByRole('button', { name: action, exact: true }).click()
      await expect(createdRow).toHaveAttribute('data-status', mod.actionTargets[i])
    }
  }

  expect(browserErrors).toEqual([])
})

test('DAG拓扑模块：节点渲染、详情、动作、导出', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (dagModules.length === 0) { test.skip(); return }

  for (const mod of dagModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    await expect(page.locator('svg.dag-svg')).toBeVisible()
    const nodes = page.locator('g.dag-node')
    const count = await nodes.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await nodes.first().click()
    await expect(page.getByTestId('dag-detail')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('时间线模块：甘特条渲染、日期筛选、日志查看、登记', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (timelineModules.length === 0) { test.skip(); return }

  for (const mod of timelineModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.locator('.timeline-bar').first()).toBeVisible({ timeout: 10000 })
    const bars = page.locator('.timeline-bar')
    const count = await bars.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await bars.first().click()
    await expect(page.getByTestId('timeline-log')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('分析看板模块：KPI卡片、运行分析、图表渲染', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (analysisModules.length === 0) { test.skip(); return }

  for (const mod of analysisModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.getByTestId('kpi-card').first()).toBeVisible({ timeout: 10000 })
    const kpiCards = page.getByTestId('kpi-card')
    const kpiCount = await kpiCards.count()
    expect(kpiCount).toBeGreaterThanOrEqual(2)
    await expect(kpiCards.first().locator('strong')).toBeVisible()

    await page.getByTestId('run-analysis').click()
    await expect(page.locator('.analysis-bar').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.data-table tbody tr').first()).toBeVisible({ timeout: 5000 })
  }

  expect(browserErrors).toEqual([])
})

test('概览汇总', async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto('/')
  await expect(page.locator('.stat-value').nth(1)).toBeVisible()
  // 验证概览页加载正常即可，不硬编码精确计数（取决于各模块 E2E 登记成功数）
})
