<template>
  <AdminLayout title="配置导入导出">
    <div class="transfer-grid">
      <section class="transfer-panel export-panel">
        <div class="panel-icon export-icon"><el-icon><Download /></el-icon></div>
        <div class="panel-content">
          <h2>一键导出系统配置</h2>
          <p>生成可迁移的 JSON 配置包，适合服务器备份、换机部署和环境复制。</p>
          <div class="scope-list">
            <el-tag>研究方向</el-tag>
            <el-tag>关键词</el-tag>
            <el-tag>RSS 源</el-tag>
            <el-tag>评分与日报规则</el-tag>
            <el-tag type="warning">Zotero Key</el-tag>
            <el-tag type="warning">AI API 配置</el-tag>
          </div>
          <el-alert
            title="导出文件包含完整 Zotero Access Key 和已配置的 AI API Key，请作为敏感文件妥善保管，不要公开分享。"
            type="warning"
            show-icon
            :closable="false"
          />
          <el-button type="primary" :loading="exporting" @click="handleExport">
            <el-icon><Download /></el-icon>
            一键导出
          </el-button>
        </div>
      </section>

      <section class="transfer-panel import-panel">
        <div class="panel-icon import-icon"><el-icon><UploadFilled /></el-icon></div>
        <div class="panel-content">
          <h2>一键导入系统配置</h2>
          <p>按名称或 URL 合并配置：同名项更新，不存在的项新增，不会删除目标系统已有配置。</p>
          <el-upload
            accept=".json,application/json"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="handleFile"
          >
            <el-button plain><el-icon><FolderOpened /></el-icon>选择 JSON 配置文件</el-button>
          </el-upload>

          <div v-if="selectedFile" class="file-preview">
            <div class="file-heading">
              <el-icon><Document /></el-icon>
              <strong>{{ selectedFile }}</strong>
            </div>
            <div class="preview-stats">
              <span>研究方向 <b>{{ preview.directions }}</b></span>
              <span>关键词 <b>{{ preview.keywords }}</b></span>
              <span>RSS 源 <b>{{ preview.sources }}</b></span>
              <span>评分规则 <b>{{ preview.hasScoring ? '有' : '无' }}</b></span>
              <span>Zotero Key <b>{{ preview.hasZoteroKey ? '有' : '无' }}</b></span>
              <span>AI API Key <b>{{ preview.hasAiKey ? '有' : '无' }}</b></span>
            </div>
          </div>

          <el-alert
            title="导入采用事务处理；任意配置校验失败时，本次导入会整体回滚。文献、日报、日志、用户和 Zotero 文献缓存不会被修改。"
            type="info"
            show-icon
            :closable="false"
          />
          <el-button type="primary" :disabled="!configPayload" :loading="importing" @click="handleImport">
            <el-icon><UploadFilled /></el-icon>
            一键导入
          </el-button>
        </div>
      </section>
    </div>

    <section class="rule-panel">
      <h3>导入规则</h3>
      <div class="rule-items">
        <div><b>研究方向</b><span>按方向名称新增或更新</span></div>
        <div><b>关键词</b><span>按关键词内容新增或更新，并恢复方向关联</span></div>
        <div><b>RSS 源</b><span>按 RSS URL 新增或更新，保留抓取历史与累计数量</span></div>
        <div><b>评分规则</b><span>覆盖数据库运行时规则，不自动触发历史文献重新评分</span></div>
        <div><b>Zotero</b><span>导入 User ID、Group ID、文献库类型和完整 Access Key</span></div>
        <div><b>AI 速读</b><span>导入服务类型、接口地址、模型和完整 API Key</span></div>
      </div>
    </section>
  </AdminLayout>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { Document, Download, FolderOpened, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminLayout from '../../components/AdminLayout.vue'
import { exportSystemConfig, importSystemConfig } from '../../api/configTransfer'

const exporting = ref(false)
const importing = ref(false)
const selectedFile = ref('')
const configPayload = ref(null)
const preview = reactive({ directions: 0, keywords: 0, sources: 0, hasScoring: false, hasZoteroKey: false, hasAiKey: false })

async function handleExport() {
  try {
    await ElMessageBox.confirm(
      '导出文件包含完整 Zotero Access Key 和已配置的 AI API Key。请确认下载后会将其保存在安全位置。',
      '确认导出敏感配置',
      { type: 'warning', confirmButtonText: '确认导出' },
    )
  } catch {
    return
  }

  exporting.value = true
  try {
    const response = await exportSystemConfig()
    const disposition = String(response.headers['content-disposition'] || '')
    const match = disposition.match(/filename="?([^";]+)"?/i)
    const filename = match?.[1] || `researcher_radar_config_${dateStamp()}.json`
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('系统配置已导出')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '导出系统配置失败')
  } finally {
    exporting.value = false
  }
}

async function handleFile(file) {
  selectedFile.value = ''
  configPayload.value = null
  try {
    const content = await file.raw.text()
    const payload = JSON.parse(content)
    if (payload?.format !== 'literature-daily-config' || ![1, 2, 3].includes(Number(payload?.version)) || !payload?.data || typeof payload.data !== 'object' || Array.isArray(payload.data)) {
      throw new Error('不是有效的科研雷达配置文件')
    }
    selectedFile.value = file.name
    configPayload.value = payload
    Object.assign(preview, {
      directions: payload.data.research_directions?.length || 0,
      keywords: payload.data.keywords?.length || 0,
      sources: payload.data.rss_sources?.length || 0,
      hasScoring: Boolean(payload.data.scoring_rules),
      hasZoteroKey: Boolean(payload.data.zotero?.api_key),
      hasAiKey: Boolean(payload.data.ai?.api_key),
    })
  } catch (error) {
    ElMessage.error(error.message || '配置文件读取失败')
  }
}

async function handleImport() {
  if (!configPayload.value) return
  try {
    await ElMessageBox.confirm(
      `确认导入“${selectedFile.value}”？同名配置将被更新，导入过程不会删除现有配置。`,
      '确认导入配置',
      { type: 'warning', confirmButtonText: '确认导入' },
    )
  } catch {
    return
  }

  importing.value = true
  try {
    const response = await importSystemConfig(configPayload.value)
    const summary = response.data.summary || {}
    const changed = Object.values(summary).reduce(
      (total, item) => total + Number(item.created || 0) + Number(item.updated || 0),
      0,
    )
    ElMessage.success(`配置导入完成，共处理 ${changed} 项`)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '导入系统配置失败')
  } finally {
    importing.value = false
  }
}

function dateStamp() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
}
</script>

<style scoped>
.transfer-grid {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.transfer-panel,
.rule-panel {
  border: 1px solid rgba(47, 140, 255, 0.14);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 14px 34px rgba(31, 96, 160, 0.08);
}

.transfer-panel {
  min-height: 390px;
  padding: 24px;
  display: flex;
  gap: 18px;
  box-sizing: border-box;
}

.panel-icon {
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  font-size: 22px;
}

.export-icon { color: #2563eb; background: #eaf3ff; }
.import-icon { color: #0f9f94; background: #e7fbf8; }

.panel-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 16px;
}

.panel-content h2,
.rule-panel h3 {
  margin: 0;
  color: var(--deep-blue);
}

.panel-content p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.75;
}

.scope-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.file-preview {
  width: 100%;
  padding: 14px;
  border: 1px solid #cfe3ff;
  border-radius: 14px;
  background: #f4f9ff;
  box-sizing: border-box;
}

.file-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--deep-blue);
  overflow-wrap: anywhere;
}

.preview-stats {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--text-muted);
  font-size: 13px;
}

.preview-stats b { color: var(--deep-blue); }

.rule-panel {
  width: 100%;
  margin-top: 18px;
  padding: 22px 24px;
  box-sizing: border-box;
}

.rule-items {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.rule-items > div {
  padding: 14px;
  border-radius: 14px;
  background: #f5f9ff;
}

.rule-items b,
.rule-items span { display: block; }
.rule-items b { color: var(--deep-blue); }
.rule-items span { margin-top: 6px; color: var(--text-muted); font-size: 13px; line-height: 1.55; }

@media (max-width: 1200px) {
  .transfer-grid { grid-template-columns: 1fr; }
  .rule-items { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
  .transfer-panel { padding: 18px; flex-direction: column; }
  .rule-items { grid-template-columns: 1fr; }
}
</style>
