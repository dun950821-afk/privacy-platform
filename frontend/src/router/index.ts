import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/workspace',
    children: [
      // 检测主线：工作台（项目→App→任务一体化）
      { path: 'workspace', name: 'Workspace', component: () => import('@/views/Workspace.vue') },
      { path: 'workspace/project/:pid', name: 'ProjectWorkspace', component: () => import('@/views/Workspace.vue') },
      { path: 'workspace/project/:pid/app/:aid', name: 'AppWorkspace', component: () => import('@/views/Workspace.vue') },
      // 任务详情（独立全页）
      { path: 'tasks/:id', name: 'TaskDetail', component: () => import('@/views/TaskDetail.vue') },
      // 问题管理
      { path: 'findings', name: 'Findings', component: () => import('@/views/Findings.vue') },
      { path: 'findings/:id', name: 'FindingDetail', component: () => import('@/views/FindingDetail.vue') },
      // 知识库
      { path: 'sdks', name: 'SDKs', component: () => import('@/views/SDKs.vue') },
      { path: 'sdks/:id', name: 'SDKDetail', component: () => import('@/views/SDKDetail.vue') },
      { path: 'engines', name: 'Engines', component: () => import('@/views/Engines.vue') },
      { path: 'rules', name: 'Rules', component: () => import('@/views/Rules.vue') },
      { path: 'rules/:id', name: 'RuleDetail', component: () => import('@/views/RuleDetail.vue') },
      // 报告
      { path: 'reports', name: 'Reports', component: () => import('@/views/Reports.vue') },
      // 系统管理
      { path: 'system/users', name: 'SystemUsers', component: () => import('@/views/SystemUsers.vue') },
      { path: 'system/nodes', name: 'SystemNodes', component: () => import('@/views/SystemNodes.vue') },
      { path: 'system/audit', name: 'SystemAudit', component: () => import('@/views/SystemAudit.vue') },
    ]
  }
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

export default router
