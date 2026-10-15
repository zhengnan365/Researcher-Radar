<template>
  <AdminLayout title="AI 与 Zotero 设置">
    <section class="settings-section" aria-labelledby="zotero-settings-title">
      <div class="section-heading">
        <div>
          <h2 id="zotero-settings-title">Zotero 文献库</h2>
          <p>连接文献库，供同步、去重和导入使用。</p>
        </div>
        <el-tag :type="zoteroConfig.has_api_key ? 'success' : 'warning'">
          {{ zoteroConfig.has_api_key ? 'Access Key 已配置' : 'Access Key 未配置' }}
        </el-tag>
      </div>

      <el-form :model="zoteroForm" label-width="130px" class="settings-form">
        <el-form-item label="文献库类型">
          <el-radio-group v-model="zoteroForm.library_type">
            <el-radio-button label="user">个人文献库</el-radio-button>
            <el-radio-button label="group">群组文献库</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="User ID">
          <el-input v-model="zoteroForm.user_id" placeholder="Zotero User ID" />
        </el-form-item>
        <el-form-item label="Group ID">
          <el-input v-model="zoteroForm.group_id" placeholder="群组文献库时填写" />
        </el-form-item>
        <el-form-item label="Access Key">
          <div class="field-content">
            <el-input v-model="zoteroForm.api_key" type="password" show-password autocomplete="new-password" placeholder="填写新 Key；留空保留已保存的 Key" />
            <span v-if="zoteroConfig.has_api_key" class="field-hint">已保存：{{ zoteroConfig.api_key_masked }}</span>
          </div>
        </el-form-item>
        <el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="zoteroSaving" @click="saveZotero">保存 Zotero 设置</el-button>
            <span v-if="zoteroConfig.updated_at" class="field-hint">更新于 {{ formatDateTime(zoteroConfig.updated_at) }}</span>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <section class="settings-section" aria-labelledby="ai-settings-title">
      <div class="section-heading">
        <div>
          <h2 id="ai-settings-title">AI 速读</h2>
          <p>手动触发时使用文献标题和原始摘要；结果不参与推荐评分。</p>
        </div>
        <el-tag :type="aiConfig.has_api_key ? 'success' : 'warning'">
          {{ aiConfig.has_api_key ? 'API Key 已配置' : 'API Key 未配置' }}
        </el-tag>
      </div>

      <el-form :model="aiForm" label-width="130px" class="settings-form">
        <el-form-item label="服务类型">
          <el-radio-group v-model="aiForm.provider" @change="changeProvider">
            <el-radio-button label="deepseek">DeepSeek</el-radio-button>
            <el-radio-button label="custom">兼容接口</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="接口基础地址">
          <el-input v-model="aiForm.base_url" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="aiForm.model" placeholder="deepseek-flash" />
        </el-form-item>
        <el-form-item label="API Key">
          <div class="field-content">
            <el-input v-model="aiForm.api_key" type="password" show-password autocomplete="new-password" placeholder="填写新 Key；留空保留已保存的 Key" />
            <span v-if="aiConfig.source === 'environment'" class="field-hint">当前使用服务器环境变量；保存后改用页面配置。</span>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="aiSaving" @click="saveAi">保存 AI 设置</el-button>
          <el-button :icon="Refresh" title="重新读取 AI 设置" aria-label="重新读取 AI 设置" @click="loadAi" />
        </el-form-item>
      </el-form>
    </section>
  </AdminLayout>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AdminLayout from '../components/AdminLayout.vue'
import { getAiSettings, saveAiSettings } from '../api/aiSettings'
import { getZoteroConfig, saveZoteroConfig } from '../api/zotero'

const zoteroSaving = ref(false)
const zoteroConfig = reactive({ has_api_key: false, api_key_masked: '', updated_at: '' })
const zoteroForm = reactive({ library_type: 'user', user_id: '', group_id: '', api_key: '' })
const aiSaving = ref(false)
const aiConfig = reactive({ has_api_key: false, source: 'none' })
const aiForm = reactive({ provider: 'deepseek', base_url: 'https://api.deepseek.com', model: 'deepseek-flash', api_key: '' })

async function loadZotero() {
  try {
    const { data } = await getZoteroConfig()
    Object.assign(zoteroConfig, data)
    zoteroForm.library_type = data.library_type || 'user'
    zoteroForm.user_id = data.user_id || ''
    zoteroForm.group_id = data.group_id || ''
    zoteroForm.api_key = ''
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '读取 Zotero 设置失败')
  }
}

async function saveZotero() {
  zoteroSaving.value = true
  try {
    const { data } = await saveZoteroConfig(zoteroForm)
    Object.assign(zoteroConfig, data)
    zoteroForm.api_key = ''
    ElMessage.success('Zotero 设置已保存')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存 Zotero 设置失败')
  } finally {
    zoteroSaving.value = false
  }
}

function changeProvider(provider) {
  if (provider === 'deepseek') {
    aiForm.base_url = 'https://api.deepseek.com'
    aiForm.model = 'deepseek-flash'
  }
}

async function loadAi() {
  try {
    const { data } = await getAiSettings()
    Object.assign(aiConfig, data)
    aiForm.provider = data.provider || 'deepseek'
    aiForm.base_url = data.base_url || 'https://api.deepseek.com'
    aiForm.model = data.model || 'deepseek-flash'
    aiForm.api_key = ''
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '读取 AI 设置失败')
  }
}

async function saveAi() {
  aiSaving.value = true
  try {
    const { data } = await saveAiSettings(aiForm)
    Object.assign(aiConfig, data)
    aiForm.api_key = ''
    ElMessage.success('AI 设置已保存')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存 AI 设置失败')
  } finally {
    aiSaving.value = false
  }
}

function formatDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (item) => String(item).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(() => {
  loadZotero()
  loadAi()
})
</script>

<style scoped>
.settings-section {
  flex: 0 0 100%;
  min-width: 0;
  padding: 0 0 20px;
}
.settings-section + .settings-section {
  border-top: 1px solid #dce4eb;
  padding-top: 22px;
}
.section-heading {
  width: min(760px, 100%);
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px 18px;
  margin-bottom: 20px;
}
.section-heading h2 {
  margin: 0;
  color: #14283e;
  font-size: 18px;
  line-height: 1.4;
}
.section-heading p {
  margin: 4px 0 0;
  color: #627386;
  font-size: 13px;
  line-height: 1.5;
}
.settings-form { width: min(760px, 100%); }
.field-content { display: flex; flex-direction: column; width: 100%; gap: 5px; }
.field-hint { color: #64748b; font-size: 13px; line-height: 1.5; }
.form-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
@media (max-width: 640px) {
  .settings-form :deep(.el-form-item__label) { width: 100% !important; justify-content: flex-start; }
  .settings-form :deep(.el-form-item__content) { margin-left: 0 !important; }
}
</style>
