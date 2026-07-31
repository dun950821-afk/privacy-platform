<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar">
        <span class="page-title">{{ sdk.name }}</span>
        <el-button @click="$router.back()">返回</el-button>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="名称">{{ sdk.name }}</el-descriptions-item>
        <el-descriptions-item label="厂商">{{ sdk.vendor }}</el-descriptions-item>
        <el-descriptions-item label="分类">{{ sdk.category }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ sdk.status }}</el-descriptions-item>
        <el-descriptions-item label="官网">{{ sdk.official_url }}</el-descriptions-item>
        <el-descriptions-item label="隐私政策">{{ sdk.privacy_policy_url }}</el-descriptions-item>
      </el-descriptions>
      <h3 style="margin-top:20px">识别指纹</h3>
      <el-table :data="sdk.fingerprints || []" size="small">
        <el-table-column prop="fingerprint_type" label="类型" />
        <el-table-column prop="fingerprint_value" label="值" show-overflow-tooltip />
        <el-table-column prop="weight" label="权重" width="80" />
      </el-table>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { sdkApi } from '@/api/sdks'

const route = useRoute()
const sdk = ref<any>({})
onMounted(async () => {
  const res: any = await sdkApi.get(Number(route.params.id))
  sdk.value = res.data
})
</script>
<style scoped>
.header-bar { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
</style>
