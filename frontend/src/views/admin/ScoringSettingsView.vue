<template>
  <AdminLayout title="推荐评分规则">
    <div class="admin-metrics">
      <div class="mini-metric"><span>重点推荐阈值</span><strong>{{ form.key_threshold }}</strong></div>
      <div class="mini-metric"><span>日报最低分</span><strong>{{ form.report_min_score }}</strong></div>
      <div class="mini-metric"><span>低分阈值</span><strong>{{ form.low_score_threshold }}</strong></div>
      <div class="mini-metric"><span>每日最多展示</span><strong>{{ form.daily_max_papers }}</strong></div>
    </div>

    <el-card shadow="never" class="settings-card distribution-card">
      <template #header>
        <div class="distribution-header">
          <strong>当前评分分布统计</strong>
          <span class="distribution-note">分布区间：0-9、10-14、15-29、30+；日报从 {{ form.report_min_score }} 分起</span>
          <div class="distribution-controls">
            <el-radio-group v-model="distributionFilters.range" size="small" @change="loadDistribution">
              <el-radio-button label="all">全部文献</el-radio-button>
              <el-radio-button label="30d">最近 30 天</el-radio-button>
            </el-radio-group>
            <el-checkbox v-model="distributionFilters.include_deleted" @change="loadDistribution">包含软删除</el-checkbox>
          </div>
        </div>
      </template>
      <div v-if="distribution.total" class="distribution-grid">
        <div v-for="bucket in distribution.buckets" :key="bucket.label" class="distribution-item">
          <div class="distribution-item-head">
            <strong>{{ bucket.label }} 分</strong>
            <span>{{ bucket.count }} 篇</span>
          </div>
          <div class="distribution-ratio">{{ bucket.ratio }}%</div>
          <div class="distribution-bar"><i :style="{ width: `${bucket.ratio}%` }"></i></div>
          <p>{{ bucket.meaning }}</p>
        </div>
      </div>
      <el-empty v-else description="暂无评分分布" :image-size="82" />
    </el-card>

    <div class="settings-grid">
      <el-card shadow="never" class="settings-card">
        <template #header><strong>评分规则配置</strong></template>
        <el-form :model="form" label-width="180px" class="settings-form">
          <el-form-item label="标题倍率"><el-input-number v-model="form.title_factor" :min="0" :max="10" :step="0.5" /></el-form-item>
          <el-form-item label="摘要倍率"><el-input-number v-model="form.abstract_factor" :min="0" :max="10" :step="0.5" /></el-form-item>
          <el-form-item label="RSS 关键词倍率"><el-input-number v-model="form.raw_factor" :min="0" :max="10" :step="0.5" /></el-form-item>
          <el-form-item label="每增加一个命中字段"><el-input-number v-model="form.field_bonus" :min="0" :max="5" /></el-form-item>
          <el-form-item label="奖励占关键词分上限"><el-input-number v-model="form.bonus_ratio" :min="0" :max="0.25" :step="0.05" :precision="2" /></el-form-item>
          <el-form-item>
            <template #label><DirectionMetricLabel metric="relevance" label="研究相关度奖励" /></template>
            <span class="rule-help">研究相关度 5 / 4 / 3 / 2 / 1 对应方向奖励 10 / 8 / 5 / 3 / 1 分，实际奖励受关键词分上限约束。</span>
          </el-form-item>
          <el-form-item label="单篇文章最高分"><el-input-number v-model="form.max_score" :min="1" :max="100" /></el-form-item>
          <el-form-item label="日报最低展示分数"><el-input-number v-model="form.report_min_score" :min="0" /></el-form-item>
          <el-form-item label="今日重点文献最低分数"><el-input-number v-model="form.key_threshold" :min="0" /></el-form-item>
          <el-form-item label="一般推荐最低分数"><el-input-number v-model="form.normal_threshold" :min="0" /></el-form-item>
          <el-form-item label="低分条目阈值"><el-input-number v-model="form.low_score_threshold" :min="0" /></el-form-item>
          <el-form-item label="重点推荐降级词">
            <div class="term-setting">
              <el-input v-model="form.key_demotion_terms" type="textarea" :rows="5" placeholder="每行一个英文词组" />
              <span class="rule-help">只匹配标题。命中后最高为重点推荐阈值以下一分，保留原始关键词贡献；用于排除明显跨领域的应用场景。</span>
            </div>
          </el-form-item>
          <el-form-item label="低相关内容保留天数">
            <el-input-number v-model="form.low_score_retention_days" :min="30" :max="3650" />
            <span class="rule-help">默认 90 天；到期后仅保留标题、DOI、链接及去重索引。收藏和已导入 Zotero 的文献不会清理。</span>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card shadow="never" class="settings-card">
        <template #header><strong>展示排序规则</strong></template>
        <el-form :model="form" label-width="180px" class="settings-form">
          <el-form-item>
            <template #label><DirectionMetricLabel metric="priority" /></template>
            <span class="rule-help">在研究方向管理页设置；用于按方向排序和推荐分相同时的展示顺序，不参与相关性评分。</span>
          </el-form-item>
          <el-form-item label="日报默认排序方式">
            <el-select v-model="form.report_sort">
              <el-option label="按推荐分数" value="score" />
              <el-option label="按发布时间" value="date" />
              <el-option label="先分数再时间" value="score_date" />
              <el-option label="按研究方向" value="direction" />
              <el-option label="按期刊名称" value="journal" />
              <el-option label="按关键词命中数量" value="keyword_count" />
            </el-select>
          </el-form-item>
          <el-form-item label="按推荐分数降序"><el-switch v-model="form.sort_by_score_desc" /></el-form-item>
          <el-form-item label="按研究方向分组"><el-switch v-model="form.group_by_direction" /></el-form-item>
          <el-form-item label="每日最多展示文献数量"><el-input-number v-model="form.daily_max_papers" :min="1" /></el-form-item>
          <el-form-item label="今日重点文献最多展示"><el-input-number v-model="form.key_papers_max" :min="1" /></el-form-item>
          <el-form-item label="展示分数明细"><el-switch v-model="form.show_score_detail" /></el-form-item>
          <el-form-item label="展示弱相关文献"><el-switch v-model="form.show_weak_related" /></el-form-item>
        </el-form>

        <div class="settings-actions">
          <el-button @click="load">重新读取</el-button>
          <el-button plain @click="resetDefaults">恢复默认</el-button>
          <el-button plain :disabled="taskActive" @click="rescoreAll">重新计算全部推荐分</el-button>
          <el-button type="primary" :loading="saving" :disabled="taskActive" @click="openSaveDialog">保存配置</el-button>
        </div>
        <div v-if="rescoreTask" class="rescore-progress">
          <span>{{ rescoreTask.message }}</span>
          <el-progress :percentage="rescorePercent" :status="rescoreTask.status === 'success' ? 'success' : rescoreTask.status === 'failed' ? 'exception' : undefined" />
        </div>
      </el-card>
    </div>

    <el-dialog v-model="rescoreDialogVisible" title="保存评分规则" width="520px" append-to-body>
      <p class="muted">评分规则已修改，是否立即对已有文献重新评分？</p>
      <el-radio-group v-model="rescoreScope" class="rescore-options">
        <el-radio label="none">只保存，不重新评分</el-radio>
        <el-radio label="7">重新评分最近 7 天</el-radio>
        <el-radio label="30">重新评分最近 30 天</el-radio>
        <el-radio label="all">重新评分全部文献</el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="rescoreDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRules">确认保存</el-button>
      </template>
    </el-dialog>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminLayout from '../../components/AdminLayout.vue'
import DirectionMetricLabel from '../../components/DirectionMetricLabel.vue'
import { getActiveScoringRescore, getScoringDistribution, getScoringRescoreStatus, getScoringSettings, resetScoringSettings, saveScoringSettings, startScoringRescore } from '../../api/settings'

const saving = ref(false)
const rescoreDialogVisible = ref(false)
const rescoreScope = ref('none')
const distribution = ref({ total: 0, buckets: [] })
const distributionFilters = reactive({ range: 'all', include_deleted: false })
const rescoreTask = ref(null)
const taskActive = computed(() => ['pending', 'running'].includes(rescoreTask.value?.status))
const rescorePercent = computed(() => rescoreTask.value?.target_count ? Math.round(100 * rescoreTask.value.processed_count / rescoreTask.value.target_count) : rescoreTask.value?.status === 'success' ? 100 : 0)
let pollTimer = null

const form = reactive({
  title_factor: 3,
  abstract_factor: 2,
  raw_factor: 1,
  field_bonus: 5,
  bonus_ratio: 0.25,
  max_score: 100,
  report_min_score: 18,
  key_threshold: 30,
  normal_threshold: 12,
  low_score_threshold: 8,
  low_score_retention_days: 90,
  report_sort: 'score',
  sort_by_score_desc: true,
  group_by_direction: true,
  daily_max_papers: 80,
  key_papers_max: 8,
  show_score_detail: true,
  show_weak_related: false,
  key_demotion_terms: '',
})

async function load() {
  const resp = await getScoringSettings()
  Object.assign(form, resp.data.rules)
  await loadDistribution()
  const active = await getActiveScoringRescore()
  if (active.data.task) trackTask(active.data.task)
}

async function loadDistribution() {
  const resp = await getScoringDistribution({ ...distributionFilters })
  distribution.value = resp.data
}

function validateClient() {
  const numberKeys = [
    'title_factor',
    'abstract_factor',
    'raw_factor',
    'field_bonus',
    'bonus_ratio',
    'max_score',
    'report_min_score',
    'key_threshold',
    'normal_threshold',
    'low_score_threshold',
    'low_score_retention_days',
    'daily_max_papers',
    'key_papers_max',
  ]
  for (const key of numberKeys) {
    if (Number(form[key]) < 0) return `${key} 不能为负数`
  }
  if (form.key_threshold <= form.report_min_score) return '今日重点文献阈值应高于日报最低展示分数'
  if (form.low_score_threshold > form.report_min_score) return '低分条目阈值不应高于日报最低展示分数'
  if (form.low_score_retention_days < 30 || form.low_score_retention_days > 3650) return '低相关内容保留天数必须在 30-3650 天之间'
  if (form.normal_threshold < form.low_score_threshold || form.normal_threshold >= form.key_threshold) return '推荐等级阈值顺序不正确'
  if (form.max_score < 1 || form.max_score > 100) return '单篇文章最高分必须为 1-100'
  if (form.bonus_ratio > 0.25 || form.field_bonus > 5) return '奖励上限超出范围'
  if (form.daily_max_papers < 1) return '每日最多展示数量不能小于 1'
  if (form.key_papers_max < 1) return '今日重点文献最多展示数量不能小于 1'
  return ''
}

function openSaveDialog() {
  const error = validateClient()
  if (error) {
    ElMessage.warning(error)
    return
  }
  rescoreScope.value = 'none'
  rescoreDialogVisible.value = true
}

async function saveRules() {
  saving.value = true
  rescoreDialogVisible.value = false
  try {
    const resp = await saveScoringSettings({ rules: { ...form }, rescore_scope: rescoreScope.value })
    Object.assign(form, resp.data.rules)
    await loadDistribution()
    if (resp.data.task) trackTask(resp.data.task)
    ElMessage.success(resp.data.task ? '已保存规则，重新评分任务已启动' : '已保存评分规则')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存评分规则失败')
  } finally {
    saving.value = false
  }
}

function trackTask(task) {
  rescoreTask.value = task
  if (pollTimer) window.clearInterval(pollTimer)
  if (!['pending', 'running'].includes(task.status)) return
  pollTimer = window.setInterval(async () => {
    try {
      const resp = await getScoringRescoreStatus(task.task_id)
      rescoreTask.value = resp.data.task
      if (!['pending', 'running'].includes(resp.data.task.status)) {
        window.clearInterval(pollTimer)
        pollTimer = null
        await loadDistribution()
        ElMessage[resp.data.task.status === 'success' ? 'success' : 'warning'](resp.data.task.message)
      }
    } catch {
      window.clearInterval(pollTimer)
      pollTimer = null
      ElMessage.error('读取重新评分进度失败')
    }
  }, 2000)
}

async function rescoreAll() {
  await ElMessageBox.confirm('将重新计算全部文献的推荐分，并刷新已有日报。', '重新计算全部推荐分', { type: 'warning' })
  const resp = await startScoringRescore('all')
  trackTask(resp.data.task)
  ElMessage.info(resp.data.created ? '重新评分任务已启动' : '已有重新评分任务正在运行')
}

async function resetDefaults() {
  const resp = await resetScoringSettings()
  Object.assign(form, resp.data.rules)
  await loadDistribution()
  ElMessage.success('已恢复默认配置，请保存后按需重新评分')
}

onMounted(load)
onUnmounted(() => { if (pollTimer) window.clearInterval(pollTimer) })
</script>

<style scoped>
.term-setting {
  display: grid;
  gap: 8px;
  width: min(100%, 560px);
}
.settings-grid {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(320px, 1fr));
  gap: 16px;
}

.distribution-card {
  width: 100%;
  margin-bottom: 16px;
}

.distribution-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.distribution-note {
  flex: 1;
  color: #64748b;
  font-size: 13px;
}

.distribution-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.distribution-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(160px, 1fr));
  gap: 12px;
}

.distribution-item {
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(238, 248, 255, 0.94), rgba(255, 255, 255, 0.88));
  border: 1px solid rgba(47, 140, 255, 0.13);
}

.distribution-item-head {
  display: flex;
  justify-content: space-between;
  color: #0f172a;
  font-size: 14px;
}

.distribution-ratio {
  margin-top: 8px;
  color: var(--tech-blue);
  font-size: 24px;
  font-weight: 900;
}

.distribution-bar {
  height: 8px;
  margin: 10px 0 8px;
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

.distribution-item p {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.settings-card {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(47, 140, 255, 0.12);
}

.settings-form :deep(.el-select) {
  width: min(220px, 100%);
}

.rule-help {
  color: var(--text-muted);
  line-height: 1.5;
}

.settings-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.16);
}

.rescore-progress { display: grid; gap: 6px; margin-top: 14px; font-size: 13px; }

.rescore-options {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

@media (max-width: 1100px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .distribution-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 760px) {
  .distribution-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .distribution-controls {
    justify-content: flex-start;
  }

  .distribution-grid {
    grid-template-columns: 1fr;
  }
}
</style>
