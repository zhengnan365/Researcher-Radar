<template>
  <el-tooltip placement="top" :show-after="200">
    <template #content>
      <div class="metric-tooltip">
        <strong>{{ metric === 'relevance' ? '研究相关度 · Research Relevance' : '关注优先级 · Attention Priority' }}</strong>
        <p v-if="metric === 'relevance'">表示该方向与您长期科研兴趣的匹配程度，会参与文献推荐评分。数值越高，相关论文获得的方向加分越高。</p>
        <p v-else>表示您希望优先查看该方向的程度，不直接改变论文相关性评分。用于日报排序和文献列表同分时的排序。</p>
        <div v-for="item in levels" :key="item[0]">{{ item[0] }} = {{ item[1] }}</div>
      </div>
    </template>
    <span class="metric-label" tabindex="0">
      {{ label || (metric === 'relevance' ? '研究相关度' : '关注优先级') }}
      <el-icon class="metric-help-icon"><QuestionFilled /></el-icon>
    </span>
  </el-tooltip>
</template>

<script setup>
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { priorityLevels, relevanceLevels } from '../utils/directionMetrics'

const props = defineProps({
  metric: { type: String, required: true, validator: (value) => ['relevance', 'priority'].includes(value) },
  label: { type: String, default: '' },
})

const levels = computed(() => Object.entries(props.metric === 'relevance' ? relevanceLevels : priorityLevels))
</script>

<style scoped>
.metric-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: help;
  white-space: nowrap;
}

.metric-label:focus-visible {
  outline: 2px solid var(--tech-blue);
  outline-offset: 2px;
  border-radius: 3px;
}

.metric-help-icon {
  color: var(--text-muted);
  font-size: 13px;
}

.metric-tooltip {
  max-width: 310px;
  line-height: 1.55;
}

.metric-tooltip p {
  margin: 7px 0;
}
</style>
