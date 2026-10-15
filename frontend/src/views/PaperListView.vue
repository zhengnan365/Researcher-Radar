<template>
  <div class="page workbench fade-in">
    <div class="paper-layout" :class="{ 'is-right-collapsed': rightPanelCollapsed }">
      <section class="paper-main">
        <div class="toolbar workbench-toolbar glass-card">
          <div class="toolbar-row filter-row">
            <el-input v-model="filters.search" placeholder="搜索标题/作者/DOI" clearable class="search-filter" @keyup.enter="applyFilters" @clear="applyFilters" />
            <el-select v-model="filters.direction" placeholder="研究方向" clearable class="direction-filter">
              <el-option v-for="item in directions" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <el-select v-model="filters.keyword" placeholder="关键词" clearable class="keyword-filter">
              <el-option v-for="item in keywords" :key="item.id" :label="item.keyword" :value="item.id" />
            </el-select>
            <el-select v-model="filters.journal" placeholder="期刊" clearable filterable class="journal-filter">
              <el-option v-for="name in journalOptions" :key="name" :label="name" :value="name" />
            </el-select>
            <el-select v-model="filters.recommend_level" placeholder="推荐等级" clearable class="level-filter">
              <el-option label="重点推荐" value="key" />
              <el-option label="一般推荐" value="normal" />
              <el-option label="弱相关" value="weak" />
              <el-option label="低相关" value="low" />
            </el-select>
            <el-switch v-model="favoriteOnly" active-text="只看收藏" />
            <el-switch v-model="importedOnly" active-text="已导入 Zotero" />
            <el-button type="primary" @click="applyFilters">搜索</el-button>
            <el-button @click="clearDate">全部日期</el-button>
          </div>
          <div class="toolbar-row action-row">
            <el-button @click="toggleSelectCurrentPage">{{ allCurrentPageSelected ? '取消本页选择' : '选择本页' }}</el-button>
            <el-button plain :loading="abstractUpdating" @click="updateMissingAbstracts">更新摘要</el-button>
            <el-button type="primary" :disabled="!selectedPapers.length" @click="openBatchZoteroImport">
              批量导入 Zotero
            </el-button>
            <span v-if="selectedPapers.length" class="selected-count">已选 {{ selectedPapers.length }} 篇</span>
          </div>
        </div>

        <div v-loading="listLoading" class="paper-scroll">
          <PaperCard
            v-for="paper in papers"
            :key="paper.id"
            :paper="paper"
            show-select
            :selected="selectedPaperIds.includes(paper.id)"
            :irrelevant-loading="irrelevantLoadingIds.has(paper.id)"
            @detail="openDetail"
            @ai-read="openAiRead"
            @toggle-favorite="toggleFavorite"
            @import-zotero="openZoteroImport"
            @toggle-select="togglePaperSelection"
            @mark-irrelevant="markIrrelevant"
          />
          <el-empty v-if="!papers.length" description="暂无文献" />
          <el-pagination
            class="bottom-pagination"
            layout="prev, pager, next, total"
            :total="total"
            :page-size="pageSize"
            v-model:current-page="page"
            @current-change="load"
          />
        </div>
      </section>

      <aside class="calendar-side">
        <button
          v-if="rightPanelCollapsed"
          type="button"
          class="right-panel-toggle"
          title="展开日历与统计"
          aria-label="展开日历与统计"
          :aria-expanded="false"
          @click="toggleRightPanel"
        >
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <el-card v-else shadow="never" class="calendar-card">
          <template #header>
            <div class="calendar-header">
              <strong>{{ monthTitle }}</strong>
              <button
                type="button"
                class="right-panel-toggle"
                title="折叠日历与统计"
                aria-label="折叠日历与统计"
                :aria-expanded="true"
                @click="toggleRightPanel"
              >
                <el-icon><ArrowRight /></el-icon>
              </button>
              <div class="calendar-controls">
                <button type="button" class="month-btn" @click="moveMonth(-1)">上一月</button>
                <button type="button" class="month-btn" @click="moveMonth(1)">下一月</button>
                <button type="button" class="today-btn" @click="goToday">今日</button>
              </div>
            </div>
          </template>
          <div class="calendar-grid">
            <div v-for="name in weekNames" :key="name" class="weekday">{{ name }}</div>
            <button
              v-for="day in calendarCells"
              :key="day.date"
              class="calendar-cell"
              :class="{ active: day.date === filters.date, outside: !day.currentMonth, today: day.date === todayText }"
              @click="selectDate(day.date)"
            >
              <span>{{ day.day }}</span>
              <em v-if="countFor(day.date)">{{ countFor(day.date) }}</em>
            </button>
          </div>
        </el-card>

        <el-card v-if="!rightPanelCollapsed" shadow="never" class="side-summary-card">
          <div class="side-summary-title">当日提要</div>
          <div class="side-summary-grid">
            <div><span>文献</span><strong>{{ total }}</strong></div>
            <div><span>收藏</span><strong>{{ selectedFavoriteCount }}</strong></div>
            <div><span>已入 Zotero</span><strong>{{ selectedImportedCount }}</strong></div>
            <div><span>待补摘要</span><strong>{{ selectedMissingAbstractCount }}</strong></div>
          </div>
        </el-card>

        <el-card v-if="!rightPanelCollapsed" shadow="never" class="side-summary-card score-distribution-card">
          <div class="side-summary-title">评分分布统计</div>
          <div v-if="scoreDistribution.total" class="distribution-list">
            <div v-for="bucket in scoreDistribution.buckets" :key="bucket.label" class="distribution-row">
              <div class="distribution-row-head">
                <strong>{{ bucket.label }} 分</strong>
                <span>{{ bucket.count }} 篇 · {{ bucket.ratio }}%</span>
              </div>
              <div class="distribution-bar"><i :style="{ width: `${bucket.ratio}%` }"></i></div>
              <em>{{ bucket.meaning }}</em>
            </div>
          </div>
          <el-empty v-else description="暂无评分分布" :image-size="72" />
        </el-card>
      </aside>
    </div>

    <PaperDetailDialog
      v-model="detailVisible"
      :paper="currentPaper"
      :ai-read-request="aiReadRequest"
      :focus-ai="focusAi"
      @summary-updated="updatePaperSummary"
    />

    <el-dialog v-model="zoteroDialogVisible" title="导入 Zotero" width="620px" append-to-body>
      <el-form label-width="110px">
        <el-form-item label="文献标题">
          <div class="dialog-paper-title">{{ zoteroTargetPaper?.title }}</div>
        </el-form-item>
        <el-form-item label="建议分组">
          <el-tag class="tag-direction">{{ zoteroSuggestion.suggested_collection_name || '待分类文献' }}</el-tag>
          <span class="suggest-reason">{{ zoteroSuggestion.reason }}</span>
        </el-form-item>
        <el-form-item label="选择分组">
          <el-tree-select
            v-model="zoteroForm.collection_key"
            :data="zoteroCollectionTree"
            :props="{ label: 'label', children: 'children' }"
            node-key="value"
            check-strictly
            filterable
            clearable
            render-after-expand
            placeholder="选择 Zotero Collection"
            style="width: 360px"
          />
          <el-button class="refresh-zotero-btn" plain :loading="zoteroSuggesting" @click="refreshZoteroSuggestion">刷新建议</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="zoteroDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="zoteroImporting" @click="importToZotero">导入 Zotero</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchDialogVisible" title="批量导入 Zotero" width="980px" append-to-body>
      <div class="batch-toolbar">
        <el-radio-group v-model="batchMode">
          <el-radio-button label="auto">按每篇文献自动推荐分组</el-radio-button>
          <el-radio-button label="unified">统一导入到指定分组</el-radio-button>
        </el-radio-group>
        <el-tree-select
          v-if="batchMode === 'unified'"
          v-model="batchUnifiedCollectionKey"
          :data="zoteroCollectionTree"
          :props="{ label: 'label', children: 'children' }"
          node-key="value"
          check-strictly
          filterable
          clearable
          render-after-expand
          placeholder="统一选择 Zotero Collection"
          style="width: 320px"
        />
      </div>

      <el-table :data="batchRows" v-loading="batchSuggesting" max-height="440" border>
        <el-table-column label="文献" min-width="320" show-overflow-tooltip>
          <template #default="{ row }">
            <strong>{{ row.paper.title }}</strong>
            <div class="batch-row-meta">{{ cleanJournal(row.paper.journal) }} · {{ row.paper.published_date || '未知日期' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="目标分组" min-width="280">
          <template #default="{ row }">
            <el-tree-select
              v-model="row.collection_key"
              :data="zoteroCollectionTree"
              :props="{ label: 'label', children: 'children' }"
              node-key="value"
              check-strictly
              filterable
              clearable
              render-after-expand
              :disabled="batchMode === 'unified'"
              placeholder="待分类文献"
              style="width: 100%"
            />
            <div class="batch-row-meta">{{ row.reason || '无推荐结果时按待分类文献处理' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="150">
          <template #default="{ row }">
            <el-tag v-if="row.status" :type="batchStatusType(row.status)" effect="light">{{ batchStatusText(row.status) }}</el-tag>
            <span v-else class="muted">待处理</span>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchImporting" :disabled="batchSuggesting || !batchRows.length" @click="importBatchToZotero">
          确认批量导入
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getDirections } from '../api/directions'
import { getKeywords } from '../api/keywords'
import {
  favoritePaper,
  getAbstractUpdateActive,
  getAbstractUpdateStatus,
  getPaperDateCounts,
  getPapers,
  markPaperIrrelevant,
  unfavoritePaper,
  updatePaperAbstracts,
} from '../api/papers'
import { getScoringDistribution } from '../api/settings'
import { getSources } from '../api/sources'
import { importPaperToZotero, suggestZoteroCollection } from '../api/zotero'
import PaperCard from '../components/PaperCard.vue'
import PaperDetailDialog from '../components/PaperDetailDialog.vue'

const pageSize = 20
const filters = reactive({ date: '', search: '', direction: '', keyword: '', journal: '', recommend_level: '' })
const favoriteOnly = ref(false)
const importedOnly = ref(false)
const rightPanelCollapsed = ref(readRightPanelCollapsed())
const calendarDate = ref(new Date())
const dateCounts = ref({})
const papers = ref([])
const listLoading = ref(false)
const total = ref(0)
const page = ref(1)
const directions = ref([])
const keywords = ref([])
const sources = ref([])
const detailVisible = ref(false)
const currentPaper = ref(null)
const aiReadRequest = ref(0)
const focusAi = ref(false)
const selectedFavoriteCount = ref(0)
const selectedImportedCount = ref(0)
const selectedMissingAbstractCount = ref(0)
const scoreDistribution = ref({ total: 0, buckets: [] })
const zoteroDialogVisible = ref(false)
const zoteroImporting = ref(false)
const zoteroSuggesting = ref(false)
const zoteroTargetPaper = ref(null)
const zoteroCollections = ref([])
const zoteroSuggestion = ref({})
const zoteroForm = reactive({ collection_key: '' })
const selectedPaperIds = ref([])
const irrelevantLoadingIds = ref(new Set())
const batchDialogVisible = ref(false)
const batchMode = ref('auto')
const batchRows = ref([])
const batchSuggesting = ref(false)
const batchImporting = ref(false)
const batchUnifiedCollectionKey = ref('')
const abstractUpdating = ref(false)
const abstractTaskId = ref('')
const abstractTaskStatus = ref('')
const abstractTaskMessage = ref('')
let abstractPollTimer = null
let listRequestId = 0
let dateCountsRequestId = 0
const weekNames = ['日', '一', '二', '三', '四', '五', '六']
const todayText = formatDate(new Date())

function readRightPanelCollapsed() {
  try {
    return window.localStorage.getItem('literature-right-panel-collapsed') === 'true'
  } catch {
    return false
  }
}

function toggleRightPanel() {
  rightPanelCollapsed.value = !rightPanelCollapsed.value
  try {
    window.localStorage.setItem('literature-right-panel-collapsed', String(rightPanelCollapsed.value))
  } catch {
    // The panel still works when browser storage is unavailable.
  }
}

const monthTitle = computed(() => {
  const d = calendarDate.value
  return `${d.getFullYear()}年${String(d.getMonth() + 1).padStart(2, '0')}月`
})

const monthKey = computed(() => `${calendarDate.value.getFullYear()}-${calendarDate.value.getMonth() + 1}`)
const zoteroCollectionTree = computed(() => buildCollectionTree(zoteroCollections.value))
const selectedPapers = computed(() => papers.value.filter((paper) => selectedPaperIds.value.includes(paper.id)))
const allCurrentPageSelected = computed(() => papers.value.length > 0 && papers.value.every((paper) => selectedPaperIds.value.includes(paper.id)))
const journalOptions = computed(() => {
  const names = sources.value
    .map((item) => cleanJournal(item.journal || item.name))
    .filter(Boolean)
  return [...new Set(names)].sort((a, b) => a.localeCompare(b))
})

function buildCollectionTree(collections) {
  const nodes = new Map()
  collections.forEach((item) => {
    nodes.set(item.key, {
      ...item,
      value: item.key,
      label: item.name,
      fullLabel: item.path || item.name,
      children: [],
    })
  })
  const roots = []
  nodes.forEach((node) => {
    const parent = node.parent && nodes.get(node.parent)
    if (parent) parent.children.push(node)
    else roots.push(node)
  })
  const sortRows = (rows) => {
    rows.sort((a, b) => String(a.label).localeCompare(String(b.label), 'zh-Hans-CN', { numeric: true }))
    rows.forEach((row) => sortRows(row.children))
  }
  sortRows(roots)
  return roots
}

const calendarCells = computed(() => {
  const year = calendarDate.value.getFullYear()
  const month = calendarDate.value.getMonth()
  const first = new Date(year, month, 1)
  const start = new Date(first)
  start.setDate(first.getDate() - first.getDay())
  return Array.from({ length: 42 }, (_, index) => {
    const d = new Date(start)
    d.setDate(start.getDate() + index)
    return {
      date: formatDate(d),
      day: d.getDate(),
      currentMonth: d.getMonth() === month,
    }
  })
})

async function load() {
  const requestId = ++listRequestId
  const params = { ...filters, order: 'score', page: page.value, page_size: pageSize }
  Object.keys(params).forEach((key) => {
    if (params[key] === '' || params[key] === null || params[key] === undefined) delete params[key]
  })
  if (favoriteOnly.value) params.favorite = 'true'
  if (importedOnly.value) params.zotero_imported = 'true'
  const base = filters.date ? { date: filters.date } : {}
  listLoading.value = true
  try {
    const [resp, favoriteResp, importedResp, missingResp, distributionResp] = await Promise.all([
      getPapers(params),
      getPapers({ ...base, favorite: 'true', page_size: 1 }),
      getPapers({ ...base, zotero_imported: 'true', page_size: 1 }),
      getPapers({ ...base, abstract_missing: 'true', page_size: 1 }),
      getScoringDistribution(base),
    ])
    if (requestId !== listRequestId) return
    papers.value = resp.data.results || resp.data
    selectedPaperIds.value = selectedPaperIds.value.filter((id) => papers.value.some((paper) => paper.id === id))
    total.value = resp.data.count ?? papers.value.length
    selectedFavoriteCount.value = favoriteResp.data.count ?? 0
    selectedImportedCount.value = importedResp.data.count ?? 0
    selectedMissingAbstractCount.value = missingResp.data.count ?? 0
    scoreDistribution.value = distributionResp.data
  } catch (error) {
    if (requestId === listRequestId) ElMessage.error(error.response?.data?.detail || '读取文献列表失败')
  } finally {
    if (requestId === listRequestId) listLoading.value = false
  }
}

async function loadDateCounts() {
  const requestId = ++dateCountsRequestId
  const d = calendarDate.value
  const params = {
    year: d.getFullYear(),
    month: d.getMonth() + 1,
    direction: filters.direction,
    keyword: filters.keyword,
    journal: filters.journal,
  }
  if (favoriteOnly.value) params.favorite = 'true'
  if (importedOnly.value) params.zotero_imported = 'true'
  try {
    const resp = await getPaperDateCounts(params)
    if (requestId === dateCountsRequestId) dateCounts.value = Object.fromEntries(resp.data.map((item) => [item.date, item.count]))
  } catch (error) {
    if (requestId === dateCountsRequestId) ElMessage.error(error.response?.data?.detail || '读取日历统计失败')
  }
}

function applyFilters() {
  page.value = 1
  load()
  loadDateCounts()
}

function openDetail(paper) {
  currentPaper.value = paper
  focusAi.value = false
  detailVisible.value = true
}

function openAiRead(paper) {
  currentPaper.value = paper
  focusAi.value = true
  detailVisible.value = true
  aiReadRequest.value += 1
}

function updatePaperSummary(updatedPaper) {
  const paper = papers.value.find((item) => item.id === updatedPaper.id)
  if (!paper) return
  paper.ai_summary = updatedPaper.ai_summary
  paper.ai_summary_model = updatedPaper.ai_summary_model
  paper.ai_summarized_at = updatedPaper.ai_summarized_at
}

async function toggleFavorite(paper) {
  if (paper.is_favorite) await unfavoritePaper(paper.id)
  else await favoritePaper(paper.id)
  await Promise.all([load(), loadDateCounts()])
}

async function markIrrelevant(paper) {
  if (irrelevantLoadingIds.value.has(paper.id)) return
  irrelevantLoadingIds.value = new Set([...irrelevantLoadingIds.value, paper.id])
  try {
    await markPaperIrrelevant(paper.id)
    ElMessage.success('已设为 0 分并从列表隐藏；记录仍保留用于去重')
    await Promise.all([load(), loadDateCounts()])
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '标记不相关失败')
  } finally {
    const next = new Set(irrelevantLoadingIds.value)
    next.delete(paper.id)
    irrelevantLoadingIds.value = next
  }
}

function togglePaperSelection(paper) {
  if (selectedPaperIds.value.includes(paper.id)) {
    selectedPaperIds.value = selectedPaperIds.value.filter((id) => id !== paper.id)
  } else {
    selectedPaperIds.value = [...selectedPaperIds.value, paper.id]
  }
}

function toggleSelectCurrentPage() {
  if (allCurrentPageSelected.value) {
    const currentIds = new Set(papers.value.map((paper) => paper.id))
    selectedPaperIds.value = selectedPaperIds.value.filter((id) => !currentIds.has(id))
  } else {
    selectedPaperIds.value = [...new Set([...selectedPaperIds.value, ...papers.value.map((paper) => paper.id)])]
  }
}

async function updateMissingAbstracts() {
  const hasSelection = selectedPapers.value.length > 0
  const targets = hasSelection ? selectedPapers.value.filter((paper) => !paper.abstract) : []
  if (hasSelection && !targets.length) {
    ElMessage.info('所选文献均已有摘要')
    return
  }
  if (!hasSelection && !filters.date) {
    ElMessage.info('请先选择一个日期，或勾选需要更新摘要的文献')
    return
  }
  abstractUpdating.value = true
  try {
    const resp = await updatePaperAbstracts({
      paper_ids: hasSelection ? targets.map((paper) => paper.id) : [],
      date: hasSelection ? '' : filters.date,
      max_items: hasSelection ? targets.length : 'all',
    })
    abstractTaskId.value = resp.data.task_id
    abstractTaskStatus.value = resp.data.status
    abstractTaskMessage.value = resp.data.message || '正在更新摘要'
    ElMessage.success(resp.data.created === false ? '已有摘要更新任务正在运行' : '摘要更新任务已启动')
    startAbstractPolling()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '更新摘要失败')
    abstractUpdating.value = false
  }
}

async function restoreAbstractTaskState() {
  try {
    const resp = await getAbstractUpdateActive()
    if (resp.data.active) {
      abstractTaskId.value = resp.data.task_id
      abstractTaskStatus.value = resp.data.status
      abstractTaskMessage.value = resp.data.message || '正在更新摘要'
      abstractUpdating.value = true
      startAbstractPolling()
    } else {
      stopAbstractPolling()
      abstractUpdating.value = false
    }
  } catch {
    stopAbstractPolling()
    abstractUpdating.value = false
  }
}

function startAbstractPolling() {
  stopAbstractPolling()
  abstractUpdating.value = true
  pollAbstractTask()
  abstractPollTimer = window.setInterval(pollAbstractTask, 2500)
}

function stopAbstractPolling() {
  if (abstractPollTimer) {
    window.clearInterval(abstractPollTimer)
    abstractPollTimer = null
  }
}

async function pollAbstractTask() {
  if (!abstractTaskId.value) {
    await restoreAbstractTaskState()
    return
  }
  try {
    const resp = await getAbstractUpdateStatus(abstractTaskId.value)
    abstractTaskStatus.value = resp.data.status
    abstractTaskMessage.value = resp.data.message || ''
    if (!['pending', 'running'].includes(resp.data.status)) {
      stopAbstractPolling()
      abstractUpdating.value = false
      if (resp.data.status === 'success') {
        ElMessage.success(resp.data.message || '摘要更新完成')
      } else {
        ElMessage.error(resp.data.message || '摘要更新失败')
      }
      abstractTaskId.value = ''
      await Promise.all([load(), loadDateCounts()])
    }
  } catch (error) {
    stopAbstractPolling()
    abstractUpdating.value = false
    ElMessage.error(error.response?.data?.detail || '摘要更新状态查询失败')
  } finally {
  }
}

async function openZoteroImport(paper) {
  zoteroTargetPaper.value = paper
  zoteroSuggestion.value = {}
  zoteroCollections.value = []
  zoteroForm.collection_key = ''
  zoteroDialogVisible.value = true
  await refreshZoteroSuggestion()
}

async function refreshZoteroSuggestion() {
  if (!zoteroTargetPaper.value) return
  zoteroSuggesting.value = true
  try {
    const resp = await suggestZoteroCollection({ paper_id: zoteroTargetPaper.value.id })
    zoteroSuggestion.value = resp.data
    zoteroCollections.value = resp.data.collections || []
    zoteroForm.collection_key = resp.data.suggested_collection_key || ''
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '获取 Zotero 分组失败')
  } finally {
    zoteroSuggesting.value = false
  }
}

async function importToZotero() {
  if (!zoteroTargetPaper.value) return
  const selectedCollection = zoteroCollections.value.find((item) => item.key === zoteroForm.collection_key)
  zoteroImporting.value = true
  try {
    await importPaperToZotero({
      paper_id: zoteroTargetPaper.value.id,
      collection_key: zoteroForm.collection_key,
      collection_name: selectedCollection?.path || selectedCollection?.name || zoteroSuggestion.value.suggested_collection_name || '',
    })
    ElMessage.success('已导入 Zotero')
    zoteroDialogVisible.value = false
    await Promise.all([load(), loadDateCounts()])
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '导入 Zotero 失败')
  } finally {
    zoteroImporting.value = false
  }
}

async function openBatchZoteroImport() {
  const targets = selectedPapers.value.filter((paper) => !paper.zotero_imported)
  if (!targets.length) {
    ElMessage.info('所选文献均已导入 Zotero')
    return
  }
  batchDialogVisible.value = true
  batchMode.value = 'auto'
  batchRows.value = targets.map((paper) => ({
    paper,
    collection_key: '',
    collection_name: '',
    reason: '',
    status: '',
    message: '',
  }))
  batchUnifiedCollectionKey.value = ''
  batchSuggesting.value = true
  try {
    const suggestions = await Promise.all(targets.map((paper) => suggestZoteroCollection({ paper_id: paper.id }).catch((error) => ({ error, paper }))))
    suggestions.forEach((resp, index) => {
      if (resp.error) {
        batchRows.value[index].reason = '推荐失败，将按待分类文献处理'
        return
      }
      const data = resp.data
      if (!zoteroCollections.value.length) zoteroCollections.value = data.collections || []
      batchRows.value[index].collection_key = data.suggested_collection_key || fallbackCollectionKey(data.collections || [])
      batchRows.value[index].collection_name = collectionNameByKey(batchRows.value[index].collection_key, data.collections || []) || data.suggested_collection_name || '待分类文献'
      batchRows.value[index].reason = data.reason || '按研究方向和关键词推荐'
    })
  } finally {
    batchSuggesting.value = false
  }
}

async function importBatchToZotero() {
  batchImporting.value = true
  const result = { created: 0, added_to_collection: 0, already_exists: 0, failed: 0 }
  try {
    for (const row of batchRows.value) {
      const collectionKey = batchMode.value === 'unified' ? batchUnifiedCollectionKey.value : row.collection_key
      const collectionName = collectionNameByKey(collectionKey, zoteroCollections.value) || row.collection_name || '待分类文献'
      try {
        const resp = await importPaperToZotero({
          paper_id: row.paper.id,
          collection_key: collectionKey,
          collection_name: collectionName,
        })
        row.status = resp.data.status || 'created'
        row.message = collectionName
        result[row.status] = (result[row.status] || 0) + 1
      } catch (error) {
        row.status = 'failed'
        row.message = error.response?.data?.detail || '导入失败'
        result.failed += 1
      }
    }
    ElMessage.success(`批量导入完成：新建 ${result.created || 0}，补充分组 ${result.added_to_collection || 0}，已存在 ${result.already_exists || 0}，失败 ${result.failed || 0}`)
    await Promise.all([load(), loadDateCounts()])
  } finally {
    batchImporting.value = false
  }
}

function selectDate(day) {
  filters.date = day
  calendarDate.value = new Date(`${day}T00:00:00`)
  page.value = 1
  load()
}

function clearDate() {
  filters.date = ''
  page.value = 1
  load()
}

function goToday() {
  const today = new Date()
  calendarDate.value = today
  filters.date = formatDate(today)
  page.value = 1
  load()
  loadDateCounts()
}

function moveMonth(offset) {
  const d = new Date(calendarDate.value)
  d.setMonth(d.getMonth() + offset)
  calendarDate.value = d
  loadDateCounts()
}

function countFor(day) {
  return dateCounts.value[day] || 0
}

function fallbackCollectionKey(collections = []) {
  const fallback = collections.find((item) => /待分类|未分类|inbox|to.?read/i.test(`${item.name || ''} ${item.path || ''}`))
  return fallback?.key || ''
}

function collectionNameByKey(key, collections = []) {
  if (!key) return ''
  const collection = collections.find((item) => item.key === key)
  return collection?.path || collection?.name || ''
}

function batchStatusType(status) {
  if (status === 'failed') return 'danger'
  if (status === 'already_exists') return 'info'
  if (status === 'added_to_collection') return 'warning'
  return 'success'
}

function batchStatusText(status) {
  const labels = {
    created: '新建成功',
    added_to_collection: '补充分组',
    already_exists: '已存在',
    failed: '失败',
  }
  return labels[status] || status
}

function cleanJournal(value) {
  return String(value || '').replace(/^ScienceDirect Publication:\s*/i, '').trim()
}

function formatDate(value) {
  const y = value.getFullYear()
  const m = String(value.getMonth() + 1).padStart(2, '0')
  const d = String(value.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

watch(favoriteOnly, applyFilters)
watch(importedOnly, applyFilters)
watch(() => [filters.direction, filters.keyword, filters.journal, filters.recommend_level], applyFilters)
watch(monthKey, loadDateCounts)

onMounted(async () => {
  const [dirResp, kwResp, sourceResp] = await Promise.all([
    getDirections({ page_size: 1000 }),
    getKeywords({ page_size: 1000 }),
    getSources({ page_size: 1000 }),
  ])
  filters.date = todayText
  calendarDate.value = new Date(`${filters.date}T00:00:00`)
  directions.value = dirResp.data.results || dirResp.data
  keywords.value = kwResp.data.results || kwResp.data
  sources.value = sourceResp.data.results || sourceResp.data
  await Promise.all([loadDateCounts(), load()])
  await restoreAbstractTaskState()
})

onBeforeUnmount(() => {
  stopAbstractPolling()
  listRequestId += 1
  dateCountsRequestId += 1
})
</script>

<style scoped>
.workbench {
  height: 100%;
  overflow: hidden;
}

.paper-layout {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(300px, 20vw, 380px);
  gap: 18px;
  align-items: stretch;
}

.paper-layout.is-right-collapsed {
  grid-template-columns: minmax(0, 1fr) 52px;
}

.paper-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.selected-count {
  color: #64748b;
  font-size: 14px;
  font-weight: 700;
}

.batch-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-bottom: 14px;
}

.batch-row-meta {
  margin-top: 5px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.workbench-toolbar {
  display: grid;
  gap: 9px;
  overflow: visible;
  margin-bottom: 14px;
  padding: 12px;
  border-radius: 22px;
  background: #fff;
  box-shadow: var(--shadow-blue);
  backdrop-filter: none;
  flex-shrink: 0;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.filter-row {
  flex-wrap: wrap;
}

.action-row {
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
}

.filter-row :deep(.el-button + .el-button) {
  margin-left: 0;
}

.search-filter {
  flex: 1.4 1 220px;
  width: auto;
  min-width: 180px;
}

.direction-filter {
  flex: 1 1 170px;
  width: auto;
  min-width: 145px;
}

.keyword-filter {
  flex: 0.9 1 150px;
  width: auto;
  min-width: 130px;
}

.journal-filter {
  flex: 1 1 180px;
  width: auto;
  min-width: 145px;
}

.level-filter {
  flex: 0.75 1 130px;
  width: auto;
  min-width: 112px;
}

.workbench-toolbar :deep(.el-input__wrapper),
.workbench-toolbar :deep(.el-select__wrapper),
.workbench-toolbar :deep(.el-input-number),
.workbench-toolbar :deep(.el-button) {
  height: 34px;
  min-height: 34px;
}

.workbench-toolbar :deep(.el-button) {
  min-width: 70px;
  padding: 0 10px;
  white-space: nowrap;
}

.workbench-toolbar :deep(.el-switch) {
  --el-switch-on-color: #38bdf8;
  min-width: 92px;
  white-space: nowrap;
}

.workbench-toolbar :deep(.el-switch__label) {
  margin-left: 5px;
  font-size: 13px;
}

.selected-count {
  white-space: nowrap;
}

@media (max-width: 1480px) {
  .paper-layout {
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 14px;
  }

  .calendar-header {
    gap: 10px;
  }

  .calendar-controls {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .workbench-toolbar {
    gap: 5px;
    padding: 10px;
  }

  .toolbar-row {
    gap: 6px;
  }

  .workbench-toolbar :deep(.el-button) {
    min-width: 56px;
    padding: 0 7px;
  }

  .workbench-toolbar :deep(.el-switch) {
    min-width: 82px;
  }
}

.paper-scroll {
  min-height: 0;
  overflow-y: auto;
  padding-right: 8px;
  padding-bottom: 12px;
}

.paper-scroll::-webkit-scrollbar {
  width: 10px;
}

.paper-scroll::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #93c5fd, #5eead4);
  border-radius: 999px;
}

.bottom-pagination {
  margin: 18px 0 4px;
  justify-content: flex-end;
}

.calendar-side {
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  padding-bottom: 12px;
}

.calendar-side :deep(.el-card) {
  backdrop-filter: none;
}

.is-right-collapsed .calendar-side {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  overflow: visible;
  padding: 4px;
  border: 1px solid rgba(59, 130, 246, 0.22);
  border-radius: 12px;
  background: rgba(248, 251, 255, 0.9);
}

.right-panel-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 1px solid rgba(47, 140, 255, 0.28);
  border-radius: 10px;
  background: #f5faff;
  color: #1d4ed8;
  font: inherit;
  font-size: 18px;
  cursor: pointer;
}

.right-panel-toggle:hover {
  background: #eaf4ff;
  border-color: rgba(47, 140, 255, 0.48);
}

.right-panel-toggle:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.calendar-side::-webkit-scrollbar {
  width: 8px;
}

.calendar-side::-webkit-scrollbar-thumb {
  background: rgba(147, 197, 253, 0.75);
  border-radius: 999px;
}

.calendar-card {
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.22);
  background:
    radial-gradient(circle at 20% 0%, rgba(59, 130, 246, 0.12), transparent 26%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.94) 0%, rgba(248, 251, 255, 0.96) 100%);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.09);
}

.calendar-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.calendar-header strong {
  min-width: 0;
  color: #0f172a;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: clamp(15px, 1vw, 18px);
}

.calendar-controls {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}

.calendar-controls button {
  width: 100%;
  min-width: 0;
  height: 38px;
  padding: 0 8px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  appearance: none;
  border-radius: 8px;
  font: inherit;
  font-size: 14px;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.month-btn {
  width: 100%;
  min-width: 0;
  margin: 0;
  box-sizing: border-box;
  border: 1px solid rgba(47, 140, 255, 0.28);
  color: #1d4ed8;
  background: linear-gradient(135deg, #f5faff, #eaf4ff);
  box-shadow: 0 5px 12px rgba(47, 140, 255, 0.08);
}

.month-btn:hover {
  color: #1558bd;
  background: linear-gradient(135deg, #eaf4ff, #dceeff);
  border-color: rgba(47, 140, 255, 0.48);
  box-shadow: 0 8px 16px rgba(47, 140, 255, 0.14);
  transform: translateY(-1px);
}

.today-btn {
  width: 100%;
  min-width: 0;
  margin: 0;
  box-sizing: border-box;
  border: 1px solid rgba(20, 184, 166, 0.34);
  color: #08756f;
  background: linear-gradient(135deg, #effdfa, #e2f8f5);
  box-shadow: 0 8px 18px rgba(20, 184, 166, 0.1);
}

.today-btn:hover {
  color: #075f5a;
  background: linear-gradient(135deg, #e2f8f5, #d4f4ef);
  border-color: rgba(20, 184, 166, 0.52);
  box-shadow: 0 10px 20px rgba(20, 184, 166, 0.16);
  transform: translateY(-1px);
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: clamp(4px, 0.35vw, 6px);
}

.weekday {
  color: #667085;
  text-align: center;
  font-size: 15px;
  padding: 4px 0 6px;
}

.calendar-cell {
  height: clamp(42px, 2.7vw, 50px);
  border: 1px solid #dce8f8;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 8px;
  padding: 5px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-start;
  cursor: pointer;
  color: #1f2a44;
  font-size: clamp(13px, 0.9vw, 15px);
  transition: transform 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.calendar-cell:hover {
  background: #e0f2fe;
  border-color: #38bdf8;
  transform: translateY(-1px);
}

.calendar-cell.outside {
  color: #a8b2c2;
  background: rgba(248, 250, 252, 0.72);
}

.calendar-cell.today {
  border-color: #14b8a6;
}

.calendar-cell.active {
  background: linear-gradient(135deg, #dcfce7, #dbeafe);
  color: #065f46;
  outline: 1px solid #14b8a6;
}

.calendar-cell em {
  align-self: flex-start;
  max-width: none;
  border-radius: 999px;
  padding: 1px 5px;
  background: linear-gradient(135deg, #0f766e, #2563eb);
  color: white;
  font-style: normal;
  font-size: 11px;
  line-height: 15px;
  font-weight: 800;
  overflow: visible;
  text-overflow: clip;
  white-space: nowrap;
}

.side-summary-card {
  margin-top: 12px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.18);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.08);
}

.side-summary-card :deep(.el-card__body) {
  padding: 16px 18px;
}

.side-summary-title {
  color: #0f172a;
  font-size: 17px;
  font-weight: 900;
}

.side-summary-date {
  display: none;
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.side-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 0;
}

.side-summary-grid div {
  padding: 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, #eff6ff, #f8fbff);
  border: 1px solid rgba(59, 130, 246, 0.12);
}

.side-summary-grid span {
  display: block;
  color: #64748b;
  font-size: 13px;
}

.side-summary-grid strong {
  display: block;
  margin-top: 4px;
  color: #0f172a;
  font-size: 22px;
}

.distribution-list {
  display: grid;
  gap: 9px;
  margin-top: 14px;
}

.distribution-row {
  padding: 9px 10px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.96), rgba(248, 251, 255, 0.92));
  border: 1px solid rgba(59, 130, 246, 0.13);
}

.distribution-row-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #0f172a;
  font-size: 13px;
}

.distribution-bar {
  height: 7px;
  margin: 7px 0 5px;
  border-radius: 999px;
  background: #e2edf8;
  overflow: hidden;
}

.distribution-bar i {
  display: block;
  height: 100%;
  min-width: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, #2f8cff, #25d6c8);
}

.distribution-row em {
  color: #64748b;
  font-style: normal;
  font-size: 12px;
  line-height: 1.35;
}

.dialog-paper-title {
  color: #0f172a;
  font-weight: 800;
  line-height: 1.5;
}

.suggest-reason {
  margin-left: 10px;
  color: #64748b;
}

.refresh-zotero-btn {
  margin-left: 10px;
}

@media (max-width: 1180px) {
  .paper-layout {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
  }

  .paper-layout.is-right-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }

  .calendar-side {
    display: block;
    max-height: 520px;
    order: 2;
    padding-right: 0;
  }

  .is-right-collapsed .calendar-side {
    order: -1;
    justify-content: flex-end;
    height: 44px;
    max-height: none;
    padding: 0;
    border: 0;
    background: transparent;
  }

  .workbench {
    overflow-y: auto;
  }

  .paper-scroll {
    overflow: visible;
    padding-right: 0;
  }
}

@media (max-width: 980px) {
  .filter-row {
    align-items: stretch;
  }

  .filter-row > * {
    flex: 1 1 160px;
  }
}
</style>
