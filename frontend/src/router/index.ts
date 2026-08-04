import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    children: [
      // 总览
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'),
        meta: { title: '综合看板', group: '总览' } },
      // 检测工作
      { path: 'workspace', name: 'Workspace', component: () => import('@/views/Workspace.vue'),
        meta: { title: '检测工作台', group: '检测工作' } },
      { path: 'queue', name: 'Queue', component: () => import('@/views/Queue.vue'),
        meta: { title: '检测队列', group: '检测工作' } },
      { path: 'workspace/project/:pid', name: 'ProjectWorkspace', component: () => import('@/views/Workspace.vue'),
        meta: { title: '检测工作台', group: '检测工作' } },
      { path: 'workspace/project/:pid/app/:aid', name: 'AppWorkspace', component: () => import('@/views/Workspace.vue'),
        meta: { title: '检测工作台', group: '检测工作' } },
      { path: 'tasks/:id', name: 'TaskDetail', component: () => import('@/views/TaskDetail.vue'),
        meta: { title: '任务详情', group: '检测工作' } },
      { path: 'tasks/:id/report', name: 'TaskReport', component: () => import('@/views/TaskReport.vue'),
        meta: { title: '检测报告', group: '检测工作' } },
      { path: 'findings', name: 'Findings', component: () => import('@/views/Findings.vue'),
        meta: { title: '问题管理', group: '检测工作' } },
      { path: 'findings/:id', name: 'FindingDetail', component: () => import('@/views/FindingDetail.vue'),
        meta: { title: '问题详情', group: '检测工作' } },
      // 知识库
      { path: 'sdks', name: 'SDKs', component: () => import('@/views/SDKs.vue'),
        meta: { title: 'SDK知识库', group: '知识库' } },
      { path: 'sdks/:id', name: 'SDKDetail', component: () => import('@/views/SDKDetail.vue'),
        meta: { title: '组件详情', group: '知识库' } },
      { path: 'engines', name: 'Engines', component: () => import('@/views/Engines.vue'),
        meta: { title: '检测引擎', group: '知识库' } },
      { path: 'appshark-rules', name: 'AppsharkRules', component: () => import('@/views/AppsharkRules.vue'),
        meta: { title: 'AppShark规则', group: '知识库' } },
      { path: 'rules', name: 'Rules', component: () => import('@/views/Rules.vue'),
        meta: { title: '规则管理', group: '知识库' } },
      { path: 'rules/:id', name: 'RuleDetail', component: () => import('@/views/RuleDetail.vue'),
        meta: { title: '规则详情', group: '知识库' } },
      // 报告
      { path: 'reports', name: 'Reports', component: () => import('@/views/Reports.vue'),
        meta: { title: '报告中心', group: '报告' } },
      // 系统管理
      { path: 'system/users', name: 'SystemUsers', component: () => import('@/views/SystemUsers.vue'),
        meta: { title: '用户管理', group: '系统管理' } },
      { path: 'system/nodes', name: 'SystemNodes', component: () => import('@/views/SystemNodes.vue'),
        meta: { title: '节点设备', group: '系统管理' } },
      { path: 'system/audit', name: 'SystemAudit', component: () => import('@/views/SystemAudit.vue'),
        meta: { title: '审计日志', group: '系统管理' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  if (to.meta.public || userStore.token) {
    next()
  } else {
    next('/login')
  }
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} - App个人信息保护检测与治理平台`
    : 'App个人信息保护检测与治理平台'
})

export default router
