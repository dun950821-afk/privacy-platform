<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar">
        <span class="page-title">{{ rule.name }}</span>
        <el-button @click="$router.back()">返回</el-button>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="编号">{{ rule.rule_key }}</el-descriptions-item>
        <el-descriptions-item label="分类">{{ rule.category }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ rule.status }}</el-descriptions-item>
        <el-descriptions-item label="描述">{{ rule.description }}</el-descriptions-item>
      </el-descriptions>
      <h3 style="margin-top:20px">版本历史</h3>
      <el-table :data="rule.versions || []" size="small">
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column prop="changelog" label="变更说明" />
        <el-table-column prop="published_at" label="发布时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ruleApi } from '@/api/rules'
const route = useRoute()
const rule = ref<any>({})
onMounted(async () => {
  const res: any = await ruleApi.get(Number(route.params.id))
  rule.value = res.data
})
</script>
<style scoped>
.header-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
</style>
