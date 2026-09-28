<template>
  <div class="report-viewer" v-loading="loading">
    <el-alert v-if="error" type="warning" :closable="false" show-icon :title="error" />

    <template v-else-if="report">
      <!-- 规则与报告元信息 -->
      <div class="meta-row">
        <span class="meta-title mono">{{ report.provider_rule_id || report.report_name }}</span>
        <span v-if="report.rule?.detail" class="meta-detail">{{ report.rule.detail }}</span>
      </div>

      <EmptyBox v-if="!codeLines.length" description="该规则未提供代码上下文" :image-size="60" />

      <template v-else>
        <div class="code-hint">
          <span class="tag tag-source">[Source]</span> 污点源
          <span class="tag tag-sink">[Sink]</span> 汇聚点
          <span class="tag tag-step">[n]</span> 数据流第 n 步
        </div>
        <div v-for="(block, bi) in report.code_blocks" :key="bi" class="code-block">
          <div v-if="block.method" class="code-method mono">{{ block.method }}</div>
          <div class="code-body">
            <div v-for="(item, li) in block.lines" :key="li"
                 class="code-line" :class="lineClass(item)">
              <span class="ln mono">{{ item.line ?? '' }}</span>
              <span v-if="item.marker" class="mk mono">[{{ item.marker }}]</span>
              <span class="tx mono">{{ item.text }}</span>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EmptyBox from '@/components/EmptyBox.vue'
import { taskApi } from '@/api/tasks'

const props = defineProps<{ taskId: number; observationId: number }>()

const report = ref<any>(null)
const loading = ref(false)
const error = ref('')

const codeLines = computed(() =>
  (report.value?.code_blocks || []).flatMap((b: any) => b.lines || []))

function lineClass(item: any) {
  const marker = (item.marker || '').toLowerCase()
  if (marker === 'source') return 'is-source'
  if (marker === 'sink') return 'is-sink'
  if (item.marker) return 'is-step'
  if (item.line === null || item.line === undefined) return 'is-label'
  return ''
}

async function load() {
  report.value = null
  error.value = ''
  if (!props.taskId || !props.observationId) return
  loading.value = true
  try {
    const res = await taskApi.engineReport(props.taskId, props.observationId)
    report.value = res.data
  } catch (e: any) {
    // 404 是正常情形：不是每条观察都有引擎报告（如权限类事实）
    error.value = e?.response?.status === 404
      ? '该条观察没有对应的引擎报告'
      : '引擎报告读取失败'
  } finally {
    loading.value = false
  }
}

watch(() => props.observationId, load, { immediate: true })
</script>

<style scoped>
.report-viewer { font-size: 12px; }
.meta-row { display: flex; gap: 8px; align-items: baseline; margin-bottom: 8px; flex-wrap: wrap; }
.meta-title { font-weight: 600; }
.meta-detail { color: #6B7A99; }
.code-hint { color: #6B7A99; margin-bottom: 8px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.tag { padding: 0 4px; border-radius: 3px; font-family: monospace; }
.tag-source { background: #FDE2E2; color: #C4361D; }
.tag-sink { background: #E1E9FF; color: #2B5AED; }
.tag-step { background: #EEF1F6; color: #6B7A99; }
.code-block { margin-bottom: 12px; }
.code-method { color: #2B5AED; margin-bottom: 4px; word-break: break-all; }
.code-body { background: #FAFBFD; border: 1px solid #EEF1F6; border-radius: 4px; overflow-x: auto; }
.code-line { display: flex; gap: 8px; padding: 1px 8px; white-space: pre; }
.code-line .ln { width: 34px; text-align: right; color: #B4BDCC; flex: none; }
.code-line .mk { flex: none; color: #6B7A99; }
.code-line .tx { word-break: break-all; white-space: pre-wrap; }
.code-line.is-source { background: #FDE2E2; }
.code-line.is-sink { background: #E1E9FF; }
.code-line.is-step { background: #F5F7FA; }
.code-line.is-label { color: #B4BDCC; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
