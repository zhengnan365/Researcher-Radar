<template>
  <div class="zotero-desktop fade-in" :class="{ 'detail-collapsed': detailCollapsed }" :style="{ '--tree-width': `${treeWidth}px` }">
    <aside class="zotero-tree">
      <div class="tree-actions">
        <div class="tree-action-row">
          <el-button class="sync-button" size="small" type="primary" :icon="Refresh" :loading="quickSyncing" :disabled="fullSyncing" @click.stop="loadLibrary({ refresh: true })">同步</el-button>
          <el-dropdown trigger="click" @command="handleLibraryAction">
            <el-button class="more-button" size="small" plain :icon="MoreFilled" :disabled="quickSyncing || fullSyncing" title="更多同步操作" aria-label="更多同步操作" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="full-sync" title="重新核对 Zotero 服务器和本地缓存；不会删除服务器上的文献">全量校准</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div v-if="syncStatusKind === 'running' || syncStatusKind === 'failed'" class="sync-notice" :class="`is-${syncStatusKind}`" role="status" aria-live="polite">
        <strong>{{ syncStatusTitle }}</strong>
        <p>{{ syncStatusMessage }}</p>
        <router-link v-if="syncStatusKind === 'failed'" to="/admin/zotero">检查 Zotero 设置</router-link>
      </div>

      <div class="tree-scroll">
        <div class="tree-heading">
          <div class="tree-root" :class="{ active: selectedKey === '__all__' }">
            <button class="tree-caret" type="button" :aria-label="libraryExpanded ? '折叠文献库' : '展开文献库'" :aria-expanded="libraryExpanded" @click.stop="toggleLibrary">{{ libraryExpanded ? '▾' : '▸' }}</button>
            <span class="library-mark" @click="selectAll"></span>
            <strong @click="selectAll">My Library</strong>
          </div>
          <el-button class="tree-add-button" text :icon="Plus" :loading="creatingCollection" title="新建文件夹" aria-label="新建文件夹" @click.stop="openCreateCollectionDialog" />
        </div>

        <div v-show="libraryExpanded" class="collection-list">
          <button
            v-for="node in flatCollectionTree"
            :key="node.key"
            class="collection-row"
            :class="{ active: selectedKey === node.key }"
            :style="{ '--depth': node.depth }"
            :title="node.name"
            @click="selectCollection(node)"
          >
            <span
              class="node-caret"
              :class="{ empty: !node.children.length }"
              @click.stop="toggleNode(node)"
            >
              {{ node.children.length ? (isExpanded(node.key) ? '▾' : '▸') : '' }}
            </span>
            <span class="folder-mark" :class="{ open: node.children.length && isExpanded(node.key) }"></span>
            <span class="collection-name">{{ node.name }}</span>
            <em v-if="node.count">{{ node.count }}</em>
          </button>

          <button
            v-if="library?.uncategorized_count"
            class="collection-row"
            :class="{ active: selectedKey === 'uncategorized' }"
            :style="{ '--depth': 0 }"
            @click="selectUncategorized"
          >
            <span class="node-caret empty"></span>
            <span class="folder-mark muted-folder"></span>
            <span class="collection-name">未分类</span>
            <em>{{ library.uncategorized_count }}</em>
          </button>
        </div>
      </div>

      <div class="sync-footer" :class="`is-${syncStatusKind}`">
        <button class="sync-footer-toggle" type="button" :aria-expanded="syncDetailsExpanded" :aria-label="syncDetailsExpanded ? '收起同步详情' : '展开同步详情'" @click="syncDetailsExpanded = !syncDetailsExpanded">
          <span class="sync-dot" aria-hidden="true"></span>
          <span class="sync-footer-label">{{ syncFooterText }}</span>
          <el-icon><ArrowUp v-if="!syncDetailsExpanded" /><ArrowDown v-else /></el-icon>
        </button>
        <div v-if="syncDetailsExpanded" class="sync-footer-details" role="status" aria-live="polite">
          <strong>{{ syncStatusTitle }}</strong>
          <p>{{ syncStatusMessage }}</p>
          <span v-if="lastSyncedAt">上次成功：{{ formatZoteroDate(lastSyncedAt) }}</span>
          <router-link v-if="syncStatusKind === 'failed'" to="/admin/zotero">检查 Zotero 设置</router-link>
        </div>
      </div>
    </aside>

    <div class="zotero-resizer" title="拖动调整文件夹栏宽度" @pointerdown="startTreeResize"></div>

    <main class="zotero-table-pane">
      <div class="library-filters">
        <el-input v-model="searchQuery" clearable placeholder="搜索标题、作者或 DOI" aria-label="搜索标题、作者或 DOI" />
        <el-select v-model="yearFilter" class="filter-select" placeholder="全部年份" aria-label="按年份筛选">
          <el-option label="全部年份" value="" />
          <el-option v-for="year in availableYears" :key="year" :label="year" :value="year" />
        </el-select>
        <el-select v-model="typeFilter" class="filter-select" placeholder="全部类型" aria-label="按类型筛选">
          <el-option label="全部类型" value="" />
          <el-option v-for="type in availableTypes" :key="type" :label="itemTypeLabel(type)" :value="type" />
        </el-select>
        <span class="filter-count">{{ hasActiveFilters ? `筛选 ${resultTotal} / ${folderTotal} 条` : `共 ${resultTotal} 条` }}</span>
      </div>
      <div v-if="pageError" class="page-error" role="alert">
        <span>{{ pageError }}</span>
        <el-button type="primary" link @click="loadPage()">重试读取</el-button>
      </div>
      <div v-loading="pageLoading" class="library-table-wrap">
        <el-table
          ref="libraryTable"
          row-key="key"
          :data="pageItems"
          height="100%"
          stripe
          highlight-current-row
          @current-change="handleCurrentItemChange"
          @sort-change="handleSortChange"
          @scroll="handleTableScroll"
        >
          <el-table-column prop="title" label="标题" min-width="520" sortable="custom" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.title || '无标题' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="creator" label="作者" width="240" sortable="custom" show-overflow-tooltip />
          <el-table-column prop="date" label="日期" width="150" sortable="custom" show-overflow-tooltip />
          <el-table-column prop="journal" label="期刊 / 出版物" width="260" sortable="custom" show-overflow-tooltip />
          <template #empty>
            <div class="library-empty">{{ pageError || tableEmptyMessage }}</div>
          </template>
          <template #append>
            <div v-if="loadingMore" class="library-load-more">正在加载…</div>
          </template>
        </el-table>
      </div>
    </main>

    <aside class="zotero-detail">
      <div class="detail-header">
        <span v-if="!detailCollapsed">详细信息</span>
        <el-button
          class="detail-toggle"
          text
          :icon="detailCollapsed ? ArrowLeft : ArrowRight"
          :title="detailCollapsed ? '展开右侧详情栏' : '折叠右侧详情栏'"
          :aria-label="detailCollapsed ? '展开右侧详情栏' : '折叠右侧详情栏'"
          :aria-expanded="!detailCollapsed"
          @click="detailCollapsed = !detailCollapsed"
        />
      </div>
      <template v-if="!detailCollapsed && selectedItem">
        <div class="detail-tabs">
          <button class="active">Information</button>
        </div>

        <div v-loading="detailLoading" class="detail-scroll">
          <section class="detail-section">
            <div class="item-type-row">
              <span class="item-type-icon large">{{ iconFor(selectedItem.item_type) }}</span>
              <div>
                <span class="field-label">Item Type</span>
                <strong>{{ itemTypeLabel(selectedItem.item_type) }}</strong>
              </div>
            </div>
            <h3>{{ selectedItem.title || 'Untitled' }}</h3>
          </section>

          <section class="detail-section">
            <dl class="info-list">
              <template v-for="field in infoFields" :key="field.label">
                <dt v-if="field.value">{{ field.label }}</dt>
                <dd v-if="field.value">
                  <a v-if="field.url" :href="field.url" target="_blank" rel="noreferrer">{{ field.value }}</a>
                  <span v-else>{{ field.value }}</span>
                </dd>
              </template>
            </dl>
          </section>

          <section v-if="selectedItem.creators?.length" class="detail-section">
            <h4>Creators</h4>
            <dl class="info-list compact">
              <template v-for="(creator, index) in selectedItem.creators" :key="`${creator.name}-${index}`">
                <dt>{{ creatorTypeLabel(creator.type) }}</dt>
                <dd>{{ creator.name }}</dd>
              </template>
            </dl>
          </section>

          <section v-if="selectedItem.abstract" class="detail-section">
            <h4>Abstract</h4>
            <p class="abstract-text">{{ selectedItem.abstract }}</p>
          </section>

          <section v-if="selectedItem.tags?.length" class="detail-section">
            <h4>Tags</h4>
            <div class="tag-list">
              <span v-for="tag in selectedItem.tags" :key="tag">{{ tag }}</span>
            </div>
          </section>
        </div>
      </template>

      <div v-else-if="!detailCollapsed" class="detail-empty">
        <div class="detail-count">{{ resultTotal }}</div>
        <p>条符合当前条件</p>
        <span>点击中间表格中的条目查看详细信息</span>
      </div>
    </aside>

    <el-dialog
      v-model="createCollectionDialogVisible"
      title="新建 Zotero 文件夹"
      width="460px"
      append-to-body
      class="collection-dialog"
    >
      <el-form label-width="96px">
        <el-form-item label="文件夹名称">
          <el-input
            v-model="collectionForm.name"
            placeholder="请输入新文件夹名称"
            maxlength="80"
            show-word-limit
            @keyup.enter="submitCreateCollection"
          />
        </el-form-item>
        <el-form-item label="新建位置">
          <el-select v-model="collectionForm.parent_key" filterable class="full-width">
            <el-option label="My Library（顶层）" value="" />
            <el-option
              v-for="collection in collectionParentOptions"
              :key="collection.key"
              :label="collection.label"
              :value="collection.key"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createCollectionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingCollection" @click="submitCreateCollection">新建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, MoreFilled, Plus, Refresh } from '@element-plus/icons-vue'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createZoteroCollection, getZoteroItem, getZoteroLibraryItems, getZoteroSyncStatus, readZoteroLibrary } from '../api/zotero'

const quickSyncing = ref(false)
const fullSyncing = ref(false)
const initialLoading = ref(false)
const library = ref(null)
const selectedKey = ref('__all__')
const selectedItem = ref(null)
const detailCollapsed = ref(false)
const detailLoading = ref(false)
const expandedKeys = ref(new Set())
const libraryExpanded = ref(true)
const sortState = ref({ prop: '', order: '' })
const treeWidth = ref(readTreeWidth())
const resizingTree = ref(false)
const createCollectionDialogVisible = ref(false)
const creatingCollection = ref(false)
const syncState = ref(null)
const syncDetailsExpanded = ref(false)
const loadError = ref('')
const pageError = ref('')
const searchQuery = ref('')
const yearFilter = ref('')
const typeFilter = ref('')
const libraryTable = ref(null)
const pageItems = ref([])
const resultTotal = ref(0)
const folderTotal = ref(0)
const currentPage = ref(1)
const pageSize = 100
const pageLoading = ref(false)
const loadingMore = ref(false)
const appliedSearch = ref('')
let backgroundPollTimer = null
let searchTimer = null
let pageRequestId = 0
const collectionForm = reactive({
  name: '',
  parent_key: '',
})

const collections = computed(() => library.value?.collections || [])
const lastSyncedAt = computed(() => library.value?.last_synced_at || syncState.value?.last_synced_at || '')
const syncStatusKind = computed(() => {
  if (initialLoading.value && !library.value) return 'running'
  if (syncState.value?.status === 'running') return 'running'
  if (loadError.value || syncState.value?.status === 'failed' || library.value?.sync_error) return 'failed'
  if (lastSyncedAt.value) return 'success'
  return 'idle'
})
const syncStatusTitle = computed(() => ({
  running: initialLoading.value && !library.value ? '正在读取文献库' : '正在同步 Zotero',
  failed: 'Zotero 同步失败',
  success: 'Zotero 已同步',
  idle: '尚未同步 Zotero',
})[syncStatusKind.value])
const syncStatusMessage = computed(() => {
  if (initialLoading.value && !library.value) return '正在读取本地缓存…'
  if (syncStatusKind.value === 'failed') return loadError.value || syncState.value?.error || library.value?.sync_error || '同步失败，请重试。'
  if (syncStatusKind.value === 'running') return syncState.value?.mode === 'full' ? '正在后台全量校准，完成后会自动更新列表。' : '正在后台同步，完成后会自动更新列表。'
  if (syncStatusKind.value === 'success') return `本地缓存 ${library.value?.cached_total_items ?? 0} 条文献。`
  return '同步后可在这里搜索和浏览文献。'
})
const syncFooterText = computed(() => {
  if (syncStatusKind.value === 'running') return initialLoading.value && !library.value ? '正在读取文献库' : '正在同步 Zotero'
  if (syncStatusKind.value === 'failed') return '同步失败 · 查看原因'
  if (!lastSyncedAt.value) return '尚未同步'
  return `已同步 ${library.value?.cached_total_items ?? 0} 条 · ${formatSyncTime(lastSyncedAt.value)}`
})
const tableEmptyMessage = computed(() => {
  if (syncStatusKind.value === 'running') return '正在同步 Zotero 文献库，请稍候…'
  if (syncStatusKind.value === 'failed' && !library.value?.cached_total_items) return '同步失败，请查看左侧错误信息并重试。'
  if (library.value?.cached_total_items && !resultTotal.value) return '没有符合当前筛选条件的文献。'
  return '文献库暂无条目。'
})
const availableYears = computed(() => library.value?.available_years || [])
const availableTypes = computed(() => library.value?.available_types || [])

const collectionTree = computed(() => {
  const nodes = new Map()
  collections.value.forEach((item) => {
    nodes.set(item.key, {
      ...item,
      depth: 0,
      count: library.value?.collection_counts?.[item.key] || 0,
      children: [],
    })
  })

  const roots = []
  nodes.forEach((node) => {
    const parent = node.parent && nodes.get(node.parent)
    if (parent) parent.children.push(node)
    else roots.push(node)
  })

  const sortNodes = (rows, depth = 0) => {
    rows.sort((a, b) => naturalCompare(a.name, b.name))
    rows.forEach((row) => {
      row.depth = depth
      sortNodes(row.children, depth + 1)
    })
  }
  sortNodes(roots)
  return roots
})

const flatCollectionTree = computed(() => {
  const rows = []
  const visit = (nodes) => {
    nodes.forEach((node) => {
      rows.push(node)
      if (node.children.length && isExpanded(node.key)) visit(node.children)
    })
  }
  visit(collectionTree.value)
  return rows
})

const hasActiveFilters = computed(() => Boolean(searchQuery.value.trim() || yearFilter.value || typeFilter.value))
watch(searchQuery, (value) => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => { appliedSearch.value = value.trim() }, 300)
})
watch([selectedKey, yearFilter, typeFilter, sortState, appliedSearch], () => {
  libraryTable.value?.setCurrentRow(null)
  selectedItem.value = null
  if (library.value) loadPage()
})

const collectionParentOptions = computed(() => {
  return [...collections.value]
    .sort((a, b) => naturalCompare(a.path || a.label || a.name, b.path || b.label || b.name))
    .map((collection) => ({
      key: collection.key,
      label: collection.path || collection.label || collection.name,
    }))
})

const infoFields = computed(() => {
  const item = selectedItem.value || {}
  return [
    { label: 'Publication', value: item.journal },
    { label: 'Date', value: item.date },
    { label: 'DOI', value: item.doi, url: item.doi ? `https://doi.org/${item.doi}` : '' },
    { label: 'URL', value: item.url, url: item.url },
    { label: 'Publisher', value: item.publisher },
    { label: 'Volume', value: item.volume },
    { label: 'Issue', value: item.issue },
    { label: 'Pages', value: item.pages },
    { label: 'ISSN', value: item.issn },
    { label: 'ISBN', value: item.isbn },
    { label: 'Language', value: item.language },
    { label: 'Library Catalog', value: item.library_catalog },
    { label: 'Archive', value: item.archive },
    { label: 'Accessed', value: formatZoteroDate(item.access_date) },
    { label: 'Date Added', value: formatZoteroDate(item.date_added) },
    { label: 'Date Modified', value: formatZoteroDate(item.date_modified) },
    { label: 'Collection', value: item.collections?.map((collection) => collection.name).join(', ') || '未分类' },
    { label: 'Extra', value: item.extra },
  ]
})

async function loadLibrary(options = {}) {
  const refresh = Boolean(options.refresh)
  const fullSync = Boolean(options.fullSync)
  if (fullSync) fullSyncing.value = true
  else if (refresh) quickSyncing.value = true
  else initialLoading.value = true
  loadError.value = ''
  try {
    const resp = await readZoteroLibrary({ max_items: 0, include_items: false, refresh, full_sync: fullSync, background: refresh })
    await applyLibraryData(resp.data)
    applySyncState(resp.data.sync_state)
    if (resp.data.sync_state?.status === 'running') {
      if (resp.data.sync_started) {
        ElMessage.info(`${resp.data.sync_state.mode === 'full' ? '全量校准' : '快速同步'}已在后台开始。`)
      } else if (resp.data.sync_already_running && refresh) {
        ElMessage.info('已有 Zotero 同步正在后台运行。')
      }
      scheduleBackgroundRefresh()
    } else if (resp.data.sync_already_running) {
      ElMessage.info('已有 Zotero 同步正在后台运行。')
    } else if (resp.data.sync_error) {
      loadError.value = resp.data.sync_error
      ElMessage.warning(`已显示本地缓存，远端同步失败：${resp.data.sync_error}`)
    } else if (refresh) {
      ElMessage.success(`${fullSync ? '全量校准' : '快速同步'}完成，当前 ${resp.data.cached_total_items} 条 Zotero 条目`)
    }
  } catch (error) {
    loadError.value = error.response?.data?.detail || error.message || '读取 Zotero 文献库失败'
    ElMessage.error(loadError.value)
  } finally {
    initialLoading.value = false
    if (!isSyncRunning()) {
      quickSyncing.value = false
      fullSyncing.value = false
    }
  }
}

async function applyLibraryData(data) {
  const loadedPages = currentPage.value
  const scrollWrapper = libraryTable.value?.$el?.querySelector('.el-scrollbar__wrap')
  const scrollTop = scrollWrapper?.scrollTop || 0
  library.value = data
  const collectionKeys = new Set((data.collections || []).map((collection) => collection.key))
  expandedKeys.value = new Set([...expandedKeys.value].filter((key) => collectionKeys.has(key)))
  if (selectedKey.value !== '__all__' && selectedKey.value !== 'uncategorized' && !collectionKeys.has(selectedKey.value)) {
    selectedKey.value = '__all__'
  }
  if (selectedKey.value === 'uncategorized' && !data.uncategorized_count) selectedKey.value = '__all__'

  const selectedItemKey = selectedItem.value?.key
  await loadPage()
  for (let page = 1; page < loadedPages && pageItems.value.length < resultTotal.value; page++) {
    await loadPage({ append: true })
  }
  await nextTick()
  if (scrollWrapper) scrollWrapper.scrollTop = scrollTop
  if (!selectedItemKey) return
  const row = pageItems.value.find((item) => item.key === selectedItemKey)
  if (row) libraryTable.value?.setCurrentRow(row)
  else selectedItem.value = null
}

async function loadPage({ append = false } = {}) {
  if (append && (pageLoading.value || loadingMore.value || pageItems.value.length >= resultTotal.value)) return
  const requestId = ++pageRequestId
  if (append) loadingMore.value = true
  else {
    pageLoading.value = true
    loadingMore.value = false
    pageError.value = ''
    libraryTable.value?.$el?.querySelector('.el-scrollbar__wrap')?.scrollTo({ top: 0 })
  }
  try {
    const response = await getZoteroLibraryItems({
      collection: selectedKey.value,
      search: appliedSearch.value,
      year: yearFilter.value,
      item_type: typeFilter.value,
      sort_by: sortState.value.prop || 'title',
      sort_order: sortState.value.order || 'ascending',
      page: append ? currentPage.value + 1 : 1,
      page_size: pageSize,
    })
    if (requestId !== pageRequestId) return
    const rows = response.data.items || []
    pageItems.value = append ? [...pageItems.value, ...rows] : rows
    pageError.value = ''
    resultTotal.value = response.data.total || 0
    folderTotal.value = response.data.folder_total || 0
    currentPage.value = response.data.page || 1
  } catch (error) {
    if (requestId !== pageRequestId) return
    const detail = error.response?.status === 404
      ? '后端服务尚未加载新版 Zotero 接口，请重启后端服务。'
      : error.response?.data?.detail || (error.code === 'ECONNABORTED' ? '读取 Zotero 列表超时，请重试。' : '读取 Zotero 列表失败，请检查后端服务。')
    pageError.value = detail
    ElMessage.error(detail)
  } finally {
    if (requestId === pageRequestId) {
      pageLoading.value = false
      loadingMore.value = false
    }
  }
}

function handleTableScroll() {
  const wrapper = libraryTable.value?.$el?.querySelector('.el-scrollbar__wrap')
  if (wrapper && wrapper.scrollTop + wrapper.clientHeight >= wrapper.scrollHeight - 240) {
    loadPage({ append: true })
  }
}

function handleLibraryAction(command) {
  if (command === 'full-sync') loadLibrary({ refresh: true, fullSync: true })
}

function applySyncState(state = {}) {
  syncState.value = state
  const running = state?.status === 'running'
  quickSyncing.value = running && state.mode !== 'full'
  fullSyncing.value = running && state.mode === 'full'
}

function isSyncRunning() {
  return quickSyncing.value || fullSyncing.value
}

function scheduleBackgroundRefresh() {
  if (backgroundPollTimer) window.clearInterval(backgroundPollTimer)
  backgroundPollTimer = window.setInterval(async () => {
    try {
      const statusResp = await getZoteroSyncStatus()
      const state = statusResp.data || {}
      applySyncState(state)
      if (state.status !== 'running') {
        stopBackgroundRefresh()
        const libraryResp = await readZoteroLibrary({ max_items: 0, include_items: false, refresh: false })
        await applyLibraryData(libraryResp.data)
        if (state.status === 'success') loadError.value = ''
        if (state.status === 'failed') loadError.value = state.error || 'Zotero 同步失败'
        if (state.status === 'success') {
          ElMessage.success(`${state.mode === 'full' ? '全量校准' : '快速同步'}完成，当前 ${libraryResp.data.cached_total_items} 条 Zotero 条目`)
        } else if (state.status === 'failed') {
          ElMessage.error(state.error || 'Zotero 同步失败')
        }
      }
    } catch (error) {
      loadError.value = error.response?.data?.detail || error.message || '无法读取 Zotero 同步状态'
    }
  }, 3000)
}

function stopBackgroundRefresh() {
  if (backgroundPollTimer) {
    window.clearInterval(backgroundPollTimer)
    backgroundPollTimer = null
  }
}

function selectAll() {
  selectedKey.value = '__all__'
  selectedItem.value = null
}

function selectCollection(node) {
  selectedKey.value = node.key
  selectedItem.value = null
}

function selectUncategorized() {
  selectedKey.value = 'uncategorized'
  selectedItem.value = null
}

function handleSortChange({ prop, order }) {
  sortState.value = { prop: prop || '', order: order || '' }
}

async function handleCurrentItemChange(row) {
  selectedItem.value = row || null
  if (!row?.key) return
  const requestedKey = row.key
  detailLoading.value = true
  try {
    const response = await getZoteroItem(requestedKey)
    if (selectedItem.value?.key === requestedKey) {
      selectedItem.value = response.data
    }
  } catch (error) {
    if (selectedItem.value?.key === requestedKey) {
      ElMessage.error(error.response?.data?.detail || '读取 Zotero 条目详情失败')
    }
  } finally {
    if (selectedItem.value?.key === requestedKey) detailLoading.value = false
  }
}

function toggleLibrary() {
  libraryExpanded.value = !libraryExpanded.value
}

function toggleNode(node) {
  if (!node.children.length) return
  const next = new Set(expandedKeys.value)
  if (next.has(node.key)) next.delete(node.key)
  else next.add(node.key)
  expandedKeys.value = next
}

function isExpanded(key) {
  return expandedKeys.value.has(key)
}

function startTreeResize(event) {
  resizingTree.value = true
  document.body.classList.add('zotero-resizing')
  window.addEventListener('pointermove', resizeTree)
  window.addEventListener('pointerup', stopTreeResize)
  window.addEventListener('pointercancel', stopTreeResize)
  resizeTree(event)
}

function resizeTree(event) {
  if (!resizingTree.value) return
  const left = document.querySelector('.zotero-desktop')?.getBoundingClientRect().left || 0
  treeWidth.value = clamp(Math.round(event.clientX - left), 240, 600)
}

function stopTreeResize() {
  if (!resizingTree.value) return
  resizingTree.value = false
  document.body.classList.remove('zotero-resizing')
  localStorage.setItem('zotero-tree-width', String(treeWidth.value))
  window.removeEventListener('pointermove', resizeTree)
  window.removeEventListener('pointerup', stopTreeResize)
  window.removeEventListener('pointercancel', stopTreeResize)
}

function openCreateCollectionDialog() {
  collectionForm.name = ''
  collectionForm.parent_key = selectedKey.value && !['__all__', 'uncategorized'].includes(selectedKey.value)
    ? selectedKey.value
    : ''
  createCollectionDialogVisible.value = true
}

async function submitCreateCollection() {
  const name = collectionForm.name.trim()
  if (!name) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  creatingCollection.value = true
  try {
    const resp = await createZoteroCollection({
      name,
      parent_key: collectionForm.parent_key,
    })
    const collection = resp.data.collection
    if (collection?.key) {
      upsertLocalCollection(collection)
      if (collection.parent) {
        expandedKeys.value = new Set([...expandedKeys.value, collection.parent])
      }
      libraryExpanded.value = true
      selectedKey.value = collection.key
      selectedItem.value = null
    }
    createCollectionDialogVisible.value = false
    ElMessage.success(resp.data.message || '文件夹创建成功')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '创建 Zotero 文件夹失败')
  } finally {
    creatingCollection.value = false
  }
}

function upsertLocalCollection(collection) {
  if (!library.value) {
    library.value = { collections: [], total_items: 0, cached_total_items: 0, collection_counts: {} }
  }
  const rows = [...(library.value.collections || [])]
  const index = rows.findIndex((item) => item.key === collection.key)
  if (index >= 0) rows[index] = collection
  else rows.push(collection)
  library.value = {
    ...library.value,
    collections: rows,
    collection_counts: { ...library.value.collection_counts, [collection.key]: 0 },
  }
}

function iconFor(type) {
  if (type === 'attachment') return '▧'
  if (type === 'book') return '▤'
  if (type === 'journalArticle') return '●'
  return '▥'
}

function itemTypeLabel(type) {
  const labels = {
    journalArticle: 'Journal Article',
    book: 'Book',
    bookSection: 'Book Section',
    conferencePaper: 'Conference Paper',
    report: 'Report',
    thesis: 'Thesis',
    webpage: 'Web Page',
    attachment: 'Attachment',
  }
  return labels[type] || type || '-'
}

function creatorTypeLabel(type) {
  const labels = {
    author: 'Author',
    editor: 'Editor',
    contributor: 'Contributor',
    translator: 'Translator',
  }
  return labels[type] || type || 'Creator'
}

function formatZoteroDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatSyncTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  const now = new Date()
  return date.toDateString() === now.toDateString() ? time : `${date.getMonth() + 1}/${date.getDate()} ${time}`
}

function naturalCompare(a = '', b = '') {
  return String(a).localeCompare(String(b), 'zh-Hans-CN', { numeric: true, sensitivity: 'base' })
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function readTreeWidth() {
  const value = Number(localStorage.getItem('zotero-tree-width') || 260)
  return Number.isFinite(value) ? clamp(value, 240, 600) : 260
}

onMounted(() => {
  loadLibrary()
})

onBeforeUnmount(() => {
  stopTreeResize()
  stopBackgroundRefresh()
  window.clearTimeout(searchTimer)
  pageRequestId += 1
})
</script>

<style scoped>
.zotero-desktop {
  height: 100%;
  display: grid;
  grid-template-columns: var(--tree-width, 260px) 6px minmax(0, 1fr) 340px;
  background: #f6f7f9;
  color: #1f2937;
  overflow: hidden;
}

.zotero-desktop.detail-collapsed {
  grid-template-columns: var(--tree-width, 260px) 6px minmax(0, 1fr) 40px;
}

.zotero-tree {
  background: #f1f3f6;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 8px 10px 0 6px;
}

.tree-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.tree-heading {
  display: flex;
  align-items: center;
  gap: 4px;
}

.zotero-resizer {
  position: relative;
  z-index: 4;
  cursor: col-resize;
  background: linear-gradient(90deg, #d8dde6 0, #d8dde6 1px, #eef2f7 1px, #eef2f7 100%);
  transition: background 0.15s ease;
}

.zotero-resizer::after {
  content: "";
  position: absolute;
  inset: 0 1px;
  border-radius: 999px;
}

.zotero-resizer:hover,
:global(.zotero-resizing) .zotero-resizer {
  background: linear-gradient(90deg, #93c5fd 0, #93c5fd 2px, #dbeafe 2px, #dbeafe 100%);
}

:global(.zotero-resizing) {
  cursor: col-resize;
  user-select: none;
}

.tree-root,
.collection-row {
  min-width: 0;
  width: 100%;
  height: 30px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  display: grid;
  grid-template-columns: 16px 18px minmax(0, 1fr) 44px;
  gap: 6px;
  align-items: center;
  color: #1f2937;
  text-align: left;
  font-size: 13px;
  white-space: nowrap;
}

.tree-root {
  flex: 1;
  width: auto;
  min-width: 0;
  margin-top: 2px;
  padding: 0 8px;
  grid-template-columns: 16px 18px minmax(0, 1fr);
  background: #eef4ff;
  cursor: pointer;
}

.tree-add-button {
  width: 30px;
  height: 30px;
  padding: 0;
  flex: 0 0 30px;
  color: #155bd4;
}

.tree-caret {
  width: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.collection-row.active {
  background: #dbeafe;
  color: #155bd4;
  font-weight: 700;
}

.tree-root.active {
  color: #155bd4;
  font-weight: 800;
}

.tree-root em,
.collection-row em {
  justify-self: end;
  width: 38px;
  color: #8a95a8;
  font-style: normal;
  font-size: 12px;
  text-align: right;
}

.tree-actions {
  padding: 8px 6px;
  flex: 0 0 auto;
}

.tree-action-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  gap: 8px;
  align-items: center;
}

.tree-action-row :deep(.el-button) {
  width: 100%;
  margin-left: 0;
}

.sync-button {
  font-weight: 700;
}

.more-button {
  padding: 0;
}

.sync-notice {
  display: grid;
  gap: 4px;
  margin: 4px 6px 8px;
  padding: 10px 12px;
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
}

.sync-notice strong {
  color: #1f2937;
  font-size: 13px;
}

.sync-notice p {
  margin: 0;
  overflow-wrap: anywhere;
}

.sync-notice a,
.sync-footer-details a {
  color: #155bd4;
  font-weight: 700;
  text-decoration: none;
}

.sync-notice.is-running {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.sync-notice.is-failed {
  border-color: #fecaca;
  background: #fff7f7;
}

.sync-notice.is-failed strong {
  color: #b42318;
}

.sync-footer {
  margin: 0 -10px 0 -6px;
  border-top: 1px solid #d8dde6;
  background: #f8fafc;
  flex: 0 0 auto;
}

.sync-footer-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  min-height: 38px;
  padding: 6px 12px;
  border: 0;
  background: transparent;
  color: #475569;
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.sync-footer-toggle:hover,
.sync-footer-toggle:focus-visible {
  background: #eaf2fc;
}

.sync-footer-label {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sync-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #94a3b8;
  flex: 0 0 7px;
}

.sync-footer.is-success .sync-dot { background: #16a34a; }
.sync-footer.is-running .sync-dot { background: #2563eb; }
.sync-footer.is-failed .sync-dot { background: #dc2626; }

.sync-footer-details {
  display: grid;
  gap: 4px;
  padding: 0 12px 12px 26px;
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
}

.sync-footer-details p {
  margin: 0;
  overflow-wrap: anywhere;
}

.sync-footer-details span {
  color: #64748b;
}

.full-width {
  width: 100%;
}

.collection-dialog :deep(.el-dialog__body) {
  padding-bottom: 8px;
}

.collection-list {
  min-width: 0;
}

.collection-row {
  cursor: pointer;
  padding: 0 8px 0 calc(8px + var(--depth) * 18px);
}

.collection-row:hover {
  background: #e7edf7;
}

.node-caret {
  width: 16px;
  color: #667085;
  text-align: center;
  font-size: 12px;
}

.node-caret.empty {
  pointer-events: none;
}

.library-mark,
.folder-mark {
  position: relative;
  display: inline-block;
  width: 15px;
  height: 11px;
  border: 1px solid #4b8df8;
  border-radius: 2px;
  background: linear-gradient(180deg, #eaf3ff, #cfe3ff);
  box-sizing: border-box;
}

.library-mark::before,
.folder-mark::before {
  content: "";
  position: absolute;
  left: 1px;
  top: -4px;
  width: 8px;
  height: 4px;
  border: 1px solid #4b8df8;
  border-bottom: 0;
  border-radius: 2px 2px 0 0;
  background: #eaf3ff;
  box-sizing: border-box;
}

.folder-mark.open {
  background: linear-gradient(180deg, #fff7bf, #ffe773);
  border-color: #e0a300;
}

.folder-mark.open::before {
  border-color: #e0a300;
  background: #fff7bf;
}

.muted-folder {
  opacity: 0.65;
}

.collection-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.zotero-table-pane {
  min-width: 0;
  overflow: hidden;
  background: #fff;
  display: flex;
  flex-direction: column;
}

.library-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
}

.library-filters :deep(.el-input) {
  width: min(300px, 100%);
}

.library-filters .filter-select {
  width: 124px;
}

.filter-count {
  margin-left: auto;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}

.page-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  color: #b42318;
  background: #fff4f2;
  font-size: 13px;
}

.library-table-wrap {
  flex: 1;
  min-height: 0;
}

.library-load-more {
  padding: 12px;
  color: #64748b;
  font-size: 12px;
  text-align: center;
}

.library-empty {
  padding: 24px 12px;
  color: #64748b;
}

.item-type-icon {
  display: inline-block;
  width: 18px;
  color: #2563eb;
}

.item-type-icon.large {
  width: 22px;
  font-size: 18px;
}

.zotero-table-pane :deep(.el-table) {
  --el-table-border-color: #e5e7eb;
  --el-table-header-bg-color: #ffffff;
  font-size: 13px;
}

.zotero-table-pane :deep(.el-table th) {
  font-weight: 500;
  color: #334155;
}

.zotero-detail {
  border-left: 1px solid #d8dde6;
  background: #fafafa;
  overflow: hidden;
  color: #334155;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.detail-header {
  min-height: 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 0 12px;
  border-bottom: 1px solid #d8dde6;
  background: #fff;
  font-size: 13px;
  font-weight: 700;
}

.detail-toggle {
  width: 28px;
  height: 28px;
  margin: 0;
  padding: 0;
  flex: 0 0 28px;
}

.detail-collapsed .detail-header {
  justify-content: center;
  padding: 0;
}

.detail-tabs {
  height: 36px;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 0 12px;
  border-bottom: 1px solid #d8dde6;
  background: #fff;
}

.detail-tabs button {
  height: 32px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #475569;
  font-size: 13px;
  cursor: default;
}

.detail-tabs button.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
  font-weight: 700;
}

.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 12px 24px;
}

.detail-section {
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid #e5e7eb;
}

.detail-section:last-child {
  border-bottom: 0;
}

.item-type-row {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.field-label {
  display: block;
  color: #94a3b8;
  font-size: 12px;
}

.item-type-row strong {
  display: block;
  color: #334155;
  font-size: 13px;
}

.detail-section h3 {
  margin: 0;
  color: #102033;
  font-size: 15px;
  line-height: 1.45;
}

.detail-section h4 {
  margin: 0 0 10px;
  color: #102033;
  font-size: 13px;
}

.info-list {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr);
  gap: 7px 10px;
  margin: 0;
  font-size: 12px;
}

.info-list.compact {
  grid-template-columns: 76px minmax(0, 1fr);
}

.info-list dt {
  color: #94a3b8;
  text-align: right;
}

.info-list dd {
  margin: 0;
  min-width: 0;
  color: #334155;
  word-break: break-word;
}

.info-list a {
  color: #2563eb;
  text-decoration: none;
}

.info-list a:hover {
  text-decoration: underline;
}

.abstract-text {
  margin: 0;
  color: #334155;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-list span {
  padding: 3px 8px;
  border-radius: 999px;
  background: #eaf3ff;
  color: #2563eb;
  font-size: 12px;
}

.detail-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 18px;
  color: #b4b8c0;
  text-align: center;
}

.detail-count {
  font-size: 28px;
}

.detail-empty p {
  margin: 4px 0 18px;
}

.detail-empty span {
  color: #94a3b8;
  font-size: 13px;
}

@media (max-width: 1440px) {
  .zotero-desktop {
    grid-template-columns: minmax(240px, var(--tree-width, 260px)) 6px minmax(0, 1fr) 280px;
  }

  .zotero-desktop.detail-collapsed {
    grid-template-columns: minmax(240px, var(--tree-width, 260px)) 6px minmax(0, 1fr) 40px;
  }
}

@media (max-width: 1180px) {
  .zotero-desktop {
    grid-template-columns: clamp(230px, var(--tree-width, 260px), 280px) 6px minmax(0, 1fr);
  }

  .zotero-desktop.detail-collapsed {
    grid-template-columns: clamp(230px, var(--tree-width, 260px), 280px) 6px minmax(0, 1fr);
  }

  .zotero-detail {
    display: none;
  }
}

@media (max-width: 900px) {
  .zotero-desktop,
  .zotero-desktop.detail-collapsed {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .zotero-resizer {
    display: none;
  }

  .zotero-tree {
    max-height: 320px;
  }

  .zotero-table-pane {
    min-height: 520px;
  }
}
</style>
