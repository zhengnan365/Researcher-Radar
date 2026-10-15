<template>
  <AdminLayout title="文献源管理">
    <div class="admin-metrics">
      <div class="mini-metric"><span>文献源总数</span><strong>{{ total }}</strong></div>
      <div class="mini-metric"><span>当前显示</span><strong>{{ rows.length }}</strong></div>
      <div class="mini-metric"><span>启用源数量</span><strong>{{ rows.filter((r) => r.enabled).length }}</strong></div>
      <div class="mini-metric danger"><span>失败源数量</span><strong>{{ rows.filter((r) => r.last_fetch_status === 'failed').length }}</strong></div>
    </div>

    <div class="filter-panel">
      <el-input v-model="filters.search" clearable placeholder="搜索名称/URL/期刊" class="filter-item search-input" @keyup.enter="load" />
      <el-select v-model="filters.enabled" clearable placeholder="启用状态" class="filter-item status-select">
        <el-option label="启用" value="true" />
        <el-option label="停用" value="false" />
      </el-select>
      <el-button type="primary" @click="load">筛选</el-button>
      <el-button plain @click="resetFilters">重置筛选</el-button>
      <div class="filter-actions">
        <el-button type="primary" @click="open()">新增文献源</el-button>
        <el-button type="primary" @click="openBulk">批量添加</el-button>
        <el-button type="danger" plain :disabled="!selectedRows.length" @click="bulkRemove">批量删除</el-button>
      </div>
    </div>

    <el-table :data="rows" border class="admin-table" @selection-change="selectedRows = $event">
      <el-table-column type="selection" width="46" />
      <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="journal" label="期刊" min-width="180" show-overflow-tooltip />
      <el-table-column prop="enabled" label="启用" width="90">
        <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="last_fetch_status" label="最近状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.last_fetch_status === 'success' ? 'success' : row.last_fetch_status === 'failed' ? 'danger' : 'warning'">
            {{ row.last_fetch_status || 'pending' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_fetched_count" label="累计" width="80" />
      <el-table-column label="操作" width="210" fixed="right">
        <template #default="{ row }">
          <el-button link @click="test(row)">测试</el-button>
          <el-button link @click="open(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" title="文献源" width="640px" append-to-body>
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="抓取方式">
          <el-select v-model="form.fetch_mode">
            <el-option label="RSS" value="rss" />
            <el-option label="OpenAlex（无 RSS）" value="openalex" />
            <el-option label="RSS + OpenAlex 补抓" value="both" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.fetch_mode !== 'openalex'" label="RSS URL"><el-input v-model="form.url" /></el-form-item>
        <el-form-item label="期刊 ISSN">
          <div class="field-content">
            <el-input v-model="form.openalex_issn" placeholder="例如 0306-2619" />
            <span class="field-hint">OpenAlex 模式必填；普通 RSS 可选。ScienceDirect RSS 可自动识别 ISSN；“测试”仅检查主源，备用结果见抓取日志。</span>
          </div>
        </el-form-item>
        <el-form-item label="期刊"><el-input v-model="form.journal" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bulkVisible" title="批量添加 RSS 源" width="760px" append-to-body>
      <el-alert
        title="每行一个 RSS 源。推荐格式：名称 | RSS URL | 期刊。也可以只填写 RSS URL。"
        type="info"
        :closable="false"
        show-icon
        class="bulk-tip"
      />
      <el-form :model="bulkForm" label-width="90px">
        <el-form-item label="启用"><el-switch v-model="bulkForm.enabled" /></el-form-item>
        <el-form-item label="RSS 源">
          <el-input
            v-model="bulkForm.sources"
            type="textarea"
            :rows="10"
            placeholder="Applied Energy | https://rss.sciencedirect.com/publication/science/03062619 | Applied Energy"
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
import { bulkCreateSources, bulkDeleteSources, createSource, deleteSource, getSources, testSource, updateSource } from '../../api/sources'

const rows = ref([])
const selectedRows = ref([])
const total = ref(0)
const visible = ref(false)
const bulkVisible = ref(false)
const bulkSaving = ref(false)

const filters = reactive({ search: '', enabled: '' })
const form = reactive({ id: null, name: '', url: '', fetch_mode: 'rss', openalex_issn: '', journal: '', enabled: true, remark: '' })
const bulkForm = reactive({ sources: '', enabled: true })

async function load() {
  const params = { page_size: 200 }
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params[key] = value
  })
  const src = await getSources(params)
  rows.value = src.data.results || src.data
  total.value = src.data.count ?? rows.value.length
  selectedRows.value = []
}

function resetFilters() {
  Object.assign(filters, { search: '', enabled: '' })
  load()
}

function open(row = null) {
  Object.assign(form, row || { id: null, name: '', url: '', fetch_mode: 'rss', openalex_issn: '', journal: '', enabled: true, remark: '' })
  visible.value = true
}

async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写名称')
  if (form.fetch_mode !== 'openalex' && !form.url.trim()) return ElMessage.warning('请填写 RSS URL')
  if (form.fetch_mode !== 'rss' && !form.openalex_issn.trim()) return ElMessage.warning('请填写 ISSN')
  if (form.fetch_mode === 'openalex') form.url = ''
  form.id ? await updateSource(form.id, form) : await createSource(form)
  visible.value = false
  ElMessage.success('已保存')
  await load()
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除 RSS 源「${row.name}」？`, '删除确认', { type: 'warning' })
  await deleteSource(row.id)
  ElMessage.success('已删除')
  await load()
}

function openBulk() {
  Object.assign(bulkForm, { sources: '', enabled: true })
  bulkVisible.value = true
}

async function saveBulk() {
  if (!bulkForm.sources.trim()) {
    ElMessage.warning('请填写至少一个 RSS 源')
    return
  }
  bulkSaving.value = true
  try {
    const resp = await bulkCreateSources({ ...bulkForm })
    ElMessage.success(`新增 ${resp.data.created?.length || 0} 个，更新 ${resp.data.updated?.length || 0} 个，跳过 ${resp.data.skipped?.length || 0} 个`)
    bulkVisible.value = false
    await load()
  } finally {
    bulkSaving.value = false
  }
}

async function bulkRemove() {
  await ElMessageBox.confirm(`确认删除选中的 ${selectedRows.value.length} 个 RSS 源？`, '批量删除确认', { type: 'warning' })
  await bulkDeleteSources(selectedRows.value.map((row) => row.id))
  ElMessage.success('已批量删除')
  await load()
}

async function test(row) {
  const resp = await testSource(row.id)
  ElMessage.info(`${resp.data.ok ? '成功' : '失败'}：${resp.data.title || resp.data.message}，条目 ${resp.data.entry_count}`)
}

onMounted(load)
</script>

<style scoped>
.field-content { display: flex; flex-direction: column; width: 100%; gap: 5px; }
.field-hint { color: #64748b; font-size: 13px; line-height: 1.5; }
</style>
