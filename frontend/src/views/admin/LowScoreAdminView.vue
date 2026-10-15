<template>
  <AdminLayout title="低分条目管理">
    <div class="admin-metrics">
      <div class="mini-metric"><span>当前显示</span><strong>{{ rows.length }}</strong></div>
      <div class="mini-metric"><span>总数</span><strong>{{ total }}</strong></div>
      <div class="mini-metric"><span>已选</span><strong>{{ selectedRows.length }}</strong></div>
      <div class="mini-metric danger"><span>低分阈值</span><strong>{{ lowScoreThreshold }}</strong></div>
    </div>

    <div class="filter-panel">
      <el-radio-group v-model="historyScope" @change="changeHistoryScope">
        <el-radio-button label="recent">最近 90 天</el-radio-button>
        <el-radio-button label="all">全部历史</el-radio-button>
      </el-radio-group>
      <el-input-number v-model="filters.max_score" :min="0" placeholder="推荐分数小于" class="filter-item" />
      <el-select v-model="filters.recommend_level" clearable placeholder="推荐等级" class="filter-item">
        <el-option label="重点推荐" value="key" />
        <el-option label="一般推荐" value="normal" />
        <el-option label="弱相关" value="weak" />
        <el-option label="低相关" value="low" />
      </el-select>
      <el-input v-model="filters.journal" clearable placeholder="期刊" class="filter-item" @keyup.enter="load" />
      <el-input v-model="filters.source" clearable placeholder="RSS 来源" class="filter-item" @keyup.enter="load" />
      <el-date-picker
        v-model="publishedRange"
        type="daterange"
        range-separator="至"
        start-placeholder="发布时间起"
        end-placeholder="发布时间止"
        value-format="YYYY-MM-DD"
        class="filter-item date-range"
      />
      <el-select v-model="filters.soft_deleted" clearable placeholder="软删除状态" class="filter-item status-select">
        <el-option label="未软删除" value="false" />
        <el-option label="已软删除" value="true" />
      </el-select>
      <el-select v-model="filters.report_candidate" clearable placeholder="日报候选" class="filter-item status-select">
        <el-option label="进入日报候选" value="true" />
        <el-option label="未进入日报候选" value="false" />
      </el-select>
      <el-button type="primary" @click="load">筛选</el-button>
      <el-button plain @click="resetFilters">重置筛选</el-button>
      <div class="filter-actions">
        <el-button plain :disabled="!selectedRows.length" @click="bulkRescore">批量重新评分</el-button>
        <el-button plain :disabled="!selectedRows.length" @click="bulkRestore">批量恢复</el-button>
        <el-button type="danger" plain :disabled="!selectedRows.length" @click="bulkSoftDelete">批量软删除</el-button>
      </div>
    </div>

    <el-table :data="rows" border class="admin-table" @selection-change="selectedRows = $event">
      <el-table-column type="selection" width="46" />
      <el-table-column prop="title" label="标题" min-width="280" show-overflow-tooltip />
      <el-table-column prop="journal" label="期刊" min-width="160" show-overflow-tooltip />
      <el-table-column prop="published_date" label="发布时间" width="110" />
      <el-table-column prop="recommend_score" label="推荐分数" width="100" sortable />
      <el-table-column prop="recommend_level" label="推荐等级" width="110">
        <template #default="{ row }"><el-tag :type="levelType(row.recommend_level)">{{ levelText(row.recommend_level) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="命中字段" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ formatMatchedFields(row.matched_fields) }}</template>
      </el-table-column>
      <el-table-column label="分数明细" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ formatScoreDetail(row.score_detail) }}</template>
      </el-table-column>
      <el-table-column prop="is_soft_deleted" label="软删除" width="90">
        <template #default="{ row }"><el-tag :type="row.is_soft_deleted ? 'danger' : 'info'">{{ row.is_soft_deleted ? '是' : '否' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="入库时间" width="155">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link @click="showDetail(row)">详情</el-button>
          <el-button link @click="singleRescore(row)">重评</el-button>
          <el-button link type="danger" @click="singleSoftDelete(row)">软删</el-button>
          <el-button v-if="row.is_soft_deleted" link @click="singleRestore(row)">恢复</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="admin-pagination"
      layout="prev, pager, next, total"
      :total="total"
      :page-size="pageSize"
      v-model:current-page="page"
      @current-change="load"
    />

    <el-drawer v-model="drawerVisible" title="低分条目详情" size="46%">
      <div v-if="current" class="detail-block">
        <h3>{{ current.title }}</h3>
        <p class="muted">{{ current.journal }} · {{ current.published_date || '未知日期' }} · {{ current.doi || '无 DOI' }}</p>
        <el-divider />
        <h4>摘要</h4>
        <p>{{ current.abstract || '暂无摘要' }}</p>
        <h4>命中字段</h4>
        <pre>{{ pretty(current.matched_fields) }}</pre>
        <h4>分数明细</h4>
        <pre>{{ pretty(current.score_detail) }}</pre>
      </div>
    </el-drawer>
  </AdminLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminLayout from '../../components/AdminLayout.vue'
import {
  bulkRescorePapers,
  bulkRestorePapers,
  bulkSoftDeletePapers,
  getLowScorePapers,
  rescorePaper,
  restorePaper,
  softDeletePaper,
} from '../../api/papers'
import { getScoringSettings } from '../../api/settings'

const rows = ref([])
const selectedRows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const lowScoreThreshold = ref(10)
const historyScope = ref('recent')
const publishedRange = ref([])
const drawerVisible = ref(false)
const current = ref(null)

const filters = reactive({
  max_score: 10,
  recommend_level: '',
  journal: '',
  source: '',
  soft_deleted: 'false',
  report_candidate: '',
})

async function load() {
  const params = { page: page.value, page_size: pageSize, history_scope: historyScope.value }
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) params[key] = value
  })
  if (publishedRange.value?.length === 2) {
    params.published_start = publishedRange.value[0]
    params.published_end = publishedRange.value[1]
  }
  const resp = await getLowScorePapers(params)
  rows.value = resp.data.results || resp.data
  total.value = resp.data.count ?? rows.value.length
  selectedRows.value = []
}

async function loadRules() {
  const resp = await getScoringSettings()
  lowScoreThreshold.value = resp.data.rules.low_score_threshold
  filters.max_score = resp.data.rules.low_score_threshold
}

function resetFilters() {
  Object.assign(filters, {
    max_score: lowScoreThreshold.value,
    recommend_level: '',
    journal: '',
    source: '',
    soft_deleted: 'false',
    report_candidate: '',
  })
  publishedRange.value = []
  historyScope.value = 'recent'
  page.value = 1
  load()
}

function changeHistoryScope() {
  page.value = 1
  load()
}

async function confirmBatch(actionName, handler) {
  await ElMessageBox.confirm(`确认对选中的 ${selectedRows.value.length} 篇文献执行“${actionName}”？`, `${actionName}确认`, { type: 'warning' })
  await handler(selectedRows.value.map((row) => row.id))
  ElMessage.success(`已完成${actionName}`)
  await load()
}

function bulkSoftDelete() {
  return confirmBatch('批量软删除', bulkSoftDeletePapers)
}

function bulkRestore() {
  return confirmBatch('批量恢复', bulkRestorePapers)
}

function bulkRescore() {
  return confirmBatch('批量重新评分', bulkRescorePapers)
}

async function singleSoftDelete(row) {
  await softDeletePaper(row.id)
  ElMessage.success('已软删除')
  await load()
}

async function singleRestore(row) {
  await restorePaper(row.id)
  ElMessage.success('已恢复')
  await load()
}

async function singleRescore(row) {
  await rescorePaper(row.id)
  ElMessage.success('已重新评分')
  await load()
}

function showDetail(row) {
  current.value = row
  drawerVisible.value = true
}

function levelText(level) {
  return { key: '重点推荐', normal: '一般推荐', weak: '弱相关', low: '低相关' }[level] || level || '-'
}

function levelType(level) {
  return { key: 'primary', normal: 'success', weak: 'warning', low: 'info' }[level] || 'info'
}

function formatMatchedFields(value) {
  if (!value || !Object.keys(value).length) return '无命中'
  return Object.entries(value)
    .map(([key, fields]) => `${key}: ${(fields || []).join('/')}`)
    .join('；')
}

function formatScoreDetail(value) {
  const items = value?.items || []
  if (!items.length) return '无明细'
  return items.map((item) => `${item.name || item.type}+${item.score}`).join('；')
}

function pretty(value) {
  return JSON.stringify(value || {}, null, 2)
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (item) => String(item).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(async () => {
  await loadRules()
  await load()
})
</script>

<style scoped>
.date-range {
  max-width: 260px;
}

.admin-pagination {
  margin: 14px 0 0 auto;
}

.detail-block {
  color: #334155;
  line-height: 1.7;
}

.detail-block h3 {
  margin: 0;
  color: var(--deep-blue);
}

.detail-block pre {
  white-space: pre-wrap;
  padding: 12px;
  border-radius: 12px;
  background: #f6f9fd;
  color: #334155;
}
</style>
