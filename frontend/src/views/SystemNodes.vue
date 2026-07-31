<template>
  <div class="page-container">
    <el-card shadow="never">
      <div class="header-bar"><span class="page-title">节点与设备</span></div>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="Agent节点" name="nodes">
          <el-table :data="nodes" size="small">
            <el-table-column prop="node_name" label="名称" />
            <el-table-column prop="node_type" label="类型" />
            <el-table-column prop="status" label="状态" width="80" />
            <el-table-column prop="capabilities" label="能力" />
            <el-table-column prop="last_heartbeat_at" label="最后心跳" width="180" />
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="Android设备" name="devices">
          <el-table :data="devices" size="small">
            <el-table-column prop="serial" label="序列号" />
            <el-table-column prop="brand" label="品牌" />
            <el-table-column prop="model" label="型号" />
            <el-table-column prop="android_version" label="Android版本" />
            <el-table-column prop="status" label="状态" width="80" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { systemApi } from '@/api/system'
const activeTab = ref('nodes')
const nodes = ref<any[]>([])
const devices = ref<any[]>([])
onMounted(async () => {
  const n: any = await systemApi.nodes(); nodes.value = n.data
  const d: any = await systemApi.devices(); devices.value = d.data
})
</script>
<style scoped>
.header-bar { margin-bottom:16px; }
.page-title { font-size:16px; font-weight:600; }
</style>
