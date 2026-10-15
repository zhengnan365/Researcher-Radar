<template>
  <AdminLayout title="日报管理">
    <div class="toolbar">
      <el-date-picker v-model="reportDate" value-format="YYYY-MM-DD" placeholder="选择日期" class="filter-item" />
      <el-button type="primary" @click="regenerate">重新生成</el-button>
    </div>
    <div class="report-grid">
      <article v-for="row in rows" :key="row.id" class="report-card hover-lift" @click="current = row">
        <h3>{{ row.report_date }}</h3>
        <strong>{{ row.paper_count }} 篇</strong>
        <p>{{ formatDateTime(row.created_at) }}</p>
        <div class="report-actions">
          <el-button size="small" type="primary" plain>查看 HTML</el-button>
          <el-button size="small" plain>查看 Markdown</el-button>
        </div>
      </article>
    </div>
    <el-card v-if="current" style="margin-top: 16px">
      <template #header>{{ current.title }}</template>
      <div v-html="current.html_content"></div>
    </el-card>
  </AdminLayout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import AdminLayout from '../../components/AdminLayout.vue'
import { getReports, regenerateReport } from '../../api/reports'

const rows = ref([])
const current = ref(null)
const reportDate = ref('')

async function load() {
  const resp = await getReports()
  rows.value = resp.data.results || resp.data
  current.value = rows.value[0] || null
}

async function regenerate() {
  await regenerateReport(reportDate.value)
  await load()
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (item) => String(item).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(load)
</script>

<style scoped>
.report-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.report-card {
  cursor: pointer;
  padding: 18px;
  border-radius: 22px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(238, 248, 255, 0.78));
  border: 1px solid rgba(255, 255, 255, 0.76);
  box-shadow: var(--shadow-soft);
}

.report-card h3 {
  margin: 0;
  color: var(--deep-blue);
}

.report-card strong {
  display: block;
  margin-top: 14px;
  color: var(--tech-blue);
  font-size: 24px;
}

.report-card p {
  color: var(--text-muted);
  font-size: 13px;
}

.report-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
