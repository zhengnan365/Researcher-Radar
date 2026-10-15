import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import PaperListView from '../views/PaperListView.vue'
import ZoteroLibraryView from '../views/ZoteroLibraryView.vue'
import ZoteroView from '../views/ZoteroView.vue'
import SourceAdminView from '../views/admin/SourceAdminView.vue'
import KeywordAdminView from '../views/admin/KeywordAdminView.vue'
import DirectionAdminView from '../views/admin/DirectionAdminView.vue'
import FetchLogView from '../views/admin/FetchLogView.vue'
import LowScoreAdminView from '../views/admin/LowScoreAdminView.vue'
import ScoringSettingsView from '../views/admin/ScoringSettingsView.vue'
import UserAdminView from '../views/admin/UserAdminView.vue'
import ConfigTransferView from '../views/admin/ConfigTransferView.vue'
import { ensureAuth } from '../stores/auth'

const routes = [
  { path: '/login', component: LoginView, meta: { public: true } },
  { path: '/', component: HomeView },
  { path: '/papers', component: PaperListView },
  { path: '/zotero/library', component: ZoteroLibraryView },
  { path: '/admin/zotero', component: ZoteroView },
  { path: '/admin/sources', component: SourceAdminView },
  { path: '/admin/keywords', component: KeywordAdminView },
  { path: '/admin/directions', component: DirectionAdminView },
  { path: '/admin/low-score', component: LowScoreAdminView },
  { path: '/admin/scoring', component: ScoringSettingsView },
  { path: '/admin/ai', redirect: '/admin/zotero' },
  { path: '/admin/fetch_logs', component: FetchLogView },
  { path: '/admin/users', component: UserAdminView },
  { path: '/admin/config-transfer', component: ConfigTransferView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const isLoggedIn = await ensureAuth()
  if (to.meta.public) {
    return isLoggedIn ? '/' : true
  }
  if (!isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
