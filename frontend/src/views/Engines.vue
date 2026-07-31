<template>
  <div class="page-container">
    <!-- 引擎统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <div class="stat-card" style="border-top-color:#2B5AED">
          <div class="stat-icon" style="background:#EEF3FE;color:#2B5AED">
            <el-icon :size="24"><Cpu /></el-icon>
          </div>
          <div>
            <div class="stat-value">{{ engines.length }}</div>
            <div class="stat-label">注册引擎</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="border-top-color:#18A058">
          <div class="stat-icon" style="background:#E8F8EE;color:#18A058">
            <el-icon :size="24"><CircleCheck /></el-icon>
          </div>
          <div>
            <div class="stat-value">{{ readyCount }}</div>
            <div class="stat-label">环境就绪</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="border-top-color:#F0A020">
          <div class="stat-icon" style="background:#FFF7E6;color:#F0A020">
            <el-icon :size="24"><Histogram /></el-icon>
          </div>
          <div>
            <div class="stat-value">{{ stats.total_executions || 0 }}</div>
            <div class="stat-label">总执行次数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card" style="border-top-color:#D03050">
          <div class="stat-icon" style="background:#FEF0F0;color:#D03050">
            <el-icon :size="24"><Warning /></el-icon>
          </div>
          <div>
            <div class="stat-value">{{ stats.by_status?.failed || 0 }}</div>
            <div class="stat-label">执行失败</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <!-- 左侧：引擎列表 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span class="card-title">检测引擎</span>
              <el-button size="small" :icon="Refresh" @click="loadEngines">刷新</el-button>
            </div>
          </template>
          <div class="engine-list">
            <div v-for="e in engines" :key="e.engine_type" class="engine-card">
              <div class="engine-header">
                <div class="engine-name-area">
                  <el-icon :size="20" :color="e.env_ready ? '#18A058' : '#C0C4CC'">
                    <Cpu v-if="e.engine_type === 'androguard'" />
                    <Connection v-else-if="e.engine_type === 'appshark'" />
                    <Monitor v-else-if="e.engine_type === 'mobsf'" />
                    <Cpu v-else />
                  </el-icon>
                  <span class="engine-name">{{ e.name }}</span>
                  <el-tag size="small" type="info">v{{ e.version }}</el-tag>
                </div>
                <el-tag :type="e.env_ready ? 'success' : 'warning'" size="small" effect="dark">
                  {{ e.env_ready ? '就绪' : '未配置' }}
                </el-tag>
              </div>
              <p class="engine-desc">{{ e.description }}</p>
              <div class="engine-caps">
                <el-tag v-for="cap in e.capabilities" :key="cap" size="small" effect="plain" class="cap-tag">
                  {{ capLabel(cap) }}
                </el-tag>
              </div>
              <!-- 未就绪时显示安装指引 -->
              <div v-if="!e.env_ready" class="install-guide">
                <el-alert type="warning" :closable="false" show-icon>
                  <template #title>环境未就绪</template>
                  <div class="guide-content">
                    <span class="guide-label">安装方式：</span>
                    <code class="guide-code">{{ e.install_guide }}</code>
                  </div>
                </el-alert>
              </div>
              <div class="engine-actions">
                <el-button size="small" :icon="Check" @click="handleHealthCheck(e.engine_type)">环境检查</el-button>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：引擎统计 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span class="card-title">执行统计</span></template>
          <el-table :data="stats.by_engine || []" size="small" stripe>
            <el-table-column prop="engine_name" label="引擎" width="100" />
            <el-table-column prop="total" label="总数" width="60" />
            <el-table-column prop="success" label="成功" width="60">
              <template #default="{ row }">
                <span style="color:#18A058">{{ row.success }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="failed" label="失败" width="60">
              <template #default="{ row }">
                <span style="color:#D03050">{{ row.failed }}</span>
              </template>
            </el-table-column>
            <el-table-column label="平均耗时">
              <template #default="{ row }">
                {{ row.avg_duration_ms > 0 ? (row.avg_duration_ms / 1000).toFixed(1) + 's' : '-' }}
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!stats.by_engine?.length" class="empty-tip">暂无执行记录</div>
        </el-card>

        <el-card shadow="never" style="margin-top:12px">
          <template #header><span class="card-title">最近执行</span></template>
          <div v-for="r in stats.recent || []" :key="r.id" class="recent-item">
            <el-tag :type="execStatusType(r.status)" size="small">{{ execStatusLabel(r.status) }}</el-tag>
            <span class="recent-engine">{{ r.engine_name }}</span>
            <span class="recent-time">{{ fmtDate(r.created_at) }}</span>
            <span class="recent-duration" v-if="r.duration_ms">{{ (r.duration_ms/1000).toFixed(1) }}s</span>
          </div>
          <div v-if="!stats.recent?.length" class="empty-tip">暂无执行记录</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 执行历史 -->
    <el-card shadow="never" style="margin-top:16px">
      <template #header>
        <div class="card-header">
          <span class="card-title">执行历史</span>
          <div class="filter-bar">
            <el-select v-model="filterEngine" placeholder="引擎" clearable size="small" @change="loadExecutions" style="width:120px">
              <el-option v-for="e in engines" :key="e.engine_type" :label="e.name" :value="e.engine_type" />
            </el-select>
            <el-select v-model="filterStatus" placeholder="状态" clearable size="small" @change="loadExecutions" style="width:100px">
              <el-option label="执行中" value="running" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
            </el-select>
          </div>
        </div>
      </template>
      <el-table :data="executions" v-loading="loadingExec" size="small" stripe>
        <el-table-column prop="engine_name" label="引擎" width="100" />
        <el-table-column prop="engine_version" label="版本" width="80" />
        <el-table-column prop="task_code" label="任务" width="160" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="execStatusType(row.status)" size="small">{{ execStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="event_count" label="事件数" width="70" />
        <el-table-column label="耗时" width="80">
          <template #default="{ row }">
            {{ row.duration_ms ? (row.duration_ms/1000).toFixed(1)+'s' : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" width="160">
          <template #default="{ row }">{{ fmtDate(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误" show-overflow-tooltip />
      </el-table>
      <el-pagination class="pager" v-model:current-page="execPage" :page-size="20"
        :total="execTotal" layout="total, prev, pager, next" @current-change="loadExecutions" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Cpu, CircleCheck, Histogram, Warning, Refresh, Check, Connection, Monitor
} from '@element-plus/icons-vue'
import { engineApi } from '@/api/engines'

const engines = ref<any[]>([])
const stats = ref<any>({})
const executions = ref<any[]>([])
const loadingExec = ref(false)
const execPage = ref(1)
const execTotal = ref(0)
const filterEngine = ref('')
const filterStatus = ref('')

const readyCount = computed(() => engines.value.filter(e => e.env_ready).length)

async function loadEngines() {
  const res: any = await engineApi.list()
  engines.value = res.data
}

async function loadStats() {
  const res: any = await engineApi.stats()
  stats.value = res.data
}

async function loadExecutions() {
  loadingExec.value = true
  try {
    const res: any = await engineApi.executions({
      engine_type: filterEngine.value || undefined,
      status: filterStatus.value || undefined,
      page: execPage.value, page_size: 20,
    })
    executions.value = res.data.items
    execTotal.value = res.data.total
  } finally {
    loadingExec.value = false
  }
}

async function handleHealthCheck(engineType: string) {
  const res: any = await engineApi.healthCheck(engineType)
  const d = res.data
  ElMessage[d.env_ready ? 'success' : 'warning'](
    `${d.name}: ${d.env_ready ? '环境就绪' : '环境未配置'}`
  )
  loadEngines()
}

function capLabel(cap: string) {
  const m: Record<string, string> = {
    BASIC_INFO: '基础信息', PERMISSIONS: '权限', COMPONENTS: '组件',
    SIGNATURE: '签名', STRINGS: '字符串', DATA_FLOW: '数据流',
    TAINT_ANALYSIS: '污点分析', STATIC_SCAN: '静态扫描',
    MALWARE_CHECK: '恶意检测', TRACKER_DETECTION: '跟踪器',
  }
  return m[cap] || cap
}

function execStatusType(s: string) {
  const m: Record<string, string> = { completed: 'success', failed: 'danger', running: 'warning', pending: 'info' }
  return m[s] || 'info'
}
function execStatusLabel(s: string) {
  const m: Record<string, string> = { completed: '完成', failed: '失败', running: '执行中', pending: '等待' }
  return m[s] || s
}
function fmtDate(d: string) {
  if (!d) return '-'
  return d.substring(0, 19).replace('T', ' ')
}

onMounted(() => {
  loadEngines()
  loadStats()
  loadExecutions()
})
</script>

<style scoped>
.page-container { padding: 20px; }
.stat-row { margin-bottom: 16px; }
.stat-card {
  background: #fff; border-radius: 8px; padding: 16px 20px;
  display: flex; align-items: center; gap: 14px;
  border-top: 3px solid #2B5AED;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.stat-icon {
  width: 44px; height: 44px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
}
.stat-value { font-size: 24px; font-weight: 700; color: #1F2329; }
.stat-label { font-size: 12px; color: #8F959E; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-size: 14px; font-weight: 600; color: #1F2329; }
.filter-bar { display: flex; gap: 8px; }

.engine-list { display: flex; flex-direction: column; gap: 12px; }
.engine-card {
  border: 1px solid #E8EAEC; border-radius: 8px; padding: 14px 16px;
  background: #FAFBFC; transition: all 0.15s;
}
.engine-card:hover { border-color: #2B5AED; background: #fff; }
.engine-header { display: flex; justify-content: space-between; align-items: center; }
.engine-name-area { display: flex; align-items: center; gap: 8px; }
.engine-name { font-size: 15px; font-weight: 600; color: #1F2329; }
.engine-desc { font-size: 13px; color: #646A73; margin: 8px 0; }
.engine-caps { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.cap-tag { font-size: 11px; }
.install-guide { margin: 8px 0; }
.guide-content { display: flex; align-items: center; gap: 4px; margin-top: 4px; }
.guide-label { font-size: 12px; color: #8F959E; }
.guide-code {
  font-size: 12px; background: #FFF7E6; color: #F0A020;
  padding: 2px 8px; border-radius: 4px; word-break: break-all;
}
.engine-actions { display: flex; gap: 8px; }

.empty-tip { text-align: center; padding: 20px; color: #C0C4CC; font-size: 13px; }
.pager { margin-top: 12px; justify-content: flex-end; }

.recent-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0; border-bottom: 1px solid #F0F1F3; font-size: 13px;
}
.recent-item:last-child { border-bottom: none; }
.recent-engine { color: #1F2329; font-weight: 500; }
.recent-time { color: #8F959E; margin-left: auto; font-size: 12px; }
.recent-duration { color: #646A73; font-size: 12px; }
</style>
