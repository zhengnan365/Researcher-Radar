<template>
  <el-dialog v-model="visible" title="文献详情" class="paper-detail-dialog" width="min(900px, calc(100vw - 28px))" top="5vh">
    <template v-if="paper">
      <h2 class="detail-title">{{ paper.title }}</h2>
      <p class="detail-authors muted">{{ paper.authors || '未获取作者' }}</p>
      <div class="detail-overview">
        <span class="journal-name">{{ paper.journal || paper.source_name || '期刊未知' }}</span>
        <span>{{ paper.published_date || '日期未知' }}</span>
        <strong>{{ paper.recommend_score ?? 0 }} 分 · {{ levelText(paper.recommend_level) }}</strong>
        <el-button v-if="paper.url" tag="a" :href="paper.url" target="_blank" size="small" type="primary" plain>查看全文</el-button>
      </div>
      <el-tabs v-model="activeTab" class="detail-tabs">
        <el-tab-pane label="摘要" name="abstract">
          <p class="abstract">{{ paper.abstract || '暂无摘要' }}</p>
        </el-tab-pane>
        <el-tab-pane label="AI 速读" name="ai">
          <div class="ai-summary-head">
            <p class="muted ai-note">仅依据标题和原始摘要生成，不代表阅读全文。</p>
            <el-button :disabled="!paper.abstract" :loading="summaryLoading" @click="generateSummary()">
              {{ localSummary ? '重新生成' : '生成速读' }}
            </el-button>
          </div>
          <p v-if="localSummary" class="abstract ai-summary">{{ localSummary }}</p>
          <el-empty v-else-if="!summaryLoading" :description="paper.abstract ? '点击生成速读' : '缺少原始摘要，暂不能生成速读'" :image-size="72" />
          <p v-else class="muted ai-waiting">正在生成速读，请稍候…</p>
        </el-tab-pane>
        <el-tab-pane label="评分与信息" name="details">
          <el-descriptions :column="2" border size="small" class="detail-descriptions">
            <el-descriptions-item label="期刊">{{ paper.journal || '-' }}</el-descriptions-item>
            <el-descriptions-item label="发布日期">{{ paper.published_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="DOI">{{ paper.doi || '-' }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{ paper.source_name || paper.source_name_display || '-' }}</el-descriptions-item>
            <el-descriptions-item label="Zotero">{{ paper.zotero_imported ? '已导入' : '未导入' }}</el-descriptions-item>
            <el-descriptions-item label="推荐分数">
              {{ paper.recommend_score ?? 0 }} 分
              <span v-if="paper.relevance_override === 'irrelevant'" class="muted">（已标记不相关，系统原评分 {{ paper.system_recommend_score ?? 0 }} 分）</span>
            </el-descriptions-item>
            <el-descriptions-item label="推荐等级">{{ levelText(paper.recommend_level) }}</el-descriptions-item>
            <el-descriptions-item label="日报候选">{{ paper.is_daily_candidate ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="重点文献">{{ paper.is_key_paper ? '是' : '否' }}</el-descriptions-item>
            <el-descriptions-item label="命中字段" :span="2">{{ matchedFieldSummary(paper) || '-' }}</el-descriptions-item>
            <el-descriptions-item label="命中关键词" :span="2">{{ matchedKeywordNames(paper) || '-' }}</el-descriptions-item>
            <el-descriptions-item label="匹配方向" :span="2">{{ matchedDirectionNames(paper) || '-' }}</el-descriptions-item>
            <el-descriptions-item label="最近评分" :span="2">{{ formatDateTime(paper.scored_at) }}</el-descriptions-item>
          </el-descriptions>
          <el-collapse v-if="paper.score_detail?.version === 2" class="score-details">
            <el-collapse-item title="评分详情" name="score">
              <div v-if="paper.score_detail.exclusion" class="muted">排除原因：{{ paper.score_detail.exclusion }}</div>
              <template v-else>
                <div class="score-totals">
                  <span>关键词 {{ paper.score_detail.keyword_score }} 分</span>
                  <span><DirectionMetricLabel metric="relevance" label="研究相关度贡献" /> +{{ paper.score_detail.direction_bonus?.score || 0 }}</span>
                  <span>多字段 +{{ paper.score_detail.field_bonus || 0 }}</span>
                  <strong>最终 {{ paper.score_detail.final_score }} 分</strong>
                </div>
                <el-table :data="paper.score_detail.keywords || []" size="small" max-height="260">
                  <el-table-column prop="keyword" label="关键词" min-width="170" />
                  <el-table-column label="位置" width="105"><template #default="{ row }">{{ fieldText(row.field) }}</template></el-table-column>
                  <el-table-column prop="weight" label="权重" width="65" />
                  <el-table-column prop="factor" label="倍率" width="65" />
                  <el-table-column prop="score" label="贡献" width="75" />
                </el-table>
                <div v-if="paper.score_detail.direction_bonus?.name" class="score-note direction-score-note">
                  <div>研究方向：{{ paper.score_detail.direction_bonus.name }}</div>
                  <div><DirectionMetricLabel metric="relevance" />：{{ paper.score_detail.direction_bonus.weight }}</div>
                  <div>方向贡献：+{{ paper.score_detail.direction_bonus.score }} 分</div>
                </div>
                <p class="score-note muted"><DirectionMetricLabel metric="priority" />只影响排序，不计入推荐分。</p>
                <p class="score-note muted">奖励合计不超过关键词分的 25%；封顶前 {{ paper.score_detail.raw_score }} 分。</p>
                <p v-if="paper.score_detail.key_demotion_match" class="score-note muted">标题命中跨领域应用词“{{ paper.score_detail.key_demotion_match }}”，重点推荐降为 {{ paper.score_detail.final_score }} 分（原计算 {{ paper.score_detail.unrestricted_score }} 分）。</p>
              </template>
            </el-collapse-item>
          </el-collapse>
          <div class="tag-row">
            <el-tag v-for="item in paper.directions" :key="`d-${item.id}`" type="success">{{ item.name }}</el-tag>
            <el-tag v-for="item in paper.keywords" :key="`k-${item.id}`">{{ item.keyword }}</el-tag>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DirectionMetricLabel from './DirectionMetricLabel.vue'
import { summarizePaper } from '../api/papers'
import { fieldText, levelText, matchedDirectionNames, matchedFieldSummary, matchedKeywordNames } from '../utils/scoring'

const props = defineProps({
  modelValue: Boolean,
  paper: Object,
  aiReadRequest: { type: Number, default: 0 },
  focusAi: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'summary-updated'])
const summaryLoadingIds = ref(new Set())
const summaryLoading = computed(() => summaryLoadingIds.value.has(props.paper?.id))
const localSummary = ref('')
const activeTab = ref('abstract')
watch(() => props.paper?.id, () => {
  localSummary.value = props.paper?.ai_summary || ''
  activeTab.value = props.focusAi || props.paper?.ai_summary ? 'ai' : 'abstract'
}, { immediate: true })
watch(() => props.modelValue, (open) => {
  if (open) activeTab.value = props.focusAi || props.paper?.ai_summary ? 'ai' : 'abstract'
})
watch(() => props.aiReadRequest, () => {
  activeTab.value = 'ai'
  if (props.paper?.abstract && !props.paper.ai_summary) generateSummary(false)
})
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

async function generateSummary(force = Boolean(localSummary.value)) {
  if (!props.paper?.id) return
  const paperId = props.paper.id
  if (summaryLoadingIds.value.has(paperId)) return
  summaryLoadingIds.value.add(paperId)
  try {
    const response = await summarizePaper(paperId, force)
    if (props.paper?.id === paperId) localSummary.value = response.data.ai_summary || ''
    emit('summary-updated', response.data)
    ElMessage.success('AI 速读已生成')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || 'AI 速读生成失败')
  } finally {
    summaryLoadingIds.value.delete(paperId)
  }
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (item) => String(item).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
</script>

<style scoped>
:global(.paper-detail-dialog) {
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  overflow: hidden;
}
:global(.paper-detail-dialog .el-dialog__body) {
  min-height: 0;
  overflow-y: auto;
  padding-top: 8px;
}
:global(.paper-detail-dialog .el-dialog__header) { flex: none; }
.detail-title { margin: 0 0 8px; font-size: 21px; line-height: 1.35; color: #10243d; }
.detail-authors { margin: 0 0 12px; font-size: 13px; line-height: 1.5; }
.detail-overview { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin-bottom: 10px; color: #64748b; font-size: 13px; }
.detail-overview strong { color: #1769d8; }
.journal-name { color: #1769d8; font-weight: 700; }
.detail-tabs { min-height: 0; }
.detail-descriptions { margin-top: 4px; }
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0;
}
.abstract {
  margin: 8px 0;
  line-height: 1.65;
  font-size: 15px;
}
.ai-summary-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ai-note { margin: 0; font-size: 13px; }
.ai-summary { white-space: pre-wrap; padding: 14px; border-radius: 12px; background: #f2f7ff; }
.ai-waiting { margin: 28px 0; text-align: center; }
.score-details { margin-top: 14px; }
.score-totals { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; margin-bottom: 12px; font-size: 13px; }
.score-totals strong { font-size: 14px; }
.score-note { margin: 10px 0 0; font-size: 13px; line-height: 1.5; }
.direction-score-note { display: grid; gap: 3px; }
@media (max-width: 640px) {
  .detail-title { font-size: 18px; }
  .ai-summary-head { align-items: flex-start; }
  .detail-descriptions :deep(.el-descriptions__label) { width: 92px; }
}

</style>
