import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import './styles.css'
import './styles/theme.css'
import './styles/dashboard.css'
import './styles/animations.css'
import './views/admin/admin-shared.css'

createApp(App).use(router).use(ElementPlus).mount('#app')
