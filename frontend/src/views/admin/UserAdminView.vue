<template>
  <AdminLayout title="用户管理">
    <div class="admin-metrics">
      <div class="mini-metric"><span>用户总数</span><strong>{{ total }}</strong></div>
      <div class="mini-metric"><span>当前显示</span><strong>{{ rows.length }}</strong></div>
      <div class="mini-metric"><span>启用用户</span><strong>{{ rows.filter((r) => r.is_active).length }}</strong></div>
      <div class="mini-metric"><span>管理员</span><strong>{{ rows.filter((r) => r.is_staff || r.is_superuser).length }}</strong></div>
    </div>

    <div class="filter-panel">
      <el-input v-model="filters.search" clearable placeholder="搜索用户名/邮箱/姓名" class="filter-item search-input" @keyup.enter="load" />
      <el-select v-model="filters.active" clearable placeholder="启用状态" class="filter-item status-select">
        <el-option label="启用" value="true" />
        <el-option label="停用" value="false" />
      </el-select>
      <el-select v-model="filters.staff" clearable placeholder="后台权限" class="filter-item status-select">
        <el-option label="管理员" value="true" />
        <el-option label="普通用户" value="false" />
      </el-select>
      <el-button type="primary" @click="load">筛选</el-button>
      <el-button plain @click="resetFilters">重置筛选</el-button>
      <div class="filter-actions">
        <el-button type="primary" @click="open()">新增用户</el-button>
      </div>
    </div>

    <el-table :data="rows" border class="admin-table">
      <el-table-column prop="username" label="用户名" min-width="150" show-overflow-tooltip />
      <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.email">{{ row.email }}</span>
          <span v-else class="muted">未填写</span>
        </template>
      </el-table-column>
      <el-table-column label="姓名" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ [row.first_name, row.last_name].filter(Boolean).join(' ') || '未填写' }}
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="权限" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.is_superuser" type="danger">超级管理员</el-tag>
          <el-tag v-else-if="row.is_staff" type="warning">管理员</el-tag>
          <el-tag v-else type="info">普通用户</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_login" label="最近登录" min-width="170">
        <template #default="{ row }">{{ formatDateTime(row.last_login) }}</template>
      </el-table-column>
      <el-table-column prop="date_joined" label="创建时间" min-width="170">
        <template #default="{ row }">{{ formatDateTime(row.date_joined) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link @click="open(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" title="用户" width="620px" append-to-body>
      <el-form :model="form" label-width="110px">
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
        <el-form-item label="名"><el-input v-model="form.first_name" /></el-form-item>
        <el-form-item label="姓"><el-input v-model="form.last_name" /></el-form-item>
        <el-form-item :label="form.id ? '重置密码' : '初始密码'">
          <el-input v-model="form.password" type="password" show-password :placeholder="form.id ? '留空则不修改密码' : '新建用户必须填写'" />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
        <el-form-item label="Django 后台"><el-switch v-model="form.is_staff" /></el-form-item>
        <el-form-item label="超级管理员"><el-switch v-model="form.is_superuser" /></el-form-item>
        <el-alert
          title="普通用户可以登录文献系统；开启 Django 后台后可进入 /admin/；超级管理员拥有用户管理权限。"
          type="info"
          :closable="false"
          show-icon
        />
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </AdminLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminLayout from '../../components/AdminLayout.vue'
import { createUser, deleteUser, getUsers, updateUser } from '../../api/users'

const rows = ref([])
const total = ref(0)
const visible = ref(false)
const saving = ref(false)

const filters = reactive({ search: '', active: '', staff: '' })
const form = reactive({
  id: null,
  username: '',
  email: '',
  first_name: '',
  last_name: '',
  password: '',
  is_active: true,
  is_staff: false,
  is_superuser: false,
})

async function load() {
  const params = { page_size: 200 }
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params[key] = value
  })
  const resp = await getUsers(params)
  rows.value = resp.data.results || resp.data
  total.value = resp.data.count ?? rows.value.length
}

function resetFilters() {
  Object.assign(filters, { search: '', active: '', staff: '' })
  load()
}

function open(row = null) {
  Object.assign(
    form,
    row
      ? { ...row, password: '' }
      : {
          id: null,
          username: '',
          email: '',
          first_name: '',
          last_name: '',
          password: '',
          is_active: true,
          is_staff: false,
          is_superuser: false,
        },
  )
  visible.value = true
}

async function save() {
  if (!form.username.trim()) {
    ElMessage.warning('请填写用户名')
    return
  }
  if (!form.id && !form.password) {
    ElMessage.warning('新建用户时请填写初始密码')
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    if (form.id && !payload.password) delete payload.password
    form.id ? await updateUser(form.id, payload) : await createUser(payload)
    visible.value = false
    ElMessage.success('已保存')
    await load()
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确认删除用户「${row.username}」？删除后该账号不能再登录。`, '删除确认', { type: 'warning' })
  await deleteUser(row.id)
  ElMessage.success('已删除')
  await load()
}

function formatDateTime(value) {
  if (!value) return '未记录'
  return String(value).replace('T', ' ').slice(0, 19)
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
  max-width: none;
}

.status-select {
  flex: 0.75 1 8rem;
  min-width: 7rem;
  max-width: none;
}

.filter-panel :deep(.filter-item),
.filter-panel :deep(.el-input),
.filter-panel :deep(.el-select) {
  width: auto !important;
}

.filter-actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  min-width: fit-content;
}

@media (max-width: 900px) {
  .filter-actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }
}
</style>
