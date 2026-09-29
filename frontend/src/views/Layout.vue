<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo-area" @click="$router.push('/dashboard')">
        <div class="logo-mark">
          <el-icon :size="18" color="#fff"><Lock /></el-icon>
        </div>
        <div v-if="!collapsed" class="logo-text">
          <div class="logo-name">隐私合规平台</div>
          <div class="logo-sub">Privacy Platform</div>
        </div>
      </div>
      <el-scrollbar class="menu-scrollbar">
        <el-menu
          :default-active="activeMenu"
          :collapse="collapsed"
          :collapse-transition="true"
          router
          class="side-menu"
          background-color="transparent"
          text-color="#646A73"
          active-text-color="#2B5AED"
        >
          <template v-for="group in visibleMenus" :key="group.label">
            <div v-if="!collapsed" class="menu-group-label">{{ group.label }}</div>
            <el-menu-item v-for="item in group.items" :key="item.path" :index="item.path">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title>{{ item.title }}</template>
            </el-menu-item>
          </template>
        </el-menu>
      </el-scrollbar>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="topbar">
        <div class="topbar-left">
          <el-tooltip :content="collapsed ? '展开菜单' : '收起菜单'" placement="bottom">
            <el-icon class="collapse-btn" @click="collapsed = !collapsed">
              <Fold v-if="!collapsed" />
              <Expand v-else />
            </el-icon>
          </el-tooltip>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item v-if="route.meta.group">{{ route.meta.group }}</el-breadcrumb-item>
            <el-breadcrumb-item>{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="topbar-right">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="30" class="user-avatar">
                {{ avatarText }}
              </el-avatar>
              <span class="username">{{ userStore.user?.full_name || userStore.user?.username }}</span>
              <el-icon class="arrow"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>个人信息
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 主内容 -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <!-- 个人信息 -->
  <el-dialog v-model="showProfile" title="个人信息" width="440px">
    <el-descriptions :column="1" border>
      <el-descriptions-item label="用户名">{{ userStore.user?.username }}</el-descriptions-item>
      <el-descriptions-item label="姓名">{{ userStore.user?.full_name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="角色">
        <StatusTag :value="userStore.user?.role" :map="USER_ROLE" />
      </el-descriptions-item>
      <el-descriptions-item label="邮箱">{{ userStore.user?.email || '-' }}</el-descriptions-item>
    </el-descriptions>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api/auth'
import StatusTag from '@/components/StatusTag.vue'
import { USER_ROLE } from '@/utils/dict'
import {
  DataAnalysis, Monitor, Warning, Box, Cpu, Document, Files,
  Setting, Fold, Expand, ArrowDown, Lock, User, SwitchButton, Stopwatch, MagicStick,
  Connection, Key,
} from '@element-plus/icons-vue'

interface MenuItem { path: string; title: string; icon: any }
interface MenuGroup { label: string; items: MenuItem[]; adminOnly?: boolean }

const MENUS: MenuGroup[] = [
  { label: '总览', items: [
    { path: '/dashboard', title: '综合看板', icon: Monitor },
  ] },
  { label: '检测工作', items: [
    { path: '/workspace', title: '检测工作台', icon: DataAnalysis },
    { path: '/queue', title: '检测队列', icon: Stopwatch },
    { path: '/findings', title: '问题管理', icon: Warning },
  ] },
  { label: '知识库', items: [
    { path: '/sdks', title: 'SDK知识库', icon: Box },
    { path: '/permissions', title: '权限知识库', icon: Key },
    // 这页不执行检测：它的 10 条判定规则用的是 `when` 那套 DSL，关联器只加载
    // category=correlation 的规则，求值器也不认这套 schema。叫「规则管理」会让人
    // 以为改这里能改检测行为，所以按它实际的角色命名——登记与版本台账。
    { path: '/rules', title: '判定规则库', icon: Document },
    { path: '/correlation-rules', title: '关联规则', icon: Connection },
    { path: '/engines', title: '检测引擎', icon: Cpu },
    { path: '/appshark-rules', title: '静态规则', icon: MagicStick },
  ] },
  { label: '报告', items: [
    { path: '/reports', title: '报告中心', icon: Files },
  ] },
  { label: '系统管理', adminOnly: true, items: [
    { path: '/system/users', title: '用户管理', icon: User },
    { path: '/system/nodes', title: '节点设备', icon: Cpu },
    { path: '/system/audit', title: '审计日志', icon: Setting },
  ] },
]

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const collapsed = ref(false)
const showProfile = ref(false)

const isAdmin = computed(() => userStore.user?.role === 'platform_admin')
const visibleMenus = computed(() => MENUS.filter(g => !g.adminOnly || isAdmin.value))

const activeMenu = computed(() => {
  const seg = '/' + (route.path.split('/')[1] || 'dashboard')
  // /tasks/:id 高亮工作台
  return seg === '/tasks' ? '/workspace' : seg
})

const avatarText = computed(() =>
  (userStore.user?.full_name || userStore.user?.username || '?').charAt(0).toUpperCase()
)

function handleCommand(cmd: string) {
  if (cmd === 'profile') {
    showProfile.value = true
  } else if (cmd === 'logout') {
    authApi.logout().catch(() => {})
    userStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout-container { height: 100vh; }
.sidebar {
  background: #fff;
  border-right: 1px solid #E8EAEC;
  transition: width 0.2s;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid #E8EAEC;
  cursor: pointer;
  flex-shrink: 0;
}
.logo-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2B5AED, #1F47C4);
  flex-shrink: 0;
}
.logo-name { font-size: 15px; font-weight: 600; color: #1F2329; white-space: nowrap; line-height: 20px; }
.logo-sub { font-size: 11px; color: #8F959E; white-space: nowrap; line-height: 14px; }
.menu-scrollbar { flex: 1; }
.side-menu { border-right: none; padding: 8px; }
.side-menu :deep(.el-menu-item) {
  height: 40px;
  line-height: 40px;
  border-radius: 6px;
  margin-bottom: 2px;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: #EEF3FE;
  font-weight: 500;
}
.menu-group-label {
  padding: 14px 12px 6px;
  font-size: 12px;
  color: #8F959E;
  white-space: nowrap;
}
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #E8EAEC;
  height: 56px; padding: 0 20px;
}
.topbar-left { display: flex; align-items: center; gap: 16px; }
.collapse-btn { font-size: 18px; cursor: pointer; color: #646A73; }
.collapse-btn:hover { color: #2B5AED; }
.topbar-right { display: flex; align-items: center; }
.user-info { display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 4px 6px; border-radius: 6px; }
.user-info:hover { background: #F0F1F3; }
.user-avatar { background: #2B5AED; font-size: 13px; }
.username { font-size: 14px; color: #1F2329; }
.arrow { font-size: 12px; color: #8F959E; }
.main-content { background: #F7F8FA; padding: 0; overflow-y: auto; }
</style>
