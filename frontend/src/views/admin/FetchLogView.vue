<template>
  <AdminLayout title="抓取日志">
    <div class="toolbar">
      <el-select v-model="filters.status" placeholder="状态" clearable class="filter-item status-select">
        <el-option label="success" value="success" />
        <el-option label="failed" value="failed" />
        <el-option label="partial" value="partial" />
      </el-select>
      <el-date-picker v-model="filters.date" value-format="YYYY-MM-DD" placeholder="日期" class="filter-item" />
      <el-button type="primary" @click="load">筛选</el-button>
      <el-button plain @click="resetFilters">重置筛选</el-button>
    </div>
    <el-table :data="rows" border class="log-table">
      <el-table-column prop="source_name" label="RSS 源" min-width="220" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="fetched_count" label="RSS 条目" width="105" />
      <el-table-column prop="new_count" label="新入库" width="90" />
      <el-table-column prop="duplicate_count" label="已存在" width="90" />
      <el-table-column label="信息" min-width="300" show-overflow-tooltip>
        <template #default="{ row }">{{ formatLogMessage(row) }}</template>
      </el-table-column>
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="详情" width="90">
        <template #default="{ row }">
          <el-button link @click="showDetail(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-drawer v-model="drawerVisible" title="抓取详情" size="42%">
      <pre class="log-detail">{{ current?.error_detail || current?.message || '无错误详情' }}</pre>
    </el-drawer>
  </AdminLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import AdminLayout from '../../components/AdminLayout.vue'
import { getFetchLogs } from '../../api/logs'

const rows = ref([])
const filters = reactive({ status: '', date: '' })
const drawerVisible = ref(false)
const current = ref(null)

async function load() {
  const resp = await getFetchLogs(filters)
  rows.value = resp.data.results || resp.data
}

function resetFilters() {
  Object.assign(filters, { status: '', date: '' })
  load()
}

function statusType(status) {
  return status === 'success' ? 'success' : status === 'failed' ? 'danger' : 'warning'
}

function showDetail(row) {
  current.value = row
  drawerVisible.value = true
}

function formatLogMessage(row) {
  if (row.status === 'success') {
    return `RSS 返回 ${row.fetched_count || 0} 条，新入库 ${row.new_count || 0} 条，已存在 ${row.duplicate_count || 0} 条`
  }
  return row.message || '-'
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

onMounted(load)
</script>

<style scoped>
.log-table {
  margin-top: 0;
}

.log-detail {
  white-space: pre-wrap;
  line-height: 1.65;
  padding: 16px;
  border-radius: 16px;
  background: #f5f8fc;
  color: #26364a;
}
</style>
