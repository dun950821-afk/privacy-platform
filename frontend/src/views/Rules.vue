<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar"><span class="page-title">规则管理</span></div>
      <el-table :data="rules" v-loading="loading" stripe>
        <el-table-column prop="rule_key" label="编号" width="180" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="category" label="分类" width="100" />
        <el-table-column prop="status" label="状态" width="80" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="$router.push(`/rules/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ruleApi } from '@/api/rules'
const loading = ref(false)
const rules = ref<any[]>([])
onMounted(async () => {
  loading.value = true
  try { const res: any = await ruleApi.list(); rules.value = res.data } finally { loading.value = false }
})
</script>
<style scoped>
.header-bar { margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
</style>
