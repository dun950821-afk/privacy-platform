<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo-area">
        <el-icon :size="22" color="#2B5AED"><Lock /></el-icon>
        <span v-if="!collapsed" class="logo-text">隐私合规平台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        class="side-menu"
        background-color="transparent"
        text-color="#646A73"
        active-text-color="#2B5AED"
      >
        <el-menu-item index="/workspace">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>检测工作台</template>
        </el-menu-item>
        <el-menu-item index="/findings">
          <el-icon><Warning /></el-icon>
          <template #title>问题管理</template>
        </el-menu-item>
        <el-menu-item index="/sdks">
          <el-icon><Box /></el-icon>
          <template #title>SDK知识库</template>
        </el-menu-item>
        <el-menu-item index="/engines">
          <el-icon><Cpu /></el-icon>
          <template #title>检测引擎</template>
        </el-menu-item>
        <el-menu-item index="/rules">
          <el-icon><Document /></el-icon>
          <template #title>规则管理</template>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <template #title>报告中心</template>
        </el-menu-item>

        <el-sub-menu v-if="isAdmin" index="system">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/system/users">用户管理</el-menu-item>
          <el-menu-item index="/system/nodes">节点设备</el-menu-item>
          <el-menu-item index="/system/audit">审计日志</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="topbar">
        <div class="topbar-left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <Fold v-if="!collapsed" />
            <Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/workspace' }">检测工作台</el-breadcrumb-item>
            <el-breadcrumb-item v-if="crumbProject">{{ crumbProject }}</el-breadcrumb-item>
            <el-breadcrumb-item v-if="crumbApp">{{ crumbApp }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="topbar-right">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="28" style="background:#2B5AED">
                {{ userStore.user?.username?.charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="username">{{ userStore.user?.full_name || userStore.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人信息</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
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
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import {
  DataAnalysis, Folder, Cellphone, List, Warning, Box,
  Document, Setting, Fold, Expand, ArrowDown, Lock, Cpu
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const collapsed = ref(false)

const activeMenu = computed(() => {
  const path = '/' + (route.path.split('/')[1] || 'workspace')
  return path
})
const isAdmin = computed(() => userStore.user?.role === 'platform_admin')

const crumbProject = computed(() => route.meta.crumbProject as string || '')
const crumbApp = computed(() => route.meta.crumbApp as string || '')

function handleCommand(cmd: string) {
  if (cmd === 'logout') {
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
}
.logo-area {
  display: flex; align-items: center; gap: 8px;
  height: 56px; padding: 0 20px;
  border-bottom: 1px solid #E8EAEC;
}
.logo-text { font-size: 15px; font-weight: 600; color: #1F2329; white-space: nowrap; }
.side-menu { border-right: none; padding: 8px 0; }
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  background: #fff; border-bottom: 1px solid #E8EAEC;
  height: 56px; padding: 0 20px;
}
.topbar-left { display: flex; align-items: center; gap: 16px; }
.collapse-btn { font-size: 18px; cursor: pointer; color: #646A73; }
.topbar-right { display: flex; align-items: center; }
.user-info { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.username { font-size: 14px; color: #1F2329; }
.main-content { background: #F7F8FA; padding: 0; overflow-y: auto; }
</style>
