<template>
  <div class="page home-page fade-in">
    <div class="home-summary">
      <div class="summary-metrics">
        <el-card v-for="item in summaryCards" :key="item.name" class="summary-card" :style="{ '--accent': item.color }" shadow="never">
          <span class="summary-card-label">{{ item.name }}</span>
          <span class="summary-card-number">
            <strong>{{ item.value }}</strong>
            <em>{{ item.unit }}</em>
          </span>
        </el-card>
      </div>
    </div>

    <div class="analysis-grid">
      <section class="analysis-panel">
        <div class="section-title">
          <h3>来源结构 · 大数据分析</h3>
          <span class="muted">RSS / Journal</span>
        </div>
        <div class="rank-list source-rank">
          <div v-for="row in sourceRows" :key="row.name" class="rank-row">
            <span>{{ row.name }}</span>
            <div class="bar-track"><div class="bar-fill" :style="{ width: `${row.percent}%` }"></div></div>
            <strong>{{ row.count }}</strong>
          </div>
          <el-empty v-if="!sourceRows.length" description="暂无来源统计" :image-size="80" />
        </div>
      </section>

      <section class="analysis-panel">
        <div class="section-title">
          <h3>研究方向聚合</h3>
          <span class="muted">Direction Profile</span>
        </div>
        <div class="rank-list">
          <div v-for="row in directionRows" :key="row.name" class="rank-row">
            <span>{{ row.name }}</span>
            <div class="bar-track"><div class="bar-fill violet" :style="{ width: `${row.percent}%` }"></div></div>
            <strong>{{ row.count }}</strong>
          </div>
          <el-empty v-if="!directionRows.length" description="暂无方向统计" :image-size="80" />
        </div>
      </section>

      <section class="analysis-panel">
        <div class="section-title">
          <h3>近 7 日文献趋势</h3>
          <span class="muted">Daily Trend</span>
        </div>
        <div class="trend-line-card">
          <svg viewBox="0 0 300 120" preserveAspectRatio="none" aria-label="近 7 日文献趋势">
            <polyline class="trend-area" :points="trendAreaPoints" />
            <polyline class="trend-line-path" :points="trendLinePoints" />
            <circle v-for="point in trendPointRows" :key="point.date" :cx="point.x" :cy="point.y" r="4" />
          </svg>
          <div class="trend-labels">
            <div v-for="item in trendRows" :key="item.date">
              <strong>{{ item.count }}</strong>
              <span>{{ item.label }}</span>
            </div>
          </div>
        </div>
      </section>

      <section class="analysis-panel">
        <div class="section-title">
          <h3>关键词热度溯源</h3>
          <span class="muted">Keyword Rank</span>
        </div>
        <div class="rank-list">
          <div v-for="row in keywordRows" :key="row.name" class="rank-row">
            <span>{{ row.name }}</span>
            <div class="bar-track"><div class="bar-fill green" :style="{ width: `${row.percent}%` }"></div></div>
            <strong>{{ row.count }}</strong>
          </div>
          <el-empty v-if="!keywordRows.length" description="暂无关键词统计" :image-size="80" />
        </div>
      </section>
    </div>

    <div class="daily-grid">
      <section class="analysis-panel paper-focus">
        <div class="section-title">
          <h3>{{ latestDate === todayText ? '今日重点文献' : `${latestDate} 重点文献` }}</h3>
          <el-button type="primary" plain @click="$router.push('/papers')">查看全部</el-button>
        </div>
        <div class="focus-list">
          <article v-for="(paper, index) in keyPapers" :key="paper.id" class="focus-item">
            <div class="focus-index">{{ index + 1 }}</div>
            <div class="focus-body">
              <div class="focus-title-row">
                <h4 @click="openPaper(paper)">{{ paper.title }}</h4>
                <el-tag :type="levelType(paper.recommend_level)" effect="light">{{ scoreTitle(paper) }}</el-tag>
              </div>
              <p class="focus-meta">
                {{ cleanJournal(paper.journal || paper.source_name) }} · 入库 {{ formatPaperDate(paper.created_at) }} · {{ publicationDateLabel(paper) }}
                <template v-if="paper.doi"> · DOI: {{ paper.doi }}</template>
              </p>
              <p class="focus-hit">{{ recommendationReason(paper) }}</p>
              <p class="focus-abstract">{{ truncate(paper.abstract || '暂无摘要，建议后续通过 DOI 补全或查看全文。', 220) }}</p>
            </div>
          </article>
          <el-empty v-if="!keyPapers.length" description="暂无达到重点推荐分数的文献" :image-size="90" />
        </div>
      </section>

      <section class="analysis-panel status-panel">
        <div class="section-title">
          <h3>入库与订阅状态</h3>
          <div class="status-actions">
            <router-link v-if="todayFetchStatus === '抓取失败'" to="/admin/fetch_logs">查看抓取日志</router-link>
            <el-button size="small" plain :loading="fetching" :disabled="fetching" @click="autoFetch">备用抓取</el-button>
          </div>
        </div>
        <div class="status-grid">
          <div class="status-cell">
            <span>DOI 覆盖率</span>
            <strong>{{ doiRate }}%</strong>
          </div>
          <div class="status-cell">
            <span>摘要覆盖率</span>
            <strong>{{ abstractRate }}%</strong>
          </div>
          <div class="status-cell">
            <span>已入 Zotero</span>
            <strong>{{ importedTodayCount }}</strong>
          </div>
          <div class="status-cell">
            <span>最近抓取</span>
            <strong :title="recentFailureReason">{{ todayFetchStatus }}</strong>
          </div>
        </div>
        <div class="log-list">
          <div v-for="log in recentLogs" :key="log.id" class="log-row">
            <el-tag :type="log.status === 'success' ? 'success' : log.status === 'partial' ? 'warning' : 'danger'" effect="light">
              {{ log.status }}
            </el-tag>
            <span>{{ log.source_name || '系统任务' }}</span>
            <em>新入库 {{ log.new_count || 0 }} / 已存在 {{ log.duplicate_count || 0 }}</em>
            <span v-if="log.status === 'failed'" class="log-reason" :title="log.message">{{ log.message || '请查看抓取日志' }}</span>
          </div>
          <el-empty v-if="!recentLogs.length" description="暂无抓取日志" :image-size="76" />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getFetchLogs } from '../api/logs'
import { getPaperDashboardStats, getPaperDateCounts, getPapers } from '../api/papers'
import { getScoringSettings } from '../api/settings'
import { getActiveFetchDailyTask, getFetchDailyTask, startFetchDailyTask } from '../api/reports'
import { levelType, recommendationReason, scoreTitle } from '../utils/scoring'

const todayText = formatDate(new Date())
const latestDate = ref(todayText)
const todayCount = ref(0)
const paperTotal = ref(0)
const favoriteCount = ref(0)
const missingAbstract = ref(0)
const sourceRows = ref([])
const directionRows = ref([])
const keywordRows = ref([])
const trendRows = ref([])
const todayPapers = ref([])
const keyThreshold = ref(30)
const keyPapersMax = ref(8)
const recentLogs = ref([])
const todayLogs = ref([])
const doiCount = ref(0)
const abstractCount = ref(0)
const importedCount = ref(0)
const fetchTaskId = ref('')
const fetchTaskStatus = ref('')
const fetchTaskMessage = ref('')
const startingFetchTask = ref(false)
let fetchPollTimer = null

const summaryCards = computed(() => [
  { name: '当日新增', value: todayCount.value, unit: '篇', color: '#2F8CFF' },
  { name: '文献总数', value: paperTotal.value, unit: '篇', color: '#25D6C8' },
  { name: '收藏数量', value: favoriteCount.value, unit: '篇', color: '#F59E0B' },
  { name: '待补摘要', value: missingAbstract.value, unit: '篇', color: '#7C6CFF' },
])

const keyPapers = computed(() => {
  return [...todayPapers.value]
    .filter((paper) => paper.recommend_level === 'key' && scorePaper(paper) >= keyThreshold.value)
    .sort((a, b) => scorePaper(b) - scorePaper(a))
    .slice(0, keyPapersMax.value)
})

const doiRate = computed(() => percent(doiCount.value, todayCount.value))
const abstractRate = computed(() => percent(abstractCount.value, todayCount.value))
const importedTodayCount = computed(() => importedCount.value)
const latestSourceLogs = computed(() => {
  const bySource = new Map()
  for (const log of [...todayLogs.value].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))) {
    const key = log.source || log.source_name || log.id
    if (!bySource.has(key)) bySource.set(key, log)
  }
  return [...bySource.values()]
})
const todayFetchStatus = computed(() => {
  const logs = latestSourceLogs.value
  if (!logs.length) return '今日未抓取'
  if (logs.some((item) => item.status === 'failed')) return '抓取失败'
  if (logs.some((item) => item.status === 'partial')) return '部分成功'
  return '抓取成功'
})
const recentFailureReason = computed(() => latestSourceLogs.value.find((item) => item.status === 'failed')?.message || '')
const fetching = computed(() => startingFetchTask.value || ['pending', 'running'].includes(fetchTaskStatus.value))
const trendPointRows = computed(() => {
  const rows = trendRows.value
  const max = Math.max(...rows.map((item) => item.count), 1)
  return rows.map((item, index) => {
    const x = rows.length <= 1 ? 150 : 20 + index * (260 / (rows.length - 1))
    const y = 100 - (item.count / max) * 72
    return { ...item, x: Math.round(x), y: Math.round(y) }
  })
})
const trendLinePoints = computed(() => trendPointRows.value.map((item) => `${item.x},${item.y}`).join(' '))
const trendAreaPoints = computed(() => {
  const points = trendPointRows.value
  if (!points.length) return ''
  return `20,108 ${points.map((item) => `${item.x},${item.y}`).join(' ')} 280,108`
})

async function loadDashboard() {
  const [allResp, favoriteResp, missingResp, todayResp, statsResp, logsResp, todayLogsResp, rulesResp] = await Promise.all([
    getPapers({ page_size: 1000 }),
    getPapers({ favorite: 'true', page_size: 1 }),
    getPapers({ abstract_missing: 'true', page_size: 1 }),
    getPapers({ date: latestDate.value, recommend_level: 'key', page_size: 1000, order: 'score' }),
    getPaperDashboardStats({ date: latestDate.value }),
    getFetchLogs({ page_size: 5 }),
    getFetchLogs({ date: todayText, page_size: 200 }),
    getScoringSettings(),
  ])

  const allRows = allResp.data.results || allResp.data
  const todayRows = todayResp.data.results || todayResp.data
  const stats = statsResp.data || {}
  todayPapers.value = todayRows
  keyThreshold.value = Number(rulesResp.data?.rules?.key_threshold ?? 30)
  keyPapersMax.value = Number(rulesResp.data?.rules?.key_papers_max ?? 8)
  recentLogs.value = logsResp.data.results || logsResp.data
  todayLogs.value = todayLogsResp.data.results || todayLogsResp.data
  todayCount.value = stats.total ?? todayResp.data.count ?? todayRows.length
  paperTotal.value = allResp.data.count ?? allRows.length
  favoriteCount.value = favoriteResp.data.count ?? 0
  missingAbstract.value = missingResp.data.count ?? 0
  doiCount.value = stats.doi_count ?? 0
  abstractCount.value = stats.abstract_count ?? 0
  importedCount.value = stats.zotero_imported_count ?? 0

  sourceRows.value = stats.source_rows || []
  directionRows.value = stats.direction_rows || []
  keywordRows.value = stats.keyword_rows || []
  await loadTrend()
}

async function loadLatestAvailableDate() {
  const resp = await getPaperDateCounts()
  const rows = Array.isArray(resp.data) ? resp.data : []
  const todayRow = rows.find((item) => item.date === todayText && item.count > 0)
  if (todayRow) {
    latestDate.value = todayText
    return
  }
  const latestRow = rows
    .filter((item) => item.date && item.count > 0)
    .sort((a, b) => String(a.date).localeCompare(String(b.date)))
    .at(-1)
  if (latestRow) {
    latestDate.value = latestRow.date
  }
}

async function autoFetch() {
  if (fetching.value) return
  startingFetchTask.value = true
  fetchTaskStatus.value = 'pending'
  fetchTaskMessage.value = '正在抓取'
  try {
    const resp = await startFetchDailyTask()
    startingFetchTask.value = false
    applyFetchTask(resp.data)
    startFetchPolling()
    ElMessage.info(resp.data.created ? '已启动后台抓取任务' : '已有抓取任务正在运行')
  } catch (error) {
    const recovered = await checkActiveFetchTask()
    startingFetchTask.value = false
    if (recovered) {
      ElMessage.warning('启动请求响应超时，但检测到后台抓取任务仍在运行')
      return
    }
    fetchTaskStatus.value = ''
    fetchTaskMessage.value = ''
    ElMessage.error(error.response?.data?.detail || error.message || '自动抓取失败')
  }
}

async function checkActiveFetchTask() {
  try {
    const resp = await getActiveFetchDailyTask()
    if (resp.data?.active) {
      startingFetchTask.value = false
      applyFetchTask(resp.data)
      startFetchPolling()
      return true
    }
    startingFetchTask.value = false
    fetchTaskId.value = ''
    fetchTaskStatus.value = ''
    fetchTaskMessage.value = ''
  } catch (error) {
    fetchTaskMessage.value = error.response?.data?.detail || error.message || ''
  }
  return false
}

function applyFetchTask(task) {
  fetchTaskId.value = task?.task_id || ''
  fetchTaskStatus.value = task?.status || ''
  fetchTaskMessage.value = task?.message || ''
  if (task?.report_date) {
    latestDate.value = task.report_date
  }
  if (fetchTaskStatus.value && !['pending', 'running'].includes(fetchTaskStatus.value)) {
    startingFetchTask.value = false
  }
}

function startFetchPolling() {
  stopFetchPolling()
  if (!fetchTaskId.value || !fetching.value) return
  fetchPollTimer = window.setInterval(pollFetchTask, 2000)
  pollFetchTask()
}

function stopFetchPolling() {
  if (fetchPollTimer) {
    window.clearInterval(fetchPollTimer)
    fetchPollTimer = null
  }
}

async function pollFetchTask() {
  if (!fetchTaskId.value) return
  try {
    const resp = await getFetchDailyTask(fetchTaskId.value)
    applyFetchTask(resp.data)
    if (!fetching.value) {
      stopFetchPolling()
      await loadDashboard()
      if (resp.data.status === 'success') {
        ElMessage.success(`自动抓取完成：新入库 ${resp.data.new_count} 篇，已存在 ${resp.data.duplicate_count} 篇`)
      } else if (resp.data.status === 'failed') {
        ElMessage.error(resp.data.message || '自动抓取失败')
      }
    }
  } catch (error) {
    stopFetchPolling()
    fetchTaskStatus.value = ''
    ElMessage.error(error.response?.data?.detail || error.message || '查询抓取任务失败')
  }
}

async function loadTrend() {
  const base = latestDate.value ? new Date(`${latestDate.value}T00:00:00`) : new Date()
  const start = new Date(base)
  start.setDate(base.getDate() - 6)
  const resp = await getPaperDateCounts({ year: base.getFullYear(), month: base.getMonth() + 1 })
  const counts = Object.fromEntries(resp.data.map((item) => [item.date, item.count]))
  const rows = Array.from({ length: 7 }, (_, index) => {
    const d = new Date(start)
    d.setDate(start.getDate() + index)
    const date = formatDate(d)
    return { date, label: `${d.getMonth() + 1}/${d.getDate()}`, count: counts[date] || 0 }
  })
  const max = Math.max(...rows.map((item) => item.count), 1)
  trendRows.value = rows.map((item) => ({ ...item, height: Math.max(8, Math.round((item.count / max) * 100)) }))
}

function buildRank(values, limit) {
  const map = new Map()
  values.filter(Boolean).forEach((value) => map.set(value, (map.get(value) || 0) + 1))
  const rows = Array.from(map, ([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count).slice(0, limit)
  const max = Math.max(...rows.map((item) => item.count), 1)
  return rows.map((item) => ({ ...item, percent: Math.max(8, Math.round((item.count / max) * 100)) }))
}

function cleanJournal(value) {
  return String(value || 'Other').replace(/^ScienceDirect Publication:\s*/i, '')
}

function formatPaperDate(value) {
  if (!value) return '未知'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value).slice(0, 10) : formatDate(date)
}

function publicationDateLabel(paper) {
  if (!paper.published_date) return '期刊日期未知'
  return `${paper.published_date > todayText ? '期刊预标日期' : '期刊日期'} ${paper.published_date}`
}

function scorePaper(paper) {
  return Number(paper.recommend_score || 0)
}

function percent(value, total) {
  if (!total) return 0
  return Math.round((value / total) * 100)
}

function truncate(value, length) {
  const text = String(value || '')
  return text.length > length ? `${text.slice(0, length)}...` : text
}

function openPaper(paper) {
  if (paper.url) window.open(paper.url, '_blank', 'noopener,noreferrer')
}

function formatDate(value) {
  const y = value.getFullYear()
  const m = String(value.getMonth() + 1).padStart(2, '0')
  const d = String(value.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

onMounted(async () => {
  await loadLatestAvailableDate()
  await loadDashboard()
  await checkActiveFetchTask()
})

onBeforeUnmount(() => {
  stopFetchPolling()
})
</script>

<style scoped>
.home-page {
  height: 100%;
  overflow-y: auto;
}

.home-summary {
  display: grid;
  gap: 16px;
  margin-bottom: 18px;
}

.summary-card {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border-radius: 14px;
  background: linear-gradient(135deg, #fff, rgba(238, 248, 255, 0.92));
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.summary-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: var(--accent);
}

.summary-card :deep(.el-card__body) {
  min-height: 68px;
  padding: 16px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.summary-card-label {
  color: #64748b;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.summary-card-number {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  white-space: nowrap;
}

.summary-card-number strong {
  color: #0b1f33;
  font-size: clamp(25px, 1.55vw, 30px);
  line-height: 1;
  font-weight: 900;
  letter-spacing: 0;
}

.summary-card-number em {
  color: var(--accent);
  font-style: normal;
  font-size: 14px;
  font-weight: 800;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
}

.daily-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
}

.analysis-panel {
  min-width: 0;
  min-height: 260px;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.07);
}

.analysis-panel .section-title {
  align-items: flex-start;
}

.analysis-panel .section-title h3 {
  font-size: 19px;
}

.analysis-panel .rank-row {
  grid-template-columns: minmax(92px, 42%) minmax(90px, 1fr) 38px;
  gap: 8px;
  font-size: 13px;
}

.analysis-panel .rank-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-rank {
  margin-top: 22px;
}

.trend-line-card {
  display: grid;
  gap: 10px;
  padding-top: 8px;
}

.trend-line-card svg {
  width: 100%;
  height: 148px;
  overflow: visible;
}

.trend-area {
  fill: rgba(47, 140, 255, 0.08);
  stroke: none;
}

.trend-line-path {
  fill: none;
  stroke: #2f8cff;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.trend-line-card circle {
  fill: #fff;
  stroke: #25d6c8;
  stroke-width: 3;
}

.trend-labels {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}

.trend-labels div {
  display: grid;
  gap: 3px;
  justify-items: center;
  color: #64748b;
  font-size: 12px;
}

.trend-labels strong {
  color: #0b1f33;
  font-size: 14px;
}

.bar-fill.violet {
  background: linear-gradient(90deg, #7c6cff, #2f8cff);
}

.bar-fill.green {
  background: linear-gradient(90deg, #22c55e, #25d6c8);
}

.paper-focus,
.status-panel {
  min-height: 360px;
}

.paper-focus {
  grid-column: span 3;
}

.status-panel {
  grid-column: span 1;
}

.focus-list {
  display: grid;
  gap: 12px;
}

.focus-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  padding: 13px 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(248, 251, 255, 0.92));
}

.focus-index {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, #2f8cff, #25d6c8);
  font-weight: 900;
}

.focus-body h4 {
  margin: 1px 0 7px;
  color: #155bd4;
  font-size: 17px;
  line-height: 1.4;
  cursor: pointer;
}

.focus-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.focus-title-row h4 {
  flex: 1;
}

.focus-body h4:hover {
  text-decoration: underline;
}

.focus-meta {
  margin: 0 0 7px;
  color: #64748b;
  font-size: 14px;
}

.focus-hit {
  margin: 0 0 7px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}

.focus-abstract {
  margin: 0;
  color: #344054;
  line-height: 1.65;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.status-cell {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(47, 140, 255, 0.14);
  background: rgba(238, 248, 255, 0.72);
}

.status-cell span {
  display: block;
  color: #64748b;
  font-size: 14px;
  font-weight: 700;
}

.status-cell strong {
  display: block;
  margin-top: 8px;
  color: #0b1f33;
  font-size: 24px;
  font-weight: 900;
}

.log-list {
  display: grid;
  gap: 10px;
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-actions a {
  color: #b42318;
  font-size: 13px;
}

.log-row {
  display: grid;
  grid-template-columns: 78px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.log-row span {
  min-width: 0;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-row em {
  color: #64748b;
  font-style: normal;
  font-size: 13px;
}

.log-row .log-reason {
  grid-column: 2 / -1;
  color: #b42318;
  font-size: 12px;
}

@media (max-width: 1280px) {
  .summary-metrics {
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(190px, 1fr));
  }

  .analysis-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .daily-grid {
    grid-template-columns: 1fr;
  }

  .paper-focus,
  .status-panel {
    grid-column: 1 / -1;
  }
}

@media (min-width: 1281px) and (max-width: 1540px) {
  .summary-metrics {
    grid-template-columns: repeat(4, minmax(130px, 1fr));
    gap: 12px;
  }

  .summary-card :deep(.el-card__body) {
    padding: 14px 15px;
  }

  .summary-card-label {
    font-size: 14px;
  }

  .summary-card-number strong {
    font-size: 27px;
  }

}

@media (max-width: 900px) {
  .summary-metrics {
    grid-column: 1 / -1;
    grid-template-columns: 1fr;
  }

  .summary-actions {
    grid-column: 1 / -1;
  }

  .analysis-grid {
    grid-template-columns: 1fr;
  }
}
</style>
