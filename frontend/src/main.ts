import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'
import Overview from './views/Overview.vue'
import Tasks from './views/Tasks.vue'
import Findings from './views/Findings.vue'
import Verification from './views/Verification.vue'
import ChannelsRules from './views/ChannelsRules.vue'
import Settings from './views/Settings.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: Overview, meta: { title: '总览' } },
    { path: '/tasks', component: Tasks, meta: { title: '监控任务' } },
    { path: '/findings', component: Findings, meta: { title: '发现列表' } },
    { path: '/verification', component: Verification, meta: { title: '验证中心' } },
    { path: '/channels', component: ChannelsRules, meta: { title: '渠道与规则' } },
    { path: '/settings', component: Settings, meta: { title: '设置' } },
  ],
})

createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
