<template>
  <el-card class="paper-card hover-lift" shadow="never">
    <template #header>
      <div class="card-head">
        <div class="title-row">
          <el-checkbox
            v-if="showSelect"
            :model-value="selected"
            @change="$emit('toggle-select', paper)"
          />
          <span class="paper-title" @click="$emit('detail', paper)">{{ paper.title }}</span>
        </div>
        <div class="card-actions">
          <el-tag class="score-tag" :class="{ 'is-key': paper.recommend_level === 'key' }" :type="levelType(paper.recommend_level)" effect="light">{{ scoreTitle(paper) }}</el-tag>
          <el-tag v-if="paper.zotero_imported" class="tag-zotero imported-tag" effect="plain">
            已导入 Zotero
            <template v-if="paper.zotero_collection_name"> · {{ paper.zotero_collection_name }}</template>
          </el-tag>
          <el-button
            class="ai-read-btn"
            plain
            :disabled="!paper.abstract && !paper.ai_summary"
            :title="!paper.abstract && !paper.ai_summary ? '缺少原始摘要，暂不能生成 AI 速读' : '查看或生成 AI 速读'"
            @click="$emit('ai-read', paper)"
          >AI 速读</el-button>
          <el-button v-if="paper.url" type="primary" plain @click="openUrl">全文</el-button>
          <el-button type="info" plain :loading="irrelevantLoading" title="设为 0 分并从列表隐藏，数据库记录仍用于去重" @click="$emit('mark-irrelevant', paper)">不相关</el-button>
          <el-button v-if="!paper.zotero_imported" class="zotero-import-btn" plain @click="$emit('import-zotero', paper)">
            导入 Zotero
          </el-button>
          <el-button :type="paper.is_favorite ? 'warning' : 'default'" @click="$emit('toggle-favorite', paper)">
            <span class="star">{{ paper.is_favorite ? '★' : '☆' }}</span>
            {{ paper.is_favorite ? '已收藏' : '收藏' }}
          </el-button>
        </div>
      </div>
    </template>

    <p class="muted paper-authors">{{ paper.authors || '未获取作者' }}</p>
    <div class="meta-line">
      <span class="journal-name">{{ cleanJournal(paper.journal) }}</span>
      <span class="meta-date">· 入库 {{ formatPaperDate(paper.created_at) }} · {{ publicationDateLabel(paper) }}</span>
      <template v-if="paper.doi">
        <span class="dot">·</span>
        <el-link :href="doiUrl" target="_blank" type="primary">DOI: {{ paper.doi }}</el-link>
        <el-button class="copy-doi-btn" size="small" text @click="copyDoi">复制 DOI</el-button>
      </template>
    </div>

    <div class="score-line">
      <span>{{ hitSummary(paper) }}</span>
      <span v-if="matchedDirectionNames(paper)">匹配方向：{{ matchedDirectionNames(paper) }}</span>
    </div>

    <p class="abstract" :class="{ empty: !paper.abstract, 'is-collapsed': abstractExpandable && !abstractExpanded }">{{ paper.abstract || '暂无摘要' }}</p>
    <el-button v-if="abstractExpandable" class="abstract-toggle" text size="small" :aria-expanded="abstractExpanded" @click="abstractExpanded = !abstractExpanded">
      {{ abstractExpanded ? '收起摘要' : '展开摘要' }}
    </el-button>

    <div v-if="paper.directions?.length || paper.keywords?.length" class="tag-row">
      <el-tag v-for="item in paper.directions" :key="`d-${item.id}`" class="tag-direction">{{ item.name }}</el-tag>
      <el-tag v-for="item in paper.keywords" :key="`k-${item.id}`" class="tag-keyword">{{ item.keyword }}</el-tag>
    </div>
  </el-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { hitSummary, levelType, matchedDirectionNames, scoreTitle } from '../utils/scoring'

const props = defineProps({
  paper: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  showSelect: { type: Boolean, default: false },
  irrelevantLoading: { type: Boolean, default: false },
})
defineEmits(['detail', 'ai-read', 'toggle-favorite', 'import-zotero', 'toggle-select', 'mark-irrelevant'])

const doiUrl = computed(() => props.paper.doi ? `https://doi.org/${props.paper.doi}` : '')
const abstractExpanded = ref(false)
const abstractExpandable = computed(() => (props.paper.abstract || '').length > 220)
const now = new Date()
const todayText = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

function formatPaperDate(value) {
  if (!value) return '未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function publicationDateLabel(paper) {
  if (!paper.published_date) return '期刊日期未知'
  return `${paper.published_date > todayText ? '期刊预标日期' : '期刊日期'} ${paper.published_date}`
}

function cleanJournal(value) {
  return String(value || '未知期刊').replace(/^ScienceDirect Publication:\s*/i, '')
}

function openUrl() {
  if (props.paper.url) window.open(props.paper.url, '_blank', 'noopener,noreferrer')
}

async function copyDoi() {
  if (!props.paper.doi) return
  await navigator.clipboard.writeText(props.paper.doi)
  ElMessage.success('已复制 DOI')
}
</script>

<style scoped>
.paper-card {
  position: relative;
  overflow: hidden;
  margin-bottom: 16px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.74);
  box-shadow: 0 16px 42px rgba(47, 140, 255, 0.1);
  backdrop-filter: blur(16px);
}

.paper-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 18px;
  bottom: 18px;
  width: 4px;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--tech-blue), var(--cyan), var(--violet));
  opacity: 0.86;
}

.paper-card:hover::before {
  opacity: 1;
  box-shadow: 0 0 18px rgba(47, 140, 255, 0.5);
}

.paper-card :deep(.el-card__body) {
  padding-top: 10px;
}

.card-head {
  display: flex;
  gap: 16px;
  justify-content: space-between;
  align-items: flex-start;
}

.title-row {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  max-width: 46%;
}

.imported-tag {
  max-width: min(280px, 100%);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score-tag {
  font-weight: 800;
}

.score-tag.is-key {
  --el-tag-bg-color: #eaf3ff;
  --el-tag-border-color: #bbd6f3;
  --el-tag-text-color: #245b91;
}

.ai-read-btn {
  color: #0f766e;
  border-color: rgba(15, 118, 110, 0.28);
  background: rgba(20, 184, 166, 0.08);
  font-weight: 700;
}

.ai-read-btn:hover {
  color: #0b5e58;
  border-color: rgba(15, 118, 110, 0.44);
  background: rgba(20, 184, 166, 0.14);
}

.zotero-import-btn {
  color: #5b4ae6;
  border-color: rgba(124, 108, 255, 0.28);
  background: rgba(124, 108, 255, 0.08);
  font-weight: 700;
}

.zotero-import-btn:hover {
  color: #4938c7;
  border-color: rgba(124, 108, 255, 0.44);
  background: rgba(124, 108, 255, 0.14);
}

.star {
  margin-right: 3px;
  font-size: 16px;
}

.paper-authors {
  margin: 0;
  line-height: 1.5;
}

.meta-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0 10px;
  font-size: 15px;
}

.journal-name {
  color: #1769d8;
  font-weight: 700;
}

.meta-date {
  color: var(--text-muted);
}

.dot {
  color: #98a2b3;
}

.copy-doi-btn {
  padding: 0 4px;
  height: auto;
  color: #1d4ed8;
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  font-weight: 700;
}

.copy-doi-btn:hover {
  color: #0f766e;
  background: transparent !important;
}

.score-line {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 8px 0 10px;
  color: #475569;
  font-size: 14px;
}

.score-line span {
  padding: 4px 9px;
  border-radius: 999px;
  background: rgba(47, 140, 255, 0.08);
  border: 1px solid rgba(47, 140, 255, 0.12);
}

.abstract {
  line-height: 1.7;
  padding: 12px 14px;
  border-left: 4px solid rgba(47, 140, 255, 0.24);
  background: rgba(238, 248, 255, 0.74);
  border-radius: 14px;
}

.abstract.empty {
  color: #8a94a6;
  background: rgba(247, 248, 250, 0.72);
  border-left-color: #d9dee8;
}

.abstract.is-collapsed {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.abstract-toggle {
  margin-top: -8px;
  padding-left: 14px;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}

@media (max-width: 1280px) {
  .card-head {
    flex-direction: column;
  }

  .card-actions {
    width: 100%;
    max-width: none;
    justify-content: flex-start;
  }
}

@media (max-width: 760px) {
  .paper-card {
    border-radius: 18px;
  }

  .title-row {
    flex-direction: column;
  }

  .meta-line,
  .score-line {
    font-size: 13px;
  }
}
</style>
