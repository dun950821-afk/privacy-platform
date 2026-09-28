<template>
  <div class="workspace">
    <!-- 左栏：项目列表 -->
    <aside class="ws-side">
      <div class="side-search">
        <el-input v-model="projectKeyword" size="small" clearable
                  placeholder="搜索项目" :prefix-icon="Search" />
      </div>
      <div class="side-list">
        <div v-for="p in filteredProjects" :key="p.id"
             :class="['proj-item', { active: selectedProject?.id === p.id }]"
             @click="selectProject(p)">
          <el-icon class="proj-icon"><Folder /></el-icon>
          <span class="proj-name">{{ p.name }}</span>
          <span v-if="p.app_count !== undefined && p.app_count !== null" class="proj-count">
            {{ p.app_count }} 个App
          </span>
          <el-icon class="proj-del" title="删除项目" @click.stop="handleDeleteProject(p)">
            <Delete />
          </el-icon>
        </div>
        <EmptyBox v-if="!filteredProjects.length" description="暂无项目" :image-size="80" />
      </div>
      <div class="side-foot">
        <el-button type="primary" :icon="Plus" style="width: 100%" @click="projectDialogVisible = true">
          新建项目
        </el-button>
      </div>
    </aside>

    <!-- 中栏：App 列表 + 版本/任务面板 -->
    <main class="ws-main">
      <template v-if="selectedProject">
        <!-- App 列表 -->
        <el-card shadow="never" class="apps-card">
          <template #header>
            <div class="card-head">
              <span class="card-title">{{ selectedProject.name }} · App 列表</span>
              <div class="head-actions">
                <el-input v-model="appKeyword" size="small" clearable style="width: 220px"
                          placeholder="搜索App名称 / 包名" :prefix-icon="Search" />
                <el-button type="primary" :icon="Upload" @click="openUploadDialog">上传APK</el-button>
              </div>
            </div>
          </template>
          <div v-if="filteredApps.length" class="app-grid" v-loading="loadingApps">
            <div v-for="a in filteredApps" :key="a.id"
                 :class="['app-card', { active: selectedApp?.id === a.id }]"
                 @click="selectApp(a)">
              <div class="app-card-head">
                <span class="app-card-name">{{ a.app_alias || a.app_name }}</span>
                <el-tag v-if="a.app_type" size="small" effect="plain">{{ a.app_type }}</el-tag>
              </div>
              <div v-if="a.app_alias && a.app_alias !== a.app_name" class="app-card-realname">
                {{ a.app_name }}
              </div>
              <div class="app-card-pkg">{{ a.package_name || '-' }}</div>
              <div class="app-card-meta">
                <span v-if="a.version_count !== undefined && a.version_count !== null">
                  {{ a.version_count }} 个版本
                </span>
                <span v-if="a.created_at">{{ fmtDate(a.created_at) }}</span>
              </div>
            </div>
          </div>
          <EmptyBox v-else description="该项目下暂无App">
            <el-button type="primary" :icon="Upload" @click="openUploadDialog">上传APK</el-button>
          </EmptyBox>
        </el-card>

        <!-- 版本与检测任务面板 -->
        <el-card v-if="selectedApp" shadow="never" class="versions-card">
          <template #header>
            <span class="card-title">{{ selectedApp.app_name }} · 版本与检测</span>
          </template>
          <div v-if="versions.length" v-loading="loadingVersions">
            <div v-for="v in pagedVersions" :key="v.id" class="version-block">
              <div class="version-head">
                <el-tag type="primary" effect="dark" size="small">{{ v.version_name }}</el-tag>
                <span class="v-code">code {{ v.version_code }}</span>
                <span class="v-meta">{{ fmtSize(v.file_size) }}</span>
                <span v-if="v.min_sdk || v.target_sdk" class="v-meta">
                  SDK {{ v.min_sdk || '?' }} ~ {{ v.target_sdk || '?' }}
                </span>
                <span class="v-meta">上传于 {{ fmtDateTime(v.created_at) }}</span>
                <el-button class="v-action" size="small" type="primary" :icon="VideoPlay"
                           @click="openTaskDialog(v)">发起检测</el-button>
              </div>
              <div v-if="versionTasks[v.id]?.length" class="v-tasks">
                <div v-for="t in versionTasks[v.id]" :key="t.id" class="task-line"
                     @click="router.push(`/tasks/${t.id}`)">
                  <span class="task-code">{{ t.task_code }}</span>
                  <StatusTag :value="t.status" :map="TASK_STATUS" />
                  <StatusTag v-if="t.analysis_coverage === 'DEGRADED'"
                             value="DEGRADED" :map="ANALYSIS_COVERAGE" />
                  <span class="task-type">{{ dictLabel(DETECTION_TYPE, t.detection_type) }}</span>
                  <span class="task-time">{{ fmtDateTime(t.created_at) }}</span>
                  <el-icon class="task-arrow"><ArrowRight /></el-icon>
                </div>
              </div>
              <div v-else class="v-no-task">暂无检测任务，点击"发起检测"开始</div>
            </div>
            <el-pagination
              v-if="versions.length > versionPageSize"
              class="versions-pager"
              small background
              layout="total, prev, pager, next"
              :total="versions.length"
              :page-size="versionPageSize"
              :current-page="versionPage"
              @current-change="handleVersionPageChange"
            />
          </div>
          <EmptyBox v-else description="暂无版本，上传APK后可发起检测" />
        </el-card>
      </template>

      <!-- 未选项目引导 -->
      <div v-else class="ws-guide">
        <EmptyBox description="请选择左侧项目，或新建项目后上传APK发起检测" :image-size="160" />
      </div>
    </main>

    <!-- 新建项目对话框 -->
    <el-dialog v-model="projectDialogVisible" title="新建项目" width="460px" @closed="resetProjectForm">
      <el-form label-width="70px">
        <el-form-item label="名称" required>
          <el-input v-model="projectForm.name" placeholder="请输入项目名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="projectForm.description" type="textarea" :rows="3"
                    placeholder="项目用途、范围说明（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingProject" @click="handleCreateProject">创建</el-button>
      </template>
    </el-dialog>

    <!-- 上传APK对话框 -->
    <el-dialog v-model="uploadDialogVisible" title="上传APK" width="560px"
               :close-on-click-modal="false" @closed="resetUpload">
      <div v-loading="uploading" element-loading-text="正在上传并自动解析APK...">
        <el-form label-width="80px">
          <el-form-item label="所属项目">
            <el-input :model-value="selectedProject?.name" disabled />
          </el-form-item>
          <el-form-item label="APK文件" required>
            <el-upload drag :auto-upload="false" :limit="1" accept=".apk"
                       :on-change="onUploadFileChange" :on-remove="onUploadFileRemove">
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">将APK拖到此处，或<em>点击选择</em></div>
              <div class="el-upload__tip">选择后自动上传解析，包名 / 版本 / SHA256 / SDK版本等信息自动获取</div>
            </el-upload>
          </el-form-item>
        </el-form>

        <!-- 解析结果 -->
        <template v-if="uploadResult">
          <div class="parse-result-head">
            <el-icon color="#18A058"><CircleCheckFilled /></el-icon>
            <span>解析成功</span>
          </div>
          <el-descriptions :column="2" border size="small" class="parse-result">
            <el-descriptions-item label="App名称" :span="2">{{ uploadResult.app_name }}</el-descriptions-item>
            <el-descriptions-item label="包名" :span="2">
              <span class="mono">{{ uploadResult.package_name || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ uploadResult.version_name }}（code {{ uploadResult.version_code }}）
            </el-descriptions-item>
            <el-descriptions-item label="文件大小">{{ fmtSize(uploadResult.file_size) }}</el-descriptions-item>
            <el-descriptions-item label="Min SDK">{{ uploadResult.min_sdk ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="Target SDK">{{ uploadResult.target_sdk ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="SHA256" :span="2">
              <span class="mono break-all">{{ uploadResult.sha256 || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-form label-width="80px" style="margin-top: 14px">
            <el-form-item label="App别称">
              <div class="alias-row">
                <el-input v-model="aliasInput" placeholder="自定义显示名（可选），便于区分同名应用"
                          maxlength="50" clearable />
                <el-button type="primary" plain :disabled="aliasInput === (uploadResult.app_alias || '')"
                           :loading="savingAlias" @click="handleSaveAlias">保存别称</el-button>
              </div>
            </el-form-item>
          </el-form>
        </template>
      </div>
      <template #footer>
        <el-button type="primary" @click="uploadDialogVisible = false">
          {{ uploadResult ? '完成' : '关闭' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 发起检测对话框 -->
    <el-dialog v-model="taskDialogVisible" title="发起检测" width="560px" @open="loadEngineOptions">
      <el-form label-width="90px">
        <el-form-item label="检测版本">
          <el-tag>{{ taskTarget?.version_name }}（code {{ taskTarget?.version_code }}）</el-tag>
        </el-form-item>
        <el-form-item label="检测类型">
          <el-select v-model="taskForm.detection_type" style="width: 100%">
            <el-option v-for="opt in detectionTypeOptions" :key="opt.value"
                       :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="规则包版本">
          <el-input v-model="taskForm.rule_pack_version" placeholder="如：1.0" />
        </el-form-item>
        <el-form-item label="检测引擎">
          <el-checkbox-group v-model="taskForm.engines" class="engine-group">
            <div v-for="e in engineOptions" :key="e.engine_type" class="engine-line">
              <el-checkbox :label="e.engine_type" :disabled="!e.env_ready">
                <span class="engine-name">{{ e.name }}</span>
                <el-tag size="small" effect="plain" style="margin-left: 6px"
                        :type="e.env_ready ? 'success' : 'info'">
                  {{ e.env_ready ? '就绪' : '未就绪' }}
                </el-tag>
              </el-checkbox>
            </div>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="needsDynamic" label="动态场景">
          <el-checkbox-group v-model="taskForm.dynamic_scenarios">
            <el-checkbox label="first_launch">首次启动</el-checkbox>
            <el-checkbox label="rejected">拒绝授权</el-checkbox>
            <el-checkbox label="consented">同意后</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-else label="检测范围">
          <el-tag type="info" size="small">仅静态分析，不执行动态检测</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingTask" @click="handleCreateTask">
          创建并提交
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Search, Folder, Upload, UploadFilled, VideoPlay, ArrowRight, Delete,
  CircleCheckFilled,
} from '@element-plus/icons-vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { fmtDate, fmtDateTime, fmtSize } from '@/utils/format'
import { dictLabel, TASK_STATUS, DETECTION_TYPE, ANALYSIS_COVERAGE } from '@/utils/dict'
import { projectApi } from '@/api/projects'
import { appApi } from '@/api/apps'
import { taskApi } from '@/api/tasks'
import { engineApi } from '@/api/engines'

const route = useRoute()
const router = useRouter()

/** 运行中任务状态（触发轮询） */
const RUNNING_STATUSES = ['queued', 'running_static', 'running_dynamic', 'analyzing', 'waiting_dynamic']

// ============ 数据 ============
const projects = ref<any[]>([])
const apps = ref<any[]>([])
const versions = ref<any[]>([])
const versionTasks = ref<Record<number, any[]>>({})
const loadingApps = ref(false)
const loadingVersions = ref(false)

// ============ 选中态与搜索 ============
const selectedProject = ref<any>(null)
const selectedApp = ref<any>(null)
const projectKeyword = ref('')
const appKeyword = ref('')

const filteredProjects = computed(() => {
  const kw = projectKeyword.value.trim().toLowerCase()
  if (!kw) return projects.value
  return projects.value.filter((p: any) => p.name?.toLowerCase().includes(kw))
})
const filteredApps = computed(() => {
  const kw = appKeyword.value.trim().toLowerCase()
  if (!kw) return apps.value
  return apps.value.filter((a: any) =>
    a.app_name?.toLowerCase().includes(kw) || a.package_name?.toLowerCase().includes(kw))
})

// ============ 加载 ============
async function loadProjects() {
  const res: any = await projectApi.list(1, 100)
  projects.value = res.data?.items || []
}

async function selectProject(p: any) {
  selectedProject.value = p
  selectedApp.value = null
  versions.value = []
  versionTasks.value = {}
  loadingApps.value = true
  try {
    const res: any = await appApi.list({ project_id: p.id, page: 1, page_size: 100 })
    apps.value = res.data?.items || []
  } finally {
    loadingApps.value = false
  }
}

async function selectApp(a: any) {
  selectedApp.value = a
  versions.value = []
  versionTasks.value = {}
  versionPage.value = 1
  loadingVersions.value = true
  try {
    const res: any = await appApi.versions(a.id)
    versions.value = res.data || []
  } finally {
    loadingVersions.value = false
  }
  await loadPageTasks()
  syncPolling()
}

// ============ 版本分页 ============
const versionPage = ref(1)
const versionPageSize = 5

const pagedVersions = computed(() => {
  const start = (versionPage.value - 1) * versionPageSize
  return versions.value.slice(start, start + versionPageSize)
})

/** 只加载当前页版本的任务，避免一次性 N+1 请求 */
async function loadPageTasks() {
  await Promise.all(pagedVersions.value.map((v: any) => loadVersionTasks(v.id)))
}

async function handleVersionPageChange(page: number) {
  versionPage.value = page
  await loadPageTasks()
  syncPolling()
}

/** 按版本精准拉取任务（修复旧版全量拉取再按 app_name 过滤的 N+1/错配问题） */
async function loadVersionTasks(versionId: number) {
  const res: any = await taskApi.list({ app_version_id: versionId, page: 1, page_size: 20 })
  versionTasks.value[versionId] = res.data?.items || []
}

// ============ 运行中任务 5s 轮询 ============
let pollTimer: ReturnType<typeof setInterval> | undefined

function hasRunningTasks(): boolean {
  return Object.values(versionTasks.value).some((list) =>
    list.some((t: any) => RUNNING_STATUSES.includes(t.status)))
}

function syncPolling() {
  if (hasRunningTasks() && !pollTimer) {
    pollTimer = setInterval(refreshVersionTasks, 5000)
  } else if (!hasRunningTasks() && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function refreshVersionTasks() {
  if (!selectedApp.value) return
  await loadPageTasks()
  syncPolling()
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// ============ URL 参数初始化 / 响应 ============
async function applyRouteParams() {
  const pid = Number(route.params.pid || 0)
  const aid = Number(route.params.aid || 0)
  if (!pid) {
    selectedProject.value = null
    selectedApp.value = null
    apps.value = []
    versions.value = []
    versionTasks.value = {}
    return
  }
  const p = projects.value.find((x: any) => x.id === pid)
  if (p && selectedProject.value?.id !== p.id) await selectProject(p)
  if (aid) {
    const a = apps.value.find((x: any) => x.id === aid)
    if (a && selectedApp.value?.id !== a.id) await selectApp(a)
  }
}

watch(() => route.params, () => {
  applyRouteParams()
})

// ============ 删除项目 ============
async function handleDeleteProject(p: any) {
  try {
    await ElMessageBox.confirm(
      `删除项目「${p.name}」将同步删除其下全部 App、版本、检测任务、事件、问题与证据文件，且不可恢复。确认删除？`,
      '删除项目',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger' }
    )
  } catch {
    return // 用户取消
  }
  try {
    const res: any = await projectApi.delete(p.id)
    const d = res?.data || {}
    ElMessage.success(`项目已删除（含 ${d.app_count ?? 0} 个App、${d.task_count ?? 0} 个检测任务）`)
    if (selectedProject.value?.id === p.id) {
      selectedProject.value = null
      selectedApp.value = null
      apps.value = []
      versions.value = []
      versionTasks.value = {}
    }
    await loadProjects()
  } catch {
    /* 错误提示由拦截器统一处理（如存在运行中任务） */
  }
}

// ============ 新建项目 ============
const projectDialogVisible = ref(false)
const creatingProject = ref(false)
const projectForm = reactive({ name: '', description: '' })

function resetProjectForm() {
  projectForm.name = ''
  projectForm.description = ''
}

async function handleCreateProject() {
  if (!projectForm.name.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  creatingProject.value = true
  try {
    const res: any = await projectApi.create({
      name: projectForm.name.trim(),
      description: projectForm.description,
    })
    ElMessage.success('项目已创建')
    projectDialogVisible.value = false
    await loadProjects()
    const p = projects.value.find((x: any) => x.id === res.data?.id)
    if (p) await selectProject(p)
  } finally {
    creatingProject.value = false
  }
}

// ============ 上传APK ============
const uploadDialogVisible = ref(false)
const uploading = ref(false)
const uploadFile = ref<File | null>(null)
const uploadResult = ref<any>(null)
const aliasInput = ref('')
const savingAlias = ref(false)

function openUploadDialog() {
  uploadDialogVisible.value = true
}

function onUploadFileChange(file: any) {
  uploadFile.value = file.raw || null
  if (uploadFile.value) {
    // 选择文件后自动上传并解析
    uploadResult.value = null
    handleUpload()
  }
}

function onUploadFileRemove() {
  uploadFile.value = null
  uploadResult.value = null
  aliasInput.value = ''
}

function resetUpload() {
  uploadFile.value = null
  uploadResult.value = null
  aliasInput.value = ''
}

async function handleUpload() {
  if (!selectedProject.value || !uploadFile.value) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('project_id', String(selectedProject.value.id))
    fd.append('file', uploadFile.value)
    const res: any = await appApi.quickUpload(fd)
    uploadResult.value = res.data
    aliasInput.value = res.data?.app_alias || ''
    ElMessage.success('上传并解析成功')
    // 刷新 App 列表并选中刚上传的 App
    await selectProject(selectedProject.value)
    const a = apps.value.find((x: any) => x.id === res.data?.app_id)
    if (a) await selectApp(a)
  } finally {
    uploading.value = false
  }
}

async function handleSaveAlias() {
  if (!uploadResult.value?.app_id) return
  savingAlias.value = true
  try {
    await appApi.update(uploadResult.value.app_id, { app_alias: aliasInput.value.trim() })
    uploadResult.value.app_alias = aliasInput.value.trim()
    ElMessage.success('别称已保存')
    // 同步刷新 App 列表中的别称显示
    const a = apps.value.find((x: any) => x.id === uploadResult.value.app_id)
    if (a) a.app_alias = aliasInput.value.trim()
  } finally {
    savingAlias.value = false
  }
}

// ============ 发起检测 ============
const taskDialogVisible = ref(false)
const creatingTask = ref(false)
const taskTarget = ref<any>(null)
const engineOptions = ref<any[]>([])
const taskForm = reactive({
  detection_type: 'full',
  rule_pack_version: '1.0',
  engines: [] as string[],
  dynamic_scenarios: ['first_launch', 'rejected', 'consented'] as string[],
})

const detectionTypeOptions = ['full', 'static_only', 'consent_pre', 'sdk_audit'].map((v) => ({
  value: v,
  label: dictLabel(DETECTION_TYPE, v),
}))

const DYNAMIC_TYPES = ['full', 'consent_pre', 'sdk_audit']
const TYPE_DEFAULT_SCENARIOS: Record<string, string[]> = {
  full: ['first_launch', 'rejected', 'consented'],
  consent_pre: ['first_launch', 'rejected'],
  sdk_audit: ['first_launch'],
}
const needsDynamic = computed(() => DYNAMIC_TYPES.includes(taskForm.detection_type))

watch(() => taskForm.detection_type, (t) => {
  taskForm.dynamic_scenarios = DYNAMIC_TYPES.includes(t)
    ? [...(TYPE_DEFAULT_SCENARIOS[t] || [])]
    : []
})

function openTaskDialog(version: any) {
  taskTarget.value = version
  taskDialogVisible.value = true
}

async function loadEngineOptions() {
  const res: any = await engineApi.list()
  engineOptions.value = res.data || []
  // 默认选中所有就绪引擎
  taskForm.engines = engineOptions.value
    .filter((e: any) => e.env_ready)
    .map((e: any) => e.engine_type)
}

async function handleCreateTask() {
  if (!taskTarget.value) return
  creatingTask.value = true
  try {
    const res: any = await taskApi.create({
      app_version_id: taskTarget.value.id,
      detection_type: taskForm.detection_type,
      rule_pack_version: taskForm.rule_pack_version,
      config: {
        engines: taskForm.engines,
        dynamic_scenarios: needsDynamic.value ? taskForm.dynamic_scenarios : [],
      },
    })
    const taskId = res.data.id
    await taskApi.submit(taskId)
    ElMessage.success('检测任务已创建并提交')
    taskDialogVisible.value = false
    await loadVersionTasks(taskTarget.value.id)
    syncPolling()
  } finally {
    creatingTask.value = false
  }
}

onMounted(async () => {
  await loadProjects()
  await applyRouteParams()
})
</script>

<style scoped>
.workspace {
  display: flex;
  gap: 16px;
  height: calc(100vh - 60px);
  padding: 16px;
  overflow: hidden;
}

/* 左栏：项目 */
.ws-side {
  width: 240px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.side-search {
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.side-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.proj-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.proj-item:hover { background: #F7F8FA; }
.proj-item.active { background: #EEF3FE; color: #2B5AED; }
.proj-icon { flex-shrink: 0; font-size: 15px; }
.proj-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.proj-count { flex-shrink: 0; font-size: 11px; color: #8F959E; }
.proj-del {
  flex-shrink: 0;
  font-size: 13px;
  color: #C0C4CC;
  display: none;
  border-radius: 4px;
  padding: 2px;
}
.proj-item:hover .proj-del { display: inline-flex; }
.proj-del:hover { color: #D03050; background: #FEF0F0; }
.side-foot {
  padding: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 中栏 */
.ws-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}
.apps-card { flex-shrink: 0; }
.versions-card { flex-shrink: 0; }
.versions-pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.card-title { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.head-actions { display: flex; align-items: center; gap: 12px; }

/* App 卡片 */
.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.app-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px 14px;
  cursor: pointer;
  background: #FAFBFC;
  transition: all 0.15s;
}
.app-card:hover { border-color: #2B5AED; background: #fff; }
.app-card.active {
  border-color: #2B5AED;
  background: #F5F8FF;
  box-shadow: 0 0 0 2px #EEF3FE;
}
.app-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.app-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-card-pkg {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-card-meta {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.app-card-realname {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 上传解析结果 */
.parse-result-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #18A058;
}
.alias-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.mono { font-family: monospace; font-size: 12px; }
.break-all { word-break: break-all; }

/* 版本块 */
.version-block {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #FAFBFC;
}
.version-block:last-child { margin-bottom: 0; }
.version-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.v-code { font-size: 13px; color: var(--el-text-color-regular); }
.v-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.v-action { margin-left: auto; }
.v-no-task {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* 版本内任务行 */
.v-tasks {
  margin-top: 8px;
  border-top: 1px dashed var(--el-border-color-light);
  padding-top: 4px;
}
.task-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.task-line:hover { background: #F0F4FF; }
.task-code {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  font-family: monospace;
}
.task-type { font-size: 12px; color: var(--el-text-color-regular); }
.task-time { margin-left: auto; font-size: 12px; color: var(--el-text-color-secondary); }
.task-arrow { font-size: 12px; color: var(--el-text-color-placeholder); }

/* 未选项目引导 */
.ws-guide {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}

/* 引擎选择 */
.engine-group { width: 100%; }
.engine-line { line-height: 28px; }
.engine-name { font-size: 13px; }
</style>
