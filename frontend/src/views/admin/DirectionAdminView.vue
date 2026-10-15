<template>
  <AdminLayout title="研究方向管理">
    <div class="admin-metrics">
      <div class="mini-metric"><span>方向总数</span><strong>{{ total }}</strong></div>
      <div class="mini-metric"><span>当前显示</span><strong>{{ rows.length }}</strong></div>
      <div class="mini-metric"><span>启用方向</span><strong>{{ rows.filter((r) => r.enabled).length }}</strong></div>
      <div class="mini-metric"><span>停用方向</span><strong>{{ rows.filter((r) => !r.enabled).length }}</strong></div>
    </div>

    <div class="filter-panel">
      <el-input v-model="filters.search" clearable placeholder="搜索研究方向" class="filter-item search-input" @keyup.enter="load" />
      <el-select v-model="filters.enabled" clearable placeholder="启用状态" class="filter-item status-select">
        <el-option label="启用" value="true" />
        <el-option label="停用" value="false" />
      </el-select>
      <el-button type="primary" @click="load">筛选</el-button>
      <el-button plain @click="resetFilters">重置筛选</el-button>
      <div class="filter-actions">
        <el-button type="primary" @click="open()">新增研究方向</el-button>
        <el-button type="primary" @click="openBulk">批量添加</el-button>
        <el-button type="danger" plain :disabled="!selectedRows.length" @click="bulkRemove">批量删除</el-button>
      </div>
    </div>

    <el-table :data="rows" border class="admin-table" @selection-change="selectedRows = $event">
      <el-table-column type="selection" width="46" />
      <el-table-column prop="name_cn" label="研究方向" min-width="180" />
      <el-table-column prop="name_en" label="英文名称" min-width="220" show-overflow-tooltip />
      <el-table-column prop="direction_weight" width="166">
        <template #header><DirectionMetricLabel metric="relevance" /></template>
        <template #default="{ row }">{{ row.direction_weight }} · {{ relevanceLevelText(row.direction_weight) }}</template>
      </el-table-column>
      <el-table-column prop="priority" width="150">
        <template #header><DirectionMetricLabel metric="priority" /></template>
        <template #default="{ row }">{{ row.priority }} · {{ priorityLevelText(row.priority) }}</template>
      </el-table-column>
      <el-table-column prop="enabled" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button link @click="open(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" title="研究方向" width="620px" append-to-body>
      <el-form :model="form" label-width="126px">
        <el-form-item label="中文名称">
          <el-input v-model="form.name_cn" placeholder="请输入中文研究方向名称" />
        </el-form-item>
        <el-form-item label="英文名称">
          <el-input v-model="form.name_en" placeholder="可选，科研标签" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item>
          <template #label><DirectionMetricLabel metric="relevance" /></template>
          <div class="metric-setting">
            <el-input-number v-model="form.direction_weight" :min="1" :max="5" />
            <span>{{ relevanceLevelText(form.direction_weight) }}</span>
          </div>
        </el-form-item>
        <el-form-item>
          <template #label><DirectionMetricLabel metric="priority" /></template>
          <div class="metric-setting">
            <el-input-number v-model="form.priority" :min="1" :max="5" />
            <span>{{ priorityLevelText(form.priority) }}</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bulkVisible" title="批量添加研究方向" width="620px" append-to-body>
      <el-alert title="每行一个方向；可填“中文名称 | 英文名称 | 研究相关度 | 关注优先级”。仅填中文名称时使用下方统一设置。研究相关度影响评分，关注优先级影响排序。" type="info" :closable="false" show-icon class="bulk-tip" />
      <el-form :model="bulkForm" label-width="126px">
        <el-form-item label="启用"><el-switch v-model="bulkForm.enabled" /></el-form-item>
        <el-form-item>
          <template #label><DirectionMetricLabel metric="relevance" label="统一研究相关度" /></template>
          <div class="metric-setting">
            <el-input-number v-model="bulkForm.direction_weight" :min="1" :max="5" />
            <span>{{ relevanceLevelText(bulkForm.direction_weight) }}</span>
          </div>
        </el-form-item>
        <el-form-item>
          <template #label><DirectionMetricLabel metric="priority" label="统一关注优先级" /></template>
          <div class="metric-setting">
            <el-input-number v-model="bulkForm.priority" :min="1" :max="5" />
            <span>{{ priorityLevelText(bulkForm.priority) }}</span>
          </div>
        </el-form-item>
        <el-form-item label="粘贴模板" class="template-item">
          <div class="bulk-example">
            <span>每行一个方向；也可以只填写中文名称，使用上方统一设置。</span>
            <pre>热力循环设计与多目标优化 | Thermodynamic Cycle Design and Multi-objective Optimization | 4 | 4</pre>
          </div>
        </el-form-item>
        <el-form-item label="方向名称">
          <el-input v-model="bulkForm.names" type="textarea" :rows="9" placeholder="热力循环设计与多目标优化 | Thermodynamic Cycle Design and Multi-objective Optimization | 4 | 4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bulkVisible = false">取消</el-button>
        <el-button type="primary" :loading="bulkSaving" @click="saveBulk">批量添加</el-button>
      </template>
    </el-dialog>
  </AdminLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminLayout from '../../components/AdminLayout.vue'
import DirectionMetricLabel from '../../components/DirectionMetricLabel.vue'
import { bulkCreateDirections, bulkDeleteDirections, createDirection, deleteDirection, getDirections, updateDirection } from '../../api/directions'
import { priorityLevelText, relevanceLevelText } from '../../utils/directionMetrics'

const rows = ref([])
const selectedRows = ref([])
const total = ref(0)
const visible = ref(false)
const bulkVisible = ref(false)
const bulkSaving = ref(false)
const filters = reactive({ search: '', enabled: '' })
const emptyForm = { id: null, name: '', name_cn: '', name_en: '', direction_weight: 3, priority: 3, enabled: true }
const form = reactive({ ...emptyForm })
const bulkForm = reactive({ names: '', direction_weight: 3, priority: 3, enabled: true })

async function load() {
  const params = { page_size: 200 }
  if (filters.search) params.search = filters.search
  if (filters.enabled) params.enabled = filters.enabled
  const resp = await getDirections(params)
  rows.value = resp.data.results || resp.data
  total.value = resp.data.count ?? rows.value.length
  selectedRows.value = []
}

function resetFilters() {
  Object.assign(filters, { search: '', enabled: '' })
  load()
}

function open(row = null) {
  Object.assign(form, row ? { ...row, name_cn: row.name_cn || row.name, name_en: row.name_en || '' } : emptyForm)
  visible.value = true
}

async function save() {
  if (!form.name_cn?.trim()) {
    ElMessage.warning('请填写中文名称')
    return
  }
  form.name = form.name_cn.trim()
  form.id ? await updateDirection(form.id, form) : await createDirection(form)
  visible.value = false
  ElMessage.success('已保存')
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除研究方向「${row.name}」？`, '删除确认', { type: 'warning' })
  await deleteDirection(row.id)
  ElMessage.success('已删除')
  await load()
}

function openBulk() {
  Object.assign(bulkForm, { names: '', direction_weight: 3, priority: 3, enabled: true })
  bulkVisible.value = true
}

async function saveBulk() {
  if (!bulkForm.names.trim()) {
    ElMessage.warning('请填写至少一个研究方向')
    return
  }
  bulkSaving.value = true
  try {
    const resp = await bulkCreateDirections({ ...bulkForm })
    ElMessage.success(`新增 ${resp.data.created?.length || 0} 个，更新 ${resp.data.updated?.length || 0} 个`)
    bulkVisible.value = false
    await load()
  } finally {
    bulkSaving.value = false
  }
}

async function bulkRemove() {
  await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 个研究方向？`, '批量删除确认', { type: 'warning' })
  await bulkDeleteDirections(selectedRows.value.map((row) => row.id))
  ElMessage.success('已批量删除')
  await load()
}

function formatDateTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  const pad = (item) => String(item).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.metric-setting { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.metric-setting span { color: var(--text-muted); font-size: 13px; }
.bulk-example { width: 100%; color: var(--text-muted); font-size: 13px; line-height: 1.35; }
.bulk-example pre { margin: 3px 0 0; padding: 6px 10px; border-radius: 8px; background: #f3f7fc; color: #334155; line-height: 1.35; white-space: pre-wrap; overflow-wrap: anywhere; user-select: text; }
.template-item { margin-bottom: 8px; }
</style>
