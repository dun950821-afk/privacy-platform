<template>
  <div class="workspace">
    <!-- 左栏：项目列表 -->
    <div class="col-projects">
      <div class="col-header">
        <span class="col-title">项目</span>
        <el-button size="small" type="primary" :icon="Plus" @click="showNewProject = true" />
      </div>
      <div class="col-body">
        <div v-for="p in projects" :key="p.id"
             :class="['tree-item', { active: selectedProject?.id === p.id }]"
             @click="selectProject(p)">
          <el-icon class="tree-icon"><Folder /></el-icon>
          <span class="tree-label">{{ p.name }}</span>
        </div>
        <el-empty v-if="!projects.length" description="暂无项目" :image-size="40" />
      </div>
    </div>

    <!-- 中栏：App版本 -->
    <div class="col-apps" v-if="selectedProject">
      <div class="col-header">
        <div class="header-left">
          <el-icon class="back-btn" @click="selectedProject = null"><ArrowLeft /></el-icon>
          <span class="col-title">{{ selectedProject.name }}</span>
        </div>
        <div>
          <el-button size="small" type="primary" :icon="Upload" @click="showQuickUpload = true">上传APK</el-button>
        </div>
      </div>
      <div class="col-body">
        <div v-for="a in apps" :key="a.id"
             :class="['tree-item app-item', { active: selectedApp?.id === a.id }]"
             @click="selectApp(a)">
          <el-icon class="tree-icon"><Cellphone /></el-icon>
          <div class="app-info">
            <div class="tree-label">{{ a.app_name }}</div>
            <div class="app-pkg">{{ a.package_name }}</div>
          </div>
        </div>
        <el-empty v-if="!apps.length" description="暂无App，点击注册App" :image-size="40" />
      </div>

      <!-- 版本+任务面板 -->
      <div class="version-task-panel" v-if="selectedApp">
        <div class="panel-header">
          <span class="panel-title">{{ selectedApp.app_name }} - 版本与检测</span>
        </div>
        <div class="panel-body">
          <div v-for="v in versions" :key="v.id" class="version-row">
            <div class="version-info">
              <el-tag size="small" type="success">{{ v.version_name }}</el-tag>
              <span class="version-code">v{{ v.version_code }}</span>
              <span class="version-meta">{{ formatSize(v.file_size) }}</span>
              <span class="version-meta" v-if="v.min_sdk">SDK {{ v.min_sdk }}-{{ v.target_sdk || '?' }}</span>
              <span class="version-meta">{{ formatDate(v.created_at) }}</span>
            </div>
            <div class="version-actions">
              <el-button size="small" type="primary" :icon="VideoPlay"
                         @click="createTask(v)">发起检测</el-button>
            </div>
            <!-- 版本下的任务列表 -->
            <div class="task-list" v-if="versionTasks[v.id]?.length">
              <div v-for="t in versionTasks[v.id]" :key="t.id" class="task-row"
                   @click="$router.push(`/tasks/${t.id}`)">
                <el-tag :type="taskStatusType(t.status)" size="small" effect="plain">
                  {{ taskStatusLabel(t.status) }}
                </el-tag>
                <span class="task-type-label">{{ detectionTypeLabel(t.detection_type) }}</span>
                <span class="task-date">{{ formatDate(t.created_at) }}</span>
                <el-icon class="task-arrow"><ArrowRight /></el-icon>
              </div>
            </div>
          </div>
          <el-empty v-if="!versions.length" description="暂无版本，点击上传APK" :image-size="40" />
        </div>
      </div>
    </div>

    <!-- 空状态引导 -->
    <div class="empty-guide" v-if="!selectedProject">
      <el-icon :size="48" color="#C0C4CC"><FolderOpened /></el-icon>
      <p class="guide-title">选择左侧项目开始检测</p>
      <p class="guide-desc">或新建项目 → 上传APK（自动解析） → 发起检测</p>
    </div>

    <!-- 新建项目对话框 -->
    <el-dialog v-model="showNewProject" title="新建项目" width="460px">
      <el-form :model="projForm" label-width="70px">
        <el-form-item label="名称"><el-input v-model="projForm.name" placeholder="请输入项目名称" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="projForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showNewProject = false">取消</el-button>
        <el-button type="primary" @click="handleCreateProject">创建</el-button>
      </template>
    </el-dialog>

    <!-- 一体化上传APK对话框 -->
    <el-dialog v-model="showQuickUpload" title="上传APK" width="480px">
      <el-form :model="quickUploadForm" label-width="80px">
        <el-form-item label="App名称" required>
          <el-input v-model="quickUploadForm.app_name" placeholder="如：测网速UUSpeed" />
        </el-form-item>
        <el-form-item label="APK文件" required>
          <el-upload :auto-upload="false" :limit="1" accept=".apk" :on-change="handleQuickFileChange" drag>
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽APK或点击上传</div>
          </el-upload>
        </el-form-item>
        <el-alert type="info" :closable="false" v-if="!quickUploadParsing">
          <template #title>包名、版本、权限等信息将从APK自动解析</template>
        </el-alert>
        <div v-if="quickUploadResult" class="parse-result">
          <el-descriptions :column="1" border size="small" title="解析结果">
            <el-descriptions-item label="包名">{{ quickUploadResult.parsed?.package_name }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ quickUploadResult.version_name }} ({{ quickUploadResult.version_code }})</el-descriptions-item>
            <el-descriptions-item label="SHA256">{{ quickUploadResult.sha256?.substring(0, 16) }}...</el-descriptions-item>
            <el-descriptions-item label="大小">{{ formatSize(quickUploadResult.file_size) }}</el-descriptions-item>
            <el-descriptions-item label="Min SDK">{{ quickUploadResult.parsed?.min_sdk || '-' }}</el-descriptions-item>
            <el-descriptions-item label="Target SDK">{{ quickUploadResult.parsed?.target_sdk || '-' }}</el-descriptions-item>
            <el-descriptions-item label="权限数">{{ quickUploadResult.parsed?.permissions?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="Activity数">{{ quickUploadResult.parsed?.activities?.length || 0 }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showQuickUpload = false">取消</el-button>
        <el-button type="primary" :loading="quickUploading" @click="handleQuickUpload">上传并解析</el-button>
      </template>
    </el-dialog>

    <!-- 发起检测对话框 -->
    <el-dialog v-model="showCreateTask" title="发起检测" width="620px" @open="loadEngineOptions">
      <el-form :model="taskForm" label-width="90px">
        <el-form-item label="检测版本">
          <el-tag>{{ taskTargetVersion?.version_name }} (v{{ taskTargetVersion?.version_code }})</el-tag>
        </el-form-item>
        <el-form-item label="检测类型">
          <el-select v-model="taskForm.detection_type" style="width:100%">
            <el-option label="完整检测（静态+动态）" value="full" />
            <el-option label="静态专项检测" value="static_only" />
            <el-option label="同意前专项" value="consent_pre" />
            <el-option label="SDK专项审计" value="sdk_audit" />
          </el-select>
        </el-form-item>
        <el-form-item label="检测引擎">
          <div class="engine-select-list">
            <div v-for="e in engineOptions" :key="e.engine_type"
                 :class="['engine-option', {
                   selected: taskForm.config.engines?.includes(e.engine_type),
                   disabled: !e.env_ready
                 }]"
                 @click="toggleEngine(e)">
              <div class="engine-opt-header">
                <el-checkbox :model-value="taskForm.config.engines?.includes(e.engine_type)"
                             :disabled="!e.env_ready" @click.stop />
                <span class="engine-opt-name">{{ e.name }}</span>
                <el-tag size="small" :type="e.env_ready ? 'success' : 'info'" effect="plain">
                  {{ e.env_ready ? '就绪' : '未安装' }}
                </el-tag>
              </div>
              <p class="engine-opt-desc">{{ e.description }}</p>
              <div class="engine-opt-caps">
                <span v-for="cap in e.capabilities" :key="cap" class="cap-chip">{{ capLabel(cap) }}</span>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="动态场景" v-if="needsDynamic">
          <el-checkbox-group v-model="taskForm.config.dynamic_scenarios">
            <el-checkbox label="first_launch">首次启动</el-checkbox>
            <el-checkbox label="rejected">拒绝同意</el-checkbox>
            <el-checkbox label="consented">同意政策</el-checkbox>
            <el-checkbox label="revoked">撤回同意</el-checkbox>
          </el-checkbox-group>
          <div class="scene-hint">该检测类型包含动态检测，可选择场景</div>
        </el-form-item>
        <el-form-item v-else label="检测范围">
          <el-tag type="info" size="small">仅静态分析，不执行动态检测</el-tag>
        </el-form-item>
        <el-form-item label="规则包">
          <el-input v-model="taskForm.rule_pack_version" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateTask = false">取消</el-button>
        <el-button type="primary" :loading="creatingTask" @click="handleCreateTask">提交检测</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Plus, Folder, Cellphone, ArrowLeft, ArrowRight, Upload, UploadFilled,
  VideoPlay, Document, FolderOpened
} from '@element-plus/icons-vue'
import { projectApi } from '@/api/projects'
import { appApi } from '@/api/apps'
import { taskApi } from '@/api/tasks'
import { engineApi } from '@/api/engines'

const route = useRoute()
const router = useRouter()

// 数据
const projects = ref<any[]>([])
const apps = ref<any[]>([])
const versions = ref<any[]>([])
const versionTasks = ref<Record<number, any[]>>({})

// 选中状态
const selectedProject = ref<any>(null)
const selectedApp = ref<any>(null)

// 对话框
const showNewProject = ref(false)
const showQuickUpload = ref(false)
const showCreateTask = ref(false)
const creatingTask = ref(false)

// 表单
const projForm = reactive({ name: '', description: '' })
const quickUploadForm = reactive({ app_name: '' })
const quickUploadFile = ref<File | null>(null)
const quickUploading = ref(false)
const quickUploadParsing = ref(false)
const quickUploadResult = ref<any>(null)
const taskForm = reactive({
  detection_type: 'full',
  rule_pack_version: '1.0',
  config: {
    dynamic_scenarios: ['first_launch', 'rejected', 'consented'],
    engines: ['androguard'] as string[]
  }
})

// 引擎选项
const engineOptions = ref<any[]>([])
async function loadEngineOptions() {
  try {
    const res: any = await engineApi.list()
    engineOptions.value = res.data || []
    // 默认选中所有就绪的引擎
    const readyEngines = engineOptions.value.filter((e: any) => e.env_ready).map((e: any) => e.engine_type)
    if (readyEngines.length) {
      taskForm.config.engines = readyEngines
    }
  } catch (e) {
    console.error('loadEngineOptions failed', e)
  }
}
function toggleEngine(e: any) {
  if (!e.env_ready) return
  const engines = taskForm.config.engines || []
  const idx = engines.indexOf(e.engine_type)
  if (idx >= 0) {
    engines.splice(idx, 1)
  } else {
    engines.push(e.engine_type)
  }
  taskForm.config.engines = [...engines]
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

// 需要动态检测的类型
const DYNAMIC_TYPES = ['full', 'consent_pre', 'sdk_audit']
const TYPE_DEFAULT_SCENARIOS: Record<string, string[]> = {
  full: ['first_launch', 'rejected', 'consented'],
  consent_pre: ['first_launch', 'rejected'],
  sdk_audit: ['first_launch'],
}
const needsDynamic = computed(() => DYNAMIC_TYPES.includes(taskForm.detection_type))

// 切换检测类型时自动设置默认场景
watch(() => taskForm.detection_type, (t) => {
  if (DYNAMIC_TYPES.includes(t)) {
    taskForm.config.dynamic_scenarios = [...(TYPE_DEFAULT_SCENARIOS[t] || [])]
  } else {
    taskForm.config.dynamic_scenarios = []
  }
})
const taskTargetVersion = ref<any>(null)
const selectedFile = ref<File | null>(null)

// 加载项目
async function loadProjects() {
  try {
    const res: any = await projectApi.list(1, 100)
    projects.value = res.data?.items || []
  } catch (e) {
    console.error('loadProjects failed', e)
  }
  // 如果URL有pid，自动选中
  const pid = route.params.pid
  if (pid) {
    const p = projects.value.find((x: any) => x.id === Number(pid))
    if (p) selectProject(p)
  }
}

// 选中项目 → 加载App
async function selectProject(p: any) {
  selectedProject.value = p
  selectedApp.value = null
  versions.value = []
  try {
    const res: any = await appApi.list({ project_id: p.id, page: 1, page_size: 100 })
    apps.value = res.data?.items || []
  } catch (e) {
    console.error('selectProject failed', e)
    apps.value = []
  }
  // 如果URL有aid，自动选中
  const aid = route.params.aid
  if (aid) {
    const a = apps.value.find((x: any) => x.id === Number(aid))
    if (a) selectApp(a)
  }
}

// 选中App → 加载版本和任务
async function selectApp(a: any) {
  selectedApp.value = a
  versions.value = []
  versionTasks.value = {}
  try {
    const res: any = await appApi.versions(a.id)
    versions.value = res.data || []
  } catch (e) {
    console.error('selectApp failed', e)
    versions.value = []
  }
  // 加载每个版本的任务
  for (const v of versions.value) {
    loadVersionTasks(v.id)
  }
}

async function loadVersionTasks(versionId: number) {
  try {
    const res: any = await taskApi.list({ page: 1, page_size: 50 })
    const all = res.data?.items || []
    versionTasks.value[versionId] = all.filter((t: any) => {
      return t.app_name === selectedApp.value?.app_name
    })
  } catch (e) {
    console.error('loadVersionTasks failed', e)
  }
}

// 新建项目
async function handleCreateProject() {
  if (!projForm.name) { ElMessage.warning('请输入名称'); return }
  await projectApi.create(projForm)
  ElMessage.success('项目已创建')
  showNewProject.value = false
  projForm.name = ''; projForm.description = ''
  loadProjects()
}

// 一体化上传APK
function handleQuickFileChange(file: any) { quickUploadFile.value = file.raw }

async function handleQuickUpload() {
  if (!quickUploadForm.app_name) { ElMessage.warning('请输入App名称'); return }
  if (!quickUploadFile.value) { ElMessage.warning('请选择APK文件'); return }

  quickUploading.value = true
  quickUploadParsing.value = true
  quickUploadResult.value = null
  try {
    const fd = new FormData()
    fd.append('project_id', String(selectedProject.value.id))
    fd.append('app_name', quickUploadForm.app_name)
    fd.append('file', quickUploadFile.value)
    const res: any = await appApi.quickUpload(fd)
    quickUploadResult.value = res.data
    ElMessage.success('上传并解析成功')
    // 刷新App列表
    selectProject(selectedProject.value)
  } catch (e) {
    ElMessage.error('上传失败')
  } finally {
    quickUploading.value = false
    quickUploadParsing.value = false
  }
}

// 发起检测
function createTask(version: any) {
  taskTargetVersion.value = version
  showCreateTask.value = true
}

async function handleCreateTask() {
  if (!taskTargetVersion.value) return
  creatingTask.value = true
  try {
    const res: any = await taskApi.create({
      app_version_id: taskTargetVersion.value.id,
      detection_type: taskForm.detection_type,
      rule_pack_version: taskForm.rule_pack_version,
      config: taskForm.config
    })
    const taskId = res.data.id
    await taskApi.submit(taskId)
    ElMessage.success('检测任务已提交')
    showCreateTask.value = false
    router.push(`/tasks/${taskId}`)
  } finally { creatingTask.value = false }
}

// 查看版本的任务


// 工具函数
function formatSize(bytes: number) {
  if (!bytes) return '-'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
function formatDate(d: string) {
  if (!d) return '-'
  return d.substring(0, 19).replace('T', ' ')
}
function taskStatusType(s: string) {
  const m: Record<string, string> = { draft: 'info', queued: 'warning', completed: 'success', failed: 'danger' }
  return m[s] || ''
}
function taskStatusLabel(s: string) {
  const m: Record<string, string> = {
    draft: '草稿', queued: '队列中', preparing: '准备中', running_static: '静态检测',
    running_dynamic: '动态检测', waiting_dynamic: '等待动态', analyzing: '分析中',
    reviewing: '复核中', completed: '已完成', failed: '失败', canceled: '已取消'
  }
  return m[s] || s
}
function detectionTypeLabel(t: string) {
  const m: Record<string, string> = {
    full: '完整检测', static_only: '静态专项', consent_pre: '同意前专项', sdk_audit: 'SDK审计'
  }
  return m[t] || t
}

onMounted(loadProjects)
</script>

<style scoped>
.workspace {
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* 左栏 */
.col-projects {
  width: 240px;
  border-right: 1px solid #E8EAEC;
  background: #fff;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #E8EAEC;
}
.header-left { display: flex; align-items: center; gap: 8px; }
.back-btn { cursor: pointer; color: #646A73; font-size: 16px; }
.col-title { font-size: 14px; font-weight: 600; color: #1F2329; }
.col-body { flex: 1; overflow-y: auto; padding: 8px; }

/* 中栏 */
.col-apps {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 树项 */
.tree-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.tree-item:hover { background: #F7F8FA; }
.tree-item.active { background: #EEF3FE; color: #2B5AED; }
.tree-icon { flex-shrink: 0; font-size: 16px; }
.tree-label { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.app-item { flex-direction: row; align-items: flex-start; }
.app-info { flex: 1; min-width: 0; }
.app-pkg { font-size: 11px; color: #8F959E; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 版本任务面板 */
.version-task-panel {
  border-top: 1px solid #E8EAEC;
  background: #fff;
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.panel-header { margin-bottom: 12px; }
.panel-title { font-size: 15px; font-weight: 600; color: #1F2329; }
.panel-body { }
.version-row {
  padding: 12px 16px;
  border: 1px solid #E8EAEC;
  border-radius: 8px;
  margin-bottom: 12px;
  background: #FAFBFC;
}
.version-info { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.version-code { font-size: 13px; color: #646A73; }
.version-meta { font-size: 12px; color: #8F959E; }
.version-actions { display: flex; gap: 8px; }

/* 任务行 */
.task-list { margin-top: 8px; }
.task-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.task-row:hover { background: #F0F4FF; }
.task-type-label { font-size: 12px; color: #646A73; }
.task-date { font-size: 12px; color: #8F959E; margin-left: auto; }
.task-arrow { font-size: 12px; color: #C0C4CC; }

/* 空状态 */
.empty-guide {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #C0C4CC;
}
.scene-hint { font-size: 12px; color: #8F959E; margin-top: 4px; }

/* 引擎选择 */
.engine-select-list { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.engine-option {
  border: 1px solid #E8EAEC; border-radius: 8px; padding: 10px 12px;
  cursor: pointer; transition: all 0.15s; background: #fff;
}
.engine-option:hover { border-color: #2B5AED; }
.engine-option.selected { border-color: #2B5AED; background: #F5F8FF; }
.engine-option.disabled { opacity: 0.5; cursor: not-allowed; }
.engine-opt-header { display: flex; align-items: center; gap: 6px; }
.engine-opt-name { font-size: 14px; font-weight: 600; color: #1F2329; }
.engine-opt-desc { font-size: 12px; color: #646A73; margin: 4px 0; }
.engine-opt-caps { display: flex; flex-wrap: wrap; gap: 4px; }
.cap-chip {
  font-size: 11px; background: #F0F1F3; color: #646A73;
  padding: 1px 6px; border-radius: 3px;
}
.parse-result { margin-top: 12px; }
.guide-title { font-size: 15px; margin-top: 12px; color: #8F959E; }
.guide-desc { font-size: 13px; margin-top: 4px; color: #C0C4CC; }
</style>
