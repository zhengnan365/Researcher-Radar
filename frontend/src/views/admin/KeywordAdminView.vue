<template>
  <AdminLayout title="关键词管理">
    <div class="admin-metrics">
      <div class="mini-metric"><span>关键词总数</span><strong>{{ total }}</strong></div>
      <div class="mini-metric"><span>当前显示</span><strong>{{ rows.length }}</strong></div>
      <div class="mini-metric"><span>启用关键词</span><strong>{{ rows.filter((r) => r.enabled).length }}</strong></div>
      <div class="mini-metric"><span>已绑定方向</span><strong>{{ rows.filter((r) => r.direction).length }}</strong></div>
    </div>

    <div class="filter-panel">
      <el-input
        v-model="filters.search"
        clearable
        placeholder="搜索关键词"
        class="filter-item search-input"
        @keyup.enter="load"
      />
      <el-select v-model="filters.direction" clearable placeholder="按研究方向筛选" class="filter-item">
        <el-option v-for="d in directions" :key="d.id" :label="d.name" :value="d.id" />
      </el-select>
      <el-select v-model="filters.enabled" clearable placeholder="启用状态" class="filter-item status-select">
        <el-option label="启用" value="true" />
        <el-option label="停用" value="false" />
      </el-select>
      <el-button type="primary" @click="load">筛选</el-button>
      <el-button plain @click="resetFilters">重置筛选</el-button>
      <div class="filter-actions">
        <el-button type="primary" @click="open()">新增关键词</el-button>
        <el-button type="primary" @click="openBulk">批量添加关键词</el-button>
        <el-button type="danger" plain :disabled="!selectedRows.length" @click="bulkRemove">批量删除</el-button>
      </div>
    </div>

    <el-table :data="rows" border class="keyword-table" @selection-change="selectedRows = $event">
      <el-table-column type="selection" width="46" />
      <el-table-column prop="keyword" label="关键词" min-width="220" />
      <el-table-column prop="direction_name" label="研究方向" min-width="180">
        <template #default="{ row }">
          <el-tag v-if="row.direction_name" class="tag-direction">{{ row.direction_name }}</el-tag>
          <span v-else class="muted">未绑定</span>
        </template>
      </el-table-column>
      <el-table-column prop="weight" label="权重" width="90" />
      <el-table-column prop="enabled" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link @click="open(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" title="关键词" width="560px" append-to-body>
      <el-form :model="form" label-width="90px">
        <el-form-item label="关键词"><el-input v-model="form.keyword" /></el-form-item>
        <el-form-item label="同义词"><el-input v-model="form.aliases" type="textarea" :rows="3" placeholder="每行一个同义词或缩写" /></el-form-item>
        <el-form-item label="排除词"><el-switch v-model="form.is_exclusion" /><span class="form-help">命中时将文献标为低相关</span></el-form-item>
        <el-form-item label="研究方向">
          <el-select v-model="form.direction" filterable placeholder="请选择研究方向">
            <el-option v-for="d in directions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="权重"><el-input-number v-model="form.weight" :min="1" :max="5" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bulkVisible" title="批量添加关键词" width="680px" append-to-body>
      <el-alert
        title="先选择研究方向，再按“关键词 | 权重”逐行粘贴；只写关键词时使用统一权重。普通关键词仍支持换行、逗号和分号分隔。"
        type="info"
        :closable="false"
        show-icon
        class="bulk-tip"
      />
      <el-form :model="bulkForm" label-width="96px">
        <el-form-item label="研究方向">
          <el-select v-model="bulkForm.direction" filterable placeholder="选择研究方向">
            <el-option v-for="d in directions" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="统一权重">
          <el-input-number v-model="bulkForm.weight" :min="1" :max="5" />
          <span class="form-help">1–5；仅关键词的行使用此权重。</span>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="bulkForm.enabled" /></el-form-item>
        <el-form-item label="更新已有">
          <el-switch v-model="bulkForm.update_existing" />
          <span class="form-help">开启后，同名关键词会更新到当前研究方向和权重。</span>
        </el-form-item>
        <el-form-item label="粘贴模板" class="template-item">
          <div class="bulk-example">
            <span>每行一项；填写行内权重时会覆盖统一权重。</span>
            <pre>integrated energy system | 5
energy hub | 4
demand response</pre>
          </div>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="bulkForm.keywords"
            type="textarea"
            :rows="9"
            placeholder="integrated energy system | 5&#10;energy hub | 4&#10;demand response"
          />
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
import { getDirections } from '../../api/directions'
import { bulkCreateKeywords, bulkDeleteKeywords, createKeyword, deleteKeyword, getKeywords, updateKeyword } from '../../api/keywords'

const rows = ref([])
const selectedRows = ref([])
const directions = ref([])
const total = ref(0)
const visible = ref(false)
const bulkVisible = ref(false)
const bulkSaving = ref(false)

const filters = reactive({ search: '', direction: '', enabled: '' })
const form = reactive({ id: null, keyword: '', aliases: '', is_exclusion: false, weight: 1, enabled: true, description: '', direction: null })
const bulkForm = reactive({
  direction: null,
  weight: 1,
  enabled: true,
  update_existing: true,
  keywords: '',
})

async function load() {
  const params = { page_size: 200 }
  if (filters.search) params.search = filters.search
  if (filters.direction) params.direction = filters.direction
  if (filters.enabled) params.enabled = filters.enabled
  const [kw, dir] = await Promise.all([getKeywords(params), getDirections({ page_size: 200 })])
  rows.value = kw.data.results || kw.data
  total.value = kw.data.count ?? rows.value.length
  directions.value = dir.data.results || dir.data
  selectedRows.value = []
}

function resetFilters() {
  Object.assign(filters, { search: '', direction: '', enabled: '' })
  load()
}

function open(row = null) {
  Object.assign(
    form,
    row
      ? { ...row, direction: row.direction || null }
      : { id: null, keyword: '', aliases: '', is_exclusion: false, weight: 1, enabled: true, description: '', direction: null },
  )
  visible.value = true
}

async function save() {
  if (!form.keyword.trim()) {
    ElMessage.warning('请填写关键词')
    return
  }
  if (!form.direction) {
    ElMessage.warning('请先选择研究方向')
    return
  }
  form.id ? await updateKeyword(form.id, form) : await createKeyword(form)
  visible.value = false
  ElMessage.success('已保存')
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除关键词「${row.keyword}」？`, '删除确认', { type: 'warning' })
  await deleteKeyword(row.id)
  ElMessage.success('已删除')
  await load()
}

async function bulkRemove() {
  await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 个关键词？`, '批量删除确认', { type: 'warning' })
  await bulkDeleteKeywords(selectedRows.value.map((row) => row.id))
  ElMessage.success('已批量删除')
  await load()
}

function openBulk() {
  Object.assign(bulkForm, { direction: null, weight: 1, enabled: true, update_existing: true, keywords: '' })
  bulkVisible.value = true
}

async function saveBulk() {
  if (!bulkForm.direction) {
    ElMessage.warning('请先选择研究方向')
    return
  }
  if (!bulkForm.keywords.trim()) {
    ElMessage.warning('请填写至少一个关键词')
    return
  }
  bulkSaving.value = true
  try {
    const resp = await bulkCreateKeywords({ ...bulkForm })
    const { created = [], updated = [], skipped = [] } = resp.data
    ElMessage.success(`新增 ${created.length} 个，更新 ${updated.length} 个，跳过 ${skipped.length} 个`)
    bulkVisible.value = false
    filters.direction = bulkForm.direction
    await load()
  } finally {
    bulkSaving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.admin-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.mini-metric {
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(240, 253, 244, 0.9), rgba(255, 255, 255, 0.86));
  border: 1px solid rgba(34, 197, 94, 0.14);
}

.mini-metric span {
  color: var(--text-muted);
  font-size: 13px;
}

.mini-metric strong {
  display: block;
  margin-top: 8px;
  color: var(--deep-blue);
  font-size: 24px;
}

.filter-panel {
  box-sizing: border-box;
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 14px;
  margin-bottom: 14px;
  border: 1px solid rgba(47, 140, 255, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  min-width: 0;
}

.filter-item {
  flex: 1 1 11rem;
  min-width: 9.5rem;
  width: auto !important;
  max-width: none;
}

.search-input {
  flex: 1.3 1 14rem;
  min-width: 12rem;
  width: auto !important;
  max-width: none;
}

.status-select {
  flex: 0.75 1 8rem;
  min-width: 7rem;
  width: auto !important;
  max-width: none;
}

.filter-panel :deep(.filter-item),
.filter-panel :deep(.el-input),
.filter-panel :deep(.el-select),
.filter-panel :deep(.el-date-editor) {
  width: auto !important;
}

.filter-panel :deep(.el-button) {
  flex: 0 0 auto;
}

.filter-actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex: 0 1 auto;
  min-width: fit-content;
}

.keyword-table {
  width: 100%;
}

.bulk-tip {
  margin-bottom: 16px;
}

.form-help {
  margin-left: 12px;
  color: var(--text-muted);
  font-size: 13px;
}

.bulk-example { width: 100%; color: var(--text-muted); font-size: 13px; line-height: 1.35; }
.bulk-example pre { margin: 3px 0 0; padding: 6px 10px; border-radius: 8px; background: #f3f7fc; color: #334155; line-height: 1.35; white-space: pre-wrap; user-select: text; }
.template-item { margin-bottom: 8px; }

@media (max-width: 900px) {
  .filter-actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }
}
</style>
