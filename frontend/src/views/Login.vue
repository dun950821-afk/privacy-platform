<template>
  <div class="login-page">
    <!-- 左侧品牌区 -->
    <div class="brand-pane">
      <div class="brand-inner">
        <div class="brand-logo">
          <el-icon :size="30"><Lock /></el-icon>
          <span class="brand-name">App个人信息保护检测与治理平台</span>
        </div>
        <h1 class="brand-slogan">一站式 App 隐私合规<br>检测、分析与治理</h1>
        <p class="brand-desc">覆盖静态扫描与动态行为分析，构建可审计的隐私合规证据链。</p>
        <ul class="brand-features">
          <li>
            <el-icon :size="16"><Cpu /></el-icon>
            <span>静态 + 动态双引擎检测</span>
          </li>
          <li>
            <el-icon :size="16"><Connection /></el-icon>
            <span>统一事件与证据链管理</span>
          </li>
          <li>
            <el-icon :size="16"><DocumentChecked /></el-icon>
            <span>规则化合规判定与报告</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- 右侧表单区 -->
    <div class="form-pane">
      <div class="login-card">
        <div class="login-header">
          <div class="login-logo">
            <el-icon :size="28" color="#2B5AED"><Lock /></el-icon>
          </div>
          <h2 class="login-title">欢迎登录</h2>
          <p class="login-sub">App个人信息保护检测与治理平台</p>
        </div>
        <el-form ref="formRef" :model="form" :rules="rules" size="large"
                 @submit.prevent="handleLogin">
          <el-form-item prop="username">
            <el-input v-model="form.username" placeholder="用户名" :prefix-icon="User" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码"
                      :prefix-icon="Lock" show-password @keyup.enter="handleLogin" />
          </el-form-item>
          <el-form-item class="login-btn-item">
            <el-button type="primary" class="login-btn" :loading="loading"
                       native-type="submit" @click="handleLogin">登 录</el-button>
          </el-form-item>
        </el-form>
        <p class="login-foot">隐私合规 · 智能治理 · 证据闭环</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock, Cpu, Connection, DocumentChecked } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { authApi } from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({ username: '', password: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value || loading.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const res: any = await authApi.login(form.username, form.password)
    const d = res.data
    userStore.setAuth(d.access_token, d.refresh_token, d.user)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch {
    // 错误已由拦截器统一提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  background: #fff;
}

/* 左侧品牌区 */
.brand-pane {
  flex: 1.1;
  display: flex;
  align-items: center;
  background: linear-gradient(150deg, #1F47C4 0%, #2B5AED 100%);
  color: #fff;
  padding: 48px 64px;
}
.brand-inner {
  max-width: 520px;
}
.brand-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 56px;
}
.brand-name {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}
.brand-slogan {
  font-size: 34px;
  font-weight: 700;
  line-height: 1.4;
  margin-bottom: 16px;
}
.brand-desc {
  font-size: 14px;
  line-height: 1.8;
  color: rgba(255, 255, 255, 0.75);
  margin-bottom: 40px;
}
.brand-features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.brand-features li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.9);
}
.brand-features .el-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.14);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 右侧表单区 */
.form-pane {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  padding: 48px 32px;
}
.login-card {
  width: 360px;
}
.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.login-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  background: #EEF3FE;
  border-radius: 14px;
  margin-bottom: 16px;
}
.login-title {
  font-size: 22px;
  font-weight: 700;
  color: #1F2329;
  margin-bottom: 6px;
}
.login-sub {
  font-size: 13px;
  color: #8F959E;
}
.login-btn-item {
  margin-top: 8px;
}
.login-btn {
  width: 100%;
  letter-spacing: 4px;
}
.login-foot {
  text-align: center;
  font-size: 12px;
  color: #C0C4CC;
  margin-top: 24px;
}

@media (max-width: 860px) {
  .brand-pane {
    display: none;
  }
}
</style>
