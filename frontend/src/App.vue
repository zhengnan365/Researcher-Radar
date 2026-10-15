<template>
  <router-view v-if="$route.meta.public" />
  <el-container v-else class="app-shell">
    <el-aside width="230px" class="side-nav" :class="{ 'is-collapsed': sidebarCollapsed }">
      <el-menu router :default-active="$route.path" :collapse="sidebarCollapsed" :collapse-transition="false" class="side-menu">
        <el-menu-item index="/">
          <el-icon><HomeFilled /></el-icon>
          <template #title>文献日报</template>
        </el-menu-item>
        <el-menu-item index="/papers">
          <el-icon><Document /></el-icon>
          <template #title>文献列表</template>
        </el-menu-item>
        <el-menu-item index="/zotero/library">
          <el-icon><Collection /></el-icon>
          <template #title>Zotero 文献库</template>
        </el-menu-item>
        <el-sub-menu index="/admin">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/admin/sources">RSS 源管理</el-menu-item>
          <el-menu-item index="/admin/directions">研究方向管理</el-menu-item>
          <el-menu-item index="/admin/keywords">关键词管理</el-menu-item>
          <el-menu-item index="/admin/scoring">推荐评分规则</el-menu-item>
          <el-menu-item index="/admin/low-score">低分条目管理</el-menu-item>
          <el-menu-item index="/admin/fetch_logs">抓取日志</el-menu-item>
          <el-menu-item index="/admin/zotero">AI 与 Zotero 设置</el-menu-item>
          <el-menu-item index="/admin/config-transfer">配置导入导出</el-menu-item>
          <el-menu-item index="/admin/users">用户管理</el-menu-item>
          <el-menu-item index="django-admin" :route="{ path: $route.path }" @click="openAdmin">管理员入口</el-menu-item>
        </el-sub-menu>
      </el-menu>

      <div class="external-tools">
        <div v-if="!sidebarCollapsed" class="external-tools-title">外部工具</div>
        <button class="external-tool-button" type="button" title="打开 Zotero" aria-label="打开 Zotero" @click="openLocalZotero">
          <span v-if="!sidebarCollapsed">打开 Zotero</span>
          <el-icon><TopRight /></el-icon>
        </button>
      </div>
    </el-aside>

    <el-container class="main-shell" :class="{ 'is-header-hidden': headerHidden }">
      <el-header class="top-bar">
        <button
          class="sidebar-toggle"
          type="button"
          :title="sidebarCollapsed ? '展开左侧菜单' : '折叠左侧菜单'"
          :aria-label="sidebarCollapsed ? '展开左侧菜单' : '折叠左侧菜单'"
          :aria-expanded="!sidebarCollapsed"
          @click="toggleSidebar"
        >
          <el-icon><Expand v-if="sidebarCollapsed" /><Fold v-else /></el-icon>
        </button>
        <router-link class="top-brand" to="/" aria-label="科研雷达 ResearcherRadar">
          <span>科研雷达</span><small>ResearcherRadar</small>
        </router-link>
        <el-dropdown class="account-menu" trigger="click" @command="handleTopMenuCommand">
          <button class="account-trigger" type="button" :aria-label="`账户菜单，当前用户 ${authState.user?.username || '用户'}`">
            <el-icon><UserFilled /></el-icon>
            <span class="account-name">{{ authState.user?.username || '用户' }}</span>
            <el-icon class="account-chevron"><ArrowDown /></el-icon>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="content-main" @scroll.capture="handleContentScroll" @wheel.capture="handleContentWheel">
        <router-view v-slot="{ Component }">
          <keep-alive :max="16">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ArrowDown, Collection, Document, Expand, Fold, HomeFilled, Setting, TopRight, UserFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authState, logout } from './stores/auth'

const router = useRouter()
const route = useRoute()
const sidebarCollapsed = ref(readSidebarCollapsed())
const headerHidden = ref(false)
let activeScrollContainer = null
const headerHideScrollThreshold = 12
const headerRevealScrollThreshold = 4

function handleContentScroll(event) {
  const target = event.target
  if (!(target instanceof HTMLElement) || target.scrollHeight <= target.clientHeight + 2) return
  if (target.scrollTop > headerHideScrollThreshold) {
    activeScrollContainer = target
    headerHidden.value = true
  } else if (target.scrollTop <= headerRevealScrollThreshold && (!activeScrollContainer || activeScrollContainer === target)) {
    activeScrollContainer = null
    headerHidden.value = false
  }
}

function handleContentWheel(event) {
  if (headerHidden.value && event.deltaY < 0 && activeScrollContainer?.scrollTop <= headerRevealScrollThreshold) {
    activeScrollContainer = null
    headerHidden.value = false
  }
}

watch(() => route.path, () => {
  activeScrollContainer = null
  headerHidden.value = false
})

function readSidebarCollapsed() {
  try {
    return window.localStorage.getItem('literature-sidebar-collapsed') === 'true'
  } catch {
    return false
  }
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  try {
    window.localStorage.setItem('literature-sidebar-collapsed', String(sidebarCollapsed.value))
  } catch {
    // The menu remains usable when browser storage is unavailable.
  }
}

function openAdmin() {
  window.open(import.meta.env.VITE_ADMIN_URL || 'http://localhost:8000/admin/', '_blank', 'noopener,noreferrer')
}

function openLocalZotero() {
  const startedAt = Date.now()
  window.location.href = 'zotero://'
  window.setTimeout(() => {
    if (document.hasFocus() && Date.now() - startedAt > 900) {
      ElMessage.warning('未检测到 Zotero 客户端，请确认已安装 Zotero 或已启用本地协议。')
    }
  }, 1200)
}

async function handleTopMenuCommand(command) {
  if (command === 'logout') {
    await handleLogout()
  }
}

async function handleLogout() {
  await logout()
  router.replace('/login')
}

</script>

<style scoped>
.app-shell {
  height: 100vh;
  overflow: hidden;
  background: transparent;
}

.side-nav {
  height: 100vh;
  overflow: hidden;
  background: #0f172a;
  box-shadow: 8px 0 28px rgba(15, 23, 42, 0.1);
  display: flex;
  flex-direction: column;
}

.side-nav.is-collapsed {
  width: 64px !important;
}

.sidebar-toggle {
  width: 40px;
  height: 40px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 12px;
  color: #1769d8;
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  flex-shrink: 0;
}

.sidebar-toggle:hover,
.sidebar-toggle:focus-visible {
  background: #edf7ff;
  outline: 2px solid rgba(47, 140, 255, 0.4);
  outline-offset: 2px;
}

.side-menu {
  border-right: 0;
  background: #fff;
  flex: 1;
  min-height: 0;
  padding: 10px 0;
  overflow-y: auto;
}

.side-menu :deep(.el-menu-item),
.side-menu :deep(.el-sub-menu__title) {
  height: 54px;
  padding-left: 20px !important;
  font-size: 16px;
  color: #111827;
}

.side-menu :deep(.el-menu-item .el-icon),
.side-menu :deep(.el-sub-menu__title .el-icon) {
  font-size: 18px;
  margin-right: 12px;
}

.side-nav.is-collapsed .side-menu :deep(.el-menu-item),
.side-nav.is-collapsed .side-menu :deep(.el-sub-menu__title) {
  padding-left: 0 !important;
  padding-right: 0 !important;
  justify-content: center;
}

.side-nav.is-collapsed .side-menu :deep(.el-menu-item .el-icon),
.side-nav.is-collapsed .side-menu :deep(.el-sub-menu__title .el-icon) {
  margin-right: 0;
}

.side-menu :deep(.el-sub-menu .el-menu-item) {
  height: 48px;
  padding-left: 42px !important;
  color: #475569;
  font-size: 15px;
  background: #f8fbff;
  position: relative;
}

.side-menu :deep(.el-sub-menu .el-menu-item::before) {
  content: "";
  position: absolute;
  left: 26px;
  top: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #cbd5e1;
  transform: translateY(-50%);
}

.side-menu :deep(.el-sub-menu .el-menu-item:hover) {
  color: #1d4ed8;
  background: #eef6ff;
}

.side-menu :deep(.el-menu-item.is-active) {
  color: #2f8cff;
  font-weight: 800;
  background: linear-gradient(90deg, rgba(47, 140, 255, 0.1), rgba(37, 214, 200, 0.04));
  border-left: 4px solid #2f8cff;
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  color: #1d4ed8;
  background: #eaf4ff;
  border-left: 0;
}

.side-menu :deep(.el-sub-menu .el-menu-item.is-active::before) {
  background: #2f8cff;
}

.external-tools {
  padding: 14px 14px 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
  background: #f8fbff;
}

.external-tools-title {
  margin: 0 0 9px 2px;
  color: #64748b;
  font-size: 13px;
  font-weight: 800;
}

.external-tool-button {
  width: 100%;
  height: 38px;
  border: 1px solid rgba(47, 140, 255, 0.24);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.86);
  color: #1769d8;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.external-tool-button:hover {
  color: #0f58bd;
  border-color: rgba(47, 140, 255, 0.42);
  background: #edf7ff;
  box-shadow: 0 8px 18px rgba(47, 140, 255, 0.1);
}

.side-nav.is-collapsed .external-tools {
  padding: 12px;
}

.side-nav.is-collapsed .external-tool-button {
  width: 40px;
  height: 40px;
}

.main-shell {
  min-width: 0;
  height: 100vh;
  overflow: hidden;
}

.top-bar {
  height: 58px;
  padding: 0 28px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(14px);
  display: grid;
  grid-template-columns: minmax(40px, 1fr) auto minmax(40px, 1fr);
  align-items: center;
  gap: 18px;
  flex-shrink: 0;
  overflow: hidden;
  transition: height 0.2s ease, opacity 0.2s ease, border-color 0.2s ease;
}

.main-shell.is-header-hidden .top-bar {
  height: 0;
  border-bottom-color: transparent;
  opacity: 0;
  pointer-events: none;
}

.top-brand {
  display: inline-flex;
  align-items: baseline;
  gap: 9px;
  color: #10243d;
  font-size: 20px;
  font-weight: 900;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
}

.top-brand small {
  color: #60758c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.account-menu {
  justify-self: end;
}

.account-trigger {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 11px;
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  color: #475569;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.account-trigger:hover,
.account-trigger:focus-visible {
  border-color: rgba(47, 140, 255, 0.5);
  color: #1769d8;
  background: #edf7ff;
  outline: 2px solid rgba(47, 140, 255, 0.2);
  outline-offset: 2px;
}

.account-chevron {
  font-size: 11px;
}

.content-main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 0;
}

@media (max-width: 1100px) {
  .side-nav {
    width: 190px !important;
  }
}

@media (max-width: 1440px) {
  .side-nav {
    width: 205px !important;
  }

  .side-menu :deep(.el-menu-item),
  .side-menu :deep(.el-sub-menu__title) {
    height: 48px;
    font-size: 15px;
  }

  .side-menu :deep(.el-sub-menu .el-menu-item) {
    height: 42px;
    padding-left: 36px !important;
    font-size: 14px;
  }

  .top-bar {
    height: 52px;
    padding: 0 20px;
  }

  .top-brand {
    font-size: 18px;
  }

}

@media (max-width: 1180px) {
  .side-nav {
    width: 184px !important;
  }

}

@media (max-width: 700px) {
  .top-brand small {
    display: none;
  }

  .account-name,
  .account-chevron {
    display: none;
  }

  .top-bar {
    grid-template-columns: minmax(40px, 1fr) auto minmax(40px, 1fr);
    gap: 8px;
    padding: 0 12px;
  }

  .account-trigger {
    width: 40px;
    padding: 0;
    justify-content: center;
  }
}
</style>
