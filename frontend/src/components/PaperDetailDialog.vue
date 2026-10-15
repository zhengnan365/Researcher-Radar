<template>
  <el-dialog v-model="visible" title="文献详情" width="760px" @opened="handleOpened">
    <template v-if="paper">
      <h2>{{ paper.title }}</h2>
      <p class="muted">{{ paper.authors || '未获取作者' }}</p>
      <el-descriptions :column="2" border>
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
      <h3>摘要</h3>
      <p class="abstract">{{ paper.abstract || '暂无摘要' }}</p>
      <div ref="aiSummarySection" class="ai-summary-head">
        <h3>AI 速读</h3>
        <el-button :disabled="!paper.abstract" :loading="summaryLoading" @click="generateSummary()">
          {{ localSummary ? '重新生成' : '生成摘要' }}
        </el-button>
      </div>
      <p class="muted">仅依据标题和原始摘要生成，不代表阅读全文。</p>
      <p v-if="localSummary" class="abstract ai-summary">{{ localSummary }}</p>
      <div class="tag-row">
        <el-tag v-for="item in paper.directions" :key="`d-${item.id}`" type="success">{{ item.name }}</el-tag>
        <el-tag v-for="item in paper.keywords" :key="`k-${item.id}`">{{ item.keyword }}</el-tag>
      </div>
      <el-button v-if="paper.url" tag="a" :href="paper.url" target="_blank" type="primary" plain>全文</el-button>
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
const aiSummarySection = ref(null)
watch(() => props.paper?.id, () => { localSummary.value = props.paper?.ai_summary || '' }, { immediate: true })
watch(() => props.aiReadRequest, () => {
  if (props.paper?.abstract && !props.paper.ai_summary) generateSummary(false)
})
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

function handleOpened() {
  if (props.focusAi) aiSummarySection.value?.scrollIntoView({ block: 'center' })
}

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
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0;
}
.abstract {
  line-height: 1.75;
  font-size: 16px;
}
.ai-summary-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.ai-summary { white-space: pre-wrap; padding: 14px; border-radius: 12px; background: #f2f7ff; }
.score-details { margin-top: 14px; }
.score-totals { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; margin-bottom: 12px; font-size: 13px; }
.score-totals strong { font-size: 14px; }
.score-note { margin: 10px 0 0; font-size: 13px; line-height: 1.5; }
.direction-score-note { display: grid; gap: 3px; }

</style>
