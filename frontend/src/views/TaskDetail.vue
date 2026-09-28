<template>
  <div class="page-container" v-loading="loading">
    <!-- 顶部：任务标题 + 操作 -->
    <PageHeader :title="task.task_code || '任务详情'" :subtitle="headerSubtitle">
      <StatusTag v-if="task.status" :value="task.status" :map="TASK_STATUS" size="default" />
      <StatusTag v-if="task.analysis_coverage" :value="task.analysis_coverage"
                 :map="ANALYSIS_COVERAGE" size="default" />
      <el-button v-if="canRetry" type="warning" plain :icon="RefreshRight" @click="handleRetry">
        重试
      </el-button>
      <el-button v-if="canCancel" type="danger" plain :icon="CircleClose" @click="handleCancel">
        取消任务
      </el-button>
      <el-button v-if="task.status === 'completed'" type="primary" :icon="Document"
                 :loading="generating" @click="handleGenerateReport">
        生成报告
      </el-button>
      <el-button :icon="DataAnalysis" @click="router.push(`/tasks/${taskId}/report`)">
        检测报告
      </el-button>
      <el-button :icon="ArrowLeft" @click="router.push('/workspace')">返回</el-button>
    </PageHeader>

    <!-- 进度步骤条 -->
    <el-card shadow="never" class="mb16">
      <el-steps :active="stepActive" align-center
                :process-status="processStatus" :finish-status="finishStatus">
        <el-step v-for="s in steps" :key="s" :title="s" />
      </el-steps>
    </el-card>

    <!-- 信息行：检测对象 + 任务信息 -->
    <el-row :gutter="16" class="mb16">
      <el-col :span="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">检测对象</span></template>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item label="App">{{ task.app?.name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="包名">
              <span class="mono">{{ task.app?.package_name || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="版本">
              {{ task.version?.version_name || '-' }}（code {{ task.version?.version_code ?? '-' }}）
            </el-descriptions-item>
            <el-descriptions-item label="SHA256">
              <span class="mono">{{ task.version?.sha256 || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="文件大小">
              {{ fmtSize(task.version?.file_size) }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">任务信息</span></template>
          <el-descriptions :column="2" size="small">
            <el-descriptions-item label="检测类型">
              <StatusTag :value="task.detection_type" :map="DETECTION_TYPE" />
            </el-descriptions-item>
            <el-descriptions-item label="规则包版本">{{ task.rule_pack_version || '-' }}</el-descriptions-item>
            <el-descriptions-item label="优先级">{{ task.priority ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建人">{{ task.created_by_name || task.created_by || '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ fmtDateTime(task.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ fmtDateTime(task.started_at) }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ fmtDateTime(task.completed_at) }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="task.failed_reason" class="failed-reason">
            <span class="failed-label">失败原因：</span>{{ task.failed_reason }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据区 Tabs -->
    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <!-- 检测结果：结论在前，原始结果按引擎各自的特点分区 -->
        <el-tab-pane label="检测结果" name="workspace">
          <TaskWorkspace :task-id="taskId" :engine-queue="engineQueue.items || []"
                          :focus="workspaceFocus" />
        </el-tab-pane>

        <!-- ① 检测阶段 -->
        <el-tab-pane :label="`检测阶段 (${subTasks.length})`" name="subtasks">
          <el-table :data="subTasks" size="small" stripe>
            <el-table-column prop="sub_task_code" label="子任务编号" width="180">
              <template #default="{ row }"><span class="mono">{{ row.sub_task_code }}</span></template>
            </el-table-column>
            <el-table-column label="引擎" width="140">
              <template #default="{ row }">{{ engineNames(row) }}</template>
            </el-table-column>
            <el-table-column prop="stage" label="阶段" width="110" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="EXEC_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="开始时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="完成时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.completed_at) }}</template>
            </el-table-column>
            <el-table-column label="结果摘要" min-width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ summaryText(row.result_summary) }}</template>
            </el-table-column>
            <el-table-column prop="error_message" label="错误信息" min-width="140"
                             show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.error_message" class="error-text">{{ row.error_message }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无检测阶段" /></template>
          </el-table>
        </el-tab-pane>

        <!-- ② 检测场景 -->
        <el-tab-pane :label="`检测场景 (${scenarios.length})`" name="scenarios">
          <el-table :data="scenarios" size="small" stripe>
            <el-table-column label="场景类型" width="150">
              <template #default="{ row }">
                {{ dictLabel(SCENARIO_TYPE, row.scenario_type) }}
              </template>
            </el-table-column>
            <el-table-column label="同意状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.consent_status" :map="CONSENT_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="执行状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="EXEC_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="设备" width="140">
              <template #default="{ row }">{{ row.device || row.device_id || '-' }}</template>
            </el-table-column>
            <el-table-column label="开始时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="完成时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.completed_at) }}</template>
            </el-table-column>
            <el-table-column prop="notes" label="备注" min-width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.notes || '-' }}</template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无检测场景" /></template>
          </el-table>
        </el-tab-pane>

        <!-- ②.5 引擎队列 -->
        <el-tab-pane :label="`引擎队列 (${engineQueue.items?.length || 0})`" name="engine_queue">
          <el-timeline v-if="engineQueue.items?.length">
            <el-timeline-item v-for="item in engineQueue.items" :key="item.id" :type="engineStatusType(item.status)" :timestamp="fmtDateTime(item.started_at || item.completed_at)">
              <strong>{{ item.engine_name }}</strong>
              <span class="sub-text"> · {{ engineStatusLabel(item.status) }} · {{ item.stage_message || item.stage || '-' }}</span>
              <el-progress v-if="item.progress != null" :percentage="item.progress" :stroke-width="6" />
              <div v-if="item.error_message" class="error-text">{{ item.error_message }}</div>
              <div v-if="item.error_code" class="sub-text">错误码：{{ item.error_code }} · 可重试：{{ item.retryable ? '是' : '否' }}</div>
              <el-button v-if="canRetryEngine(item)" size="small" type="warning" plain
                         :loading="retryingId === item.id" @click="handleEngineRetry(item)">重新执行本引擎</el-button>
            </el-timeline-item>
          </el-timeline>
          <EmptyBox v-else description="暂无引擎执行记录" />
        </el-tab-pane>

        <!-- ③ 事件流 -->
        <!-- ④ SDK识别 -->
        <el-tab-pane :label="`SDK识别 (${sdkHits.length})`" name="sdks">
          <el-table :data="sdkHits" size="small" stripe v-loading="loadingSdkHits">
            <el-table-column label="SDK名称" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link type="primary" :underline="false" @click="openSdkDetail(row)">
                  {{ row.sdk_name }}
                </el-link>
              </template>
            </el-table-column>
            <el-table-column prop="category" label="分类" width="110">
              <template #default="{ row }">{{ row.category || '-' }}</template>
            </el-table-column>
            <el-table-column prop="vendor" label="厂商" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.vendor || '-' }}</template>
            </el-table-column>
            <el-table-column label="置信度" width="80">
              <template #default="{ row }">
                <StatusTag :value="row.confidence_level" :map="SENSITIVITY" />
              </template>
            </el-table-column>
            <el-table-column label="综合得分" width="110">
              <template #default="{ row }">
                <div class="score-cell">
                  <el-progress :percentage="row.total_score" :stroke-width="6"
                               :color="scoreColor(row.total_score)" :show-text="false" />
                  <span class="score-num">{{ row.total_score }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="evidence_count" label="证据数" width="80" align="center" />
            <el-table-column label="涉及信息" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.involved_info?.length ? row.involved_info.join('、') : '-' }}
              </template>
            </el-table-column>
            <el-table-column label="包名前缀" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.package_prefixes?.[0] || row.primary_package || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="敏感权限" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.sensitive_permission" type="danger" size="small">涉及</el-tag>
                <el-tag v-else type="info" size="small" effect="plain">否</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.hit_status" :map="HIT_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openSdkDetail(row)">查看证据</el-button>
                <el-button v-if="row.hit_status !== 'REJECTED'" link type="danger"
                           @click="reviewHit(row, 'reject')">误报</el-button>
                <el-button v-else link type="success" @click="reviewHit(row, 'confirm')">恢复</el-button>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="未识别到SDK" /></template>
          </el-table>
        </el-tab-pane>

        <!-- ⑤ 未识别包簇 -->
        <el-tab-pane :label="`未识别包簇 (${clusters.length})`" name="clusters">
          <el-alert type="info" :closable="false" class="cluster-tip"
                    title="以下包前缀未命中知识库。可标记为自研代码 / 关联已有SDK / 创建新SDK知识 / 加入白名单 / 标记加固组件，知识库将随扫描持续完善。" />
          <el-table :data="clusters" size="small" stripe v-loading="loadingClusters">
            <el-table-column label="包名前缀" min-width="190" show-overflow-tooltip>
              <template #default="{ row }">
                <el-link type="primary" :underline="false" class="mono"
                         @click="openClusterClasses(row)">{{ row.package_prefix }}</el-link>
              </template>
            </el-table-column>
            <el-table-column prop="class_count" label="类数量" width="80" align="center" />
            <el-table-column label="组件分布" width="140">
              <template #default="{ row }">{{ typeStatText(row.component_type_stat) }}</template>
            </el-table-column>
            <el-table-column label="推测属性" width="130">
              <template #default="{ row }">
                <el-tag size="small" effect="plain"
                        :type="row.guess_attr?.includes('加固') ? 'danger'
                              : row.guess_attr?.includes('自研') ? 'success' : 'info'">
                  {{ row.guess_attr }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <StatusTag :value="row.review_status" :map="REVIEW_STATUS" />
                <div v-if="row.linked_component_name" class="linked-name">
                  → {{ row.linked_component_name }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="首次出现" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.first_seen_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-dropdown trigger="click" @command="(cmd: string) => handleClusterAction(cmd, row)">
                  <el-button link type="primary">处理<el-icon><ArrowDown /></el-icon></el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="classes">查看全部类</el-dropdown-item>
                      <el-dropdown-item command="self_code">标记为自研代码</el-dropdown-item>
                      <el-dropdown-item command="link">关联已有SDK</el-dropdown-item>
                      <el-dropdown-item command="create">创建新SDK知识</el-dropdown-item>
                      <el-dropdown-item command="whitelist">加入白名单</el-dropdown-item>
                      <el-dropdown-item command="packer">标记为加固组件</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="无未识别包簇" /></template>
          </el-table>
        </el-tab-pane>

        <!-- ⑥ 问题 -->
        <el-tab-pane :label="`问题 (${findings.length})`" name="findings">
          <el-table :data="findings" size="small" stripe class="clickable-table"
                    @row-click="(row: any) => router.push(`/findings/${row.id}`)">
            <el-table-column label="严重度" width="90">
              <template #default="{ row }">
                <StatusTag :value="row.severity" :map="SEVERITY" />
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
            <el-table-column prop="data_type" label="数据类型" width="110">
              <template #default="{ row }">{{ row.data_type || '-' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <StatusTag :value="row.status" :map="FINDING_STATUS" />
              </template>
            </el-table-column>
            <el-table-column label="发现时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
            </el-table-column>
            <template #empty>
              <EmptyBox :description="task.analysis_coverage === 'DEGRADED' ? '本次分析未生效，不能据此判断' : '未发现问题'" />
            </template>
          </el-table>
        </el-tab-pane>

        <!-- ⑤ 证据 -->
        <el-tab-pane :label="`证据 (${evidenceList.length})`" name="evidence">
          <el-table :data="evidenceList" size="small" stripe>
            <el-table-column label="类型" width="180">
              <template #default="{ row }">
                {{ evidenceTypeLabel(row.evidence_type) }}
                <span v-if="row.metadata_json?.engine" class="perm-sub">
                  · {{ row.metadata_json.engine }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ fmtSize(row.artifact_size) }}</template>
            </el-table-column>
            <el-table-column label="哈希" width="140">
              <template #default="{ row }">
                <span class="mono">{{ row.artifact_hash ? row.artifact_hash.slice(0, 12) : '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" width="150">
              <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" :icon="View"
                           @click.stop="openPreview(row)">预览</el-button>
                <el-button link type="primary" size="small" :icon="Download"
                           @click.stop="downloadEvidence(row)">下载</el-button>
              </template>
            </el-table-column>
            <template #empty><EmptyBox description="暂无证据" /></template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 事件详情抽屉 -->

    <!-- SDK识别详情抽屉 -->
    <el-drawer v-model="sdkDrawerVisible" size="640px" :title="sdkDetail?.sdk_name || 'SDK详情'">
      <template v-if="sdkDetail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="厂商" :span="2">
            {{ sdkDetail.vendor || '未知' }}
            <el-link v-if="sdkDetail.vendor_website" :href="sdkDetail.vendor_website"
                     target="_blank" type="primary" style="margin-left: 8px">官网</el-link>
          </el-descriptions-item>
          <el-descriptions-item label="分类">{{ sdkDetail.category || '-' }}</el-descriptions-item>
          <el-descriptions-item label="识别状态">
            <StatusTag :value="sdkDetail.hit_status" :map="HIT_STATUS" />
          </el-descriptions-item>
          <el-descriptions-item label="置信度">
            <StatusTag :value="sdkDetail.confidence_level" :map="SENSITIVITY" />
          </el-descriptions-item>
          <el-descriptions-item label="综合得分">
            <span class="score-num">{{ sdkDetail.total_score }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="检测规则版本">{{ sdkDetail.rule_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="SDK版本">{{ sdkDetail.detected_version || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="json-title">证据汇总（{{ sdkDetail.evidence_total }} 条）</div>
        <div class="ev-stat-cards">
          <div v-for="(count, type) in sdkDetail.evidence_type_stat" :key="type" class="ev-stat-card">
            <div class="ev-stat-num">{{ count }}</div>
            <div class="ev-stat-type">{{ evidenceKindLabel(String(type)) }}</div>
          </div>
        </div>

        <div class="json-title">证据明细</div>
        <el-table :data="sdkDetail.evidences" size="small" stripe max-height="380">
          <el-table-column label="类型" width="100">
            <template #default="{ row }">{{ evidenceKindLabel(row.evidence_type) }}</template>
          </el-table-column>
          <el-table-column label="命中特征" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <el-link type="primary" :underline="false" class="mono"
                       @click="jumpToEvent(sdkDetail.component_id, row.evidence_value)">
                {{ row.evidence_value }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="score" label="分值" width="70" align="center" />
          <el-table-column prop="source" label="来源" width="90" />
        </el-table>
        <div class="ev-jump-tip">点击命中特征可跳回事件流并定位高亮该事件</div>
      </template>
    </el-drawer>

    <!-- 包簇类列表抽屉 -->
    <el-drawer v-model="clusterDrawerVisible" size="560px"
               :title="`包簇类列表 · ${currentCluster?.package_prefix || ''}`">
      <el-table :data="clusterClasses" size="small" stripe v-loading="loadingClusterClasses">
        <el-table-column label="类名" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" :underline="false" class="mono"
                     @click="jumpToEvent(null, row.class_name)">{{ row.class_name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="组件类型" width="100">
          <template #default="{ row }">{{ evidenceKindLabel(row.component_type) }}</template>
        </el-table-column>
        <template #empty><EmptyBox description="该包簇下无类" /></template>
      </el-table>
    </el-drawer>

    <!-- 关联已有SDK对话框 -->
    <el-dialog v-model="linkDialogVisible" title="关联已有SDK" width="480px">
      <el-select v-model="linkComponentId" filterable remote clearable
                 :remote-method="searchComponents" :loading="searchingComponents"
                 placeholder="输入SDK名称搜索" style="width: 100%">
        <el-option v-for="c in componentOptions" :key="c.id"
                   :label="`${c.name}（${c.vendor || '未知厂商'}）`" :value="c.id" />
      </el-select>
      <template #footer>
        <el-button @click="linkDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!linkComponentId" @click="confirmLink">关联</el-button>
      </template>
    </el-dialog>

    <!-- 创建新SDK知识对话框 -->
    <el-dialog v-model="createSdkDialogVisible" title="创建新SDK知识" width="480px">
      <el-form label-width="90px">
        <el-form-item label="包名前缀">
          <el-input :model-value="currentCluster?.package_prefix" disabled />
        </el-form-item>
        <el-form-item label="SDK名称" required>
          <el-input v-model="createSdkName" placeholder="如：某某统计SDK" maxlength="100" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="createSdkKind" style="width: 100%">
            <el-option v-for="(item, value) in COMPONENT_KIND" :key="value"
                       :label="item.label" :value="value" />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert type="success" :closable="false"
                title="将创建组件并自动添加包名前缀指纹（PREFIX匹配，权重30），后续扫描即可自动识别" />
      <template #footer>
        <el-button @click="createSdkDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!createSdkName.trim()" @click="confirmCreateSdk">
          创建并关联
        </el-button>
      </template>
    </el-dialog>

    <!-- 证据预览对话框（可拖拽调整大小） -->
    <el-dialog v-model="previewVisible" :title="previewTitle" :width="previewSize.w + 'px'" top="4vh">
      <div v-loading="previewLoading" class="preview-body" :style="{ height: previewSize.h + 'px' }">
        <img v-if="previewKind === 'image' && previewUrl" :src="previewUrl"
             class="preview-image" alt="证据预览" />
        <template v-else-if="previewKind === 'text'">
          <pre class="json-pre preview-text">{{ previewContent }}</pre>
          <div v-if="previewTruncated" class="preview-truncated">
            文件过大，仅显示前 512KB，完整内容请下载查看
          </div>
        </template>
        <EmptyBox v-else-if="previewKind === 'unsupported'"
                  description="该文件类型暂不支持预览，请下载后查看">
          <el-button type="primary" :icon="Download" @click="downloadEvidence(previewRow)">
            下载文件
          </el-button>
        </EmptyBox>
        <div class="resize-grip" title="拖拽调整大小" @mousedown="startResize">
          <el-icon><Rank /></el-icon>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, RefreshRight, CircleClose, Document, Download, View, ArrowRight, Rank, ArrowDown, Setting, DataAnalysis } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusTag from '@/components/StatusTag.vue'
import EmptyBox from '@/components/EmptyBox.vue'
import AppSharkPanel from '@/components/AppSharkPanel.vue'
import TaskWorkspace from '@/components/TaskWorkspace.vue'
import api from '@/api'
import { taskApi } from '@/api/tasks'
import { reportApi } from '@/api/reports'
import { sdkApi } from '@/api/sdks'
import { engineApi } from '@/api/engines'
import { fmtDateTime, fmtDateTimeFull, fmtSize } from '@/utils/format'
import {
  dictLabel, TASK_STATUS, EXEC_STATUS, SEVERITY, FINDING_STATUS,
  SCENARIO_TYPE, CONSENT_STATUS, EVENT_TYPE, DETECTION_TYPE,
  COMPONENT_KIND, SENSITIVITY, HIT_STATUS, ANALYSIS_COVERAGE,
} from '@/utils/dict'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => Number(route.params.id))

const loading = ref(true)
const generating = ref(false)
const activeTab = ref('subtasks')

const task = ref<any>({})
const subTasks = computed<any[]>(() => task.value.sub_tasks || [])
const engineQueue = computed<any>(() => task.value.engine_queue || { items: [] })
const retryingId = ref<number | null>(null)
const ENGINE_RETRYABLE = ['failed', 'timed_out', 'canceled']
function canRetryEngine(item: any) {
  return ENGINE_RETRYABLE.includes(item.status) && item.retryable
}
async function handleEngineRetry(item: any) {
  retryingId.value = item.id
  try {
    await engineApi.retryExecution(item.id)
    ElMessage.success(`已重新排队：${item.engine_name}`)
    await loadTask()
  } finally {
    retryingId.value = null
  }
}
const engineStatusLabel = (status: string) => ({ pending: '等待执行', running: '执行中', completed: '已完成', failed: '失败', canceled: '已取消' }[status] || status)
const engineStatusType = (status: string) => ({ pending: 'info', running: 'primary', completed: 'success', failed: 'danger', canceled: 'warning' }[status] || 'info') as any

const scenarios = ref<any[]>([])
const events = ref<any[]>([])
const eventPage = ref(1)
const workspaceFocus = ref<any>(null)
const eventTotal = ref(0)
const loadingEvents = ref(false)
const eventTypeFilter = ref('')
const eventDataTypeFilter = ref('')
const eventSdkFilter = ref<number | ''>('')
const matchedSdks = ref<any[]>([])
const highlightValue = ref('')

// ============ 事件流自定义列 ============
const EVENT_COLUMN_DEFS = [
  { key: 'time', label: '时间' },
  { key: 'type', label: '类型' },
  { key: 'consent', label: '同意状态' },
  { key: 'dataType', label: '数据类型' },
  { key: 'api', label: 'API / 路径' },
  { key: 'caller', label: '调用方' },
  { key: 'permission', label: '权限' },
  { key: 'permissionCategory', label: '权限类别' },
  { key: 'permissionCapability', label: '能力说明' },
  { key: 'permissionRisk', label: '权限风险' },
  { key: 'sdk', label: '关联SDK' },
  { key: 'engine', label: '引擎' },
  { key: 'engineVersion', label: '引擎版本' },
  { key: 'traceId', label: 'Trace ID' },
  { key: 'eventUid', label: '事件ID' },
]
const DEFAULT_EVENT_COLS = ['time', 'type', 'consent', 'dataType', 'api', 'caller', 'permission', 'permissionCategory', 'permissionCapability', 'permissionRisk', 'sdk', 'engine']
const EVENT_COLS_STORAGE_KEY = 'task-detail-event-columns'

function loadEventCols(): string[] {
  try {
    const raw = localStorage.getItem(EVENT_COLS_STORAGE_KEY)
    const keys: unknown = raw ? JSON.parse(raw) : null
    if (!Array.isArray(keys)) return [...DEFAULT_EVENT_COLS]
    const validKeys = EVENT_COLUMN_DEFS.map(c => c.key)
    const filtered = keys.filter((k): k is string => validKeys.includes(k))
    return filtered.length ? filtered : [...DEFAULT_EVENT_COLS]
  } catch {
    return [...DEFAULT_EVENT_COLS]
  }
}

const visibleEventCols = ref<string[]>(loadEventCols())

watch(visibleEventCols, (v) => {
  if (!v.length) { // 至少保留一列，避免空表格
    visibleEventCols.value = ['time']
    return
  }
  localStorage.setItem(EVENT_COLS_STORAGE_KEY, JSON.stringify(v))
})

function eventColVisible(key: string): boolean {
  return visibleEventCols.value.includes(key)
}

function resetEventCols() {
  visibleEventCols.value = [...DEFAULT_EVENT_COLS]
}

// ============ SDK识别 / 未识别包簇 ============
const sdkHits = ref<any[]>([])
const loadingSdkHits = ref(false)
const clusters = ref<any[]>([])
const loadingClusters = ref(false)
const sdkDrawerVisible = ref(false)
const sdkDetail = ref<any>(null)

const REVIEW_STATUS: Record<string, { label: string; type: 'primary' | 'success' | 'warning' | 'danger' | 'info' }> = {
  pending: { label: '待识别', type: 'warning' },
  self_code: { label: '自研代码', type: 'info' },
  linked: { label: '已关联', type: 'success' },
  whitelisted: { label: '白名单', type: 'info' },
  packer: { label: '加固组件', type: 'danger' },
}
const findings = ref<any[]>([])
const evidenceList = ref<any[]>([])

/** 运行中状态（触发轮询 / 允许取消） */
const RUNNING_STATUSES = ['queued', 'running_static', 'running_dynamic', 'waiting_dynamic', 'analyzing']

const headerSubtitle = computed(() => {
  const app = task.value.app?.name
  const version = task.value.version?.version_name
  if (!app && !version) return undefined
  return [app, version].filter(Boolean).join(' · ')
})

const canRetry = computed(() => ['failed', 'canceled'].includes(task.value.status))
const canCancel = computed(() => RUNNING_STATUSES.includes(task.value.status))

// ============ 进度步骤条 ============
const DYNAMIC_TYPES = ['full', 'consent_pre', 'sdk_audit']
const hasDynamic = computed(() => DYNAMIC_TYPES.includes(task.value.detection_type))

const steps = computed(() =>
  hasDynamic.value
    ? ['创建', '静态检测', '动态检测', '分析判定', '完成']
    : ['创建', '静态检测', '分析判定', '完成'])

const stepActive = computed(() => {
  const status = task.value.status
  const dyn = hasDynamic.value
  switch (status) {
    case 'draft': return 0
    case 'queued': return 1
    case 'running_static': return 1
    case 'waiting_dynamic':
    case 'running_dynamic': return dyn ? 2 : 1
    case 'analyzing': return dyn ? 3 : 2
    case 'completed': return steps.value.length
    case 'failed': {
      // 按已完成的子任务数推断失败发生的位置
      const done = (task.value.sub_tasks || [])
        .filter((s: any) => s.status === 'completed').length
      return Math.min(1 + done, steps.value.length - 1)
    }
    case 'canceled': return 1
    default: return 0
  }
})

const processStatus = computed<'process' | 'error' | 'wait'>(() => {
  if (task.value.status === 'failed') return 'error'
  if (task.value.status === 'canceled') return 'wait'
  return 'process'
})
const finishStatus = computed<'success' | 'wait'>(() =>
  task.value.status === 'canceled' ? 'wait' : 'success')

// ============ 数据加载 ============
async function loadTask() {
  const res: any = await taskApi.get(taskId.value)
  task.value = res.data
}

async function loadScenarios() {
  const res: any = await taskApi.scenarios(taskId.value)
  scenarios.value = res.data || []
}

async function loadEvents() {
  loadingEvents.value = true
  try {
    const res: any = await taskApi.events(taskId.value, {
      event_type: eventTypeFilter.value || undefined,
      data_type: eventDataTypeFilter.value.trim() || undefined,
      sdk_id: eventSdkFilter.value || undefined,
      page: eventPage.value,
      page_size: 50,
    })
    events.value = res.data?.items || []
    eventTotal.value = res.data?.total || 0
    matchedSdks.value = res.data?.matched_sdks || []
  } finally {
    loadingEvents.value = false
  }
}

/** 得分进度条颜色 */
function scoreColor(score: number): string {
  if (score >= 70) return '#18A058'
  if (score >= 40) return '#F0A020'
  return '#8F959E'
}

// ============ SDK识别 ============
async function loadSdkHits() {
  loadingSdkHits.value = true
  try {
    const res: any = await api.get(`/tasks/${taskId.value}/sdk-hits`)
    sdkHits.value = res.data || []
  } finally {
    loadingSdkHits.value = false
  }
}

async function openSdkDetail(row: any) {
  const res: any = await api.get(`/tasks/${taskId.value}/sdk-hits/${row.hit_id}`)
  sdkDetail.value = res.data
  sdkDrawerVisible.value = true
}

/** 事件流"已关联"图标 → 跳到SDK识别并打开详情 */
async function openSdkByComponent(componentId: number) {
  if (!sdkHits.value.length) await loadSdkHits()
  const hit = sdkHits.value.find((h: any) => h.component_id === componentId)
  activeTab.value = 'sdks'
  if (hit) openSdkDetail(hit)
}

async function reviewHit(row: any, action: string) {
  if (action === 'reject') {
    try {
      await ElMessageBox.confirm(
        `确认将「${row.sdk_name}」标记为误报？标记后不再计入识别结果（可恢复）。`,
        '标记误报', { type: 'warning', confirmButtonText: '确认标记', cancelButtonText: '取消' }
      )
    } catch { return }
  }
  await api.post(`/tasks/${taskId.value}/sdk-hits/${row.hit_id}/review`, { action })
  ElMessage.success(action === 'reject' ? '已标记为误报' : '已恢复')
  loadSdkHits()
}

// ============ 未识别包簇 ============
const clusterDrawerVisible = ref(false)
const currentCluster = ref<any>(null)
const clusterClasses = ref<any[]>([])
const loadingClusterClasses = ref(false)

async function loadClusters() {
  loadingClusters.value = true
  try {
    const res: any = await api.get(`/tasks/${taskId.value}/package-clusters`)
    clusters.value = res.data || []
  } finally {
    loadingClusters.value = false
  }
}

async function openClusterClasses(row: any) {
  currentCluster.value = row
  clusterDrawerVisible.value = true
  loadingClusterClasses.value = true
  try {
    const res: any = await api.get(`/tasks/${taskId.value}/package-clusters/${row.id}/classes`)
    clusterClasses.value = res.data?.classes || []
  } finally {
    loadingClusterClasses.value = false
  }
}

const linkDialogVisible = ref(false)
const linkComponentId = ref<number | null>(null)
const componentOptions = ref<any[]>([])
const searchingComponents = ref(false)

async function searchComponents(keyword: string) {
  searchingComponents.value = true
  try {
    const res: any = await sdkApi.list({ keyword: keyword || undefined, page: 1, page_size: 20 })
    componentOptions.value = res.data?.items || []
  } finally {
    searchingComponents.value = false
  }
}

const createSdkDialogVisible = ref(false)
const createSdkName = ref('')
const createSdkKind = ref('SDK')

function handleClusterAction(cmd: string, row: any) {
  currentCluster.value = row
  if (cmd === 'classes') {
    openClusterClasses(row)
  } else if (cmd === 'link') {
    linkComponentId.value = null
    componentOptions.value = []
    searchComponents('')
    linkDialogVisible.value = true
  } else if (cmd === 'create') {
    createSdkName.value = ''
    createSdkKind.value = 'SDK'
    createSdkDialogVisible.value = true
  } else {
    const labels: Record<string, string> = {
      self_code: '标记为自研代码', whitelist: '加入白名单', packer: '标记为加固组件',
    }
    ElMessageBox.confirm(`确认将包簇「${row.package_prefix}」${labels[cmd]}？`, '包簇处理',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
      .then(async () => {
        await api.post(`/tasks/${taskId.value}/package-clusters/${row.id}/review`, { action: cmd })
        ElMessage.success('处理完成')
        loadClusters()
      })
      .catch(() => {})
  }
}

async function confirmLink() {
  await api.post(`/tasks/${taskId.value}/package-clusters/${currentCluster.value.id}/review`,
    { action: 'link', component_id: linkComponentId.value })
  ElMessage.success('已关联')
  linkDialogVisible.value = false
  loadClusters()
}

async function confirmCreateSdk() {
  await api.post(`/tasks/${taskId.value}/package-clusters/${currentCluster.value.id}/review`,
    { action: 'create', name: createSdkName.value.trim(), kind: createSdkKind.value })
  ElMessage.success('已创建SDK知识并关联')
  createSdkDialogVisible.value = false
  loadClusters()
  loadSdkHits()
}

// ============ 证据 → 事件流 跳转定位 ============
function jumpToEvent(componentId: number | null, value: string) {
  sdkDrawerVisible.value = false
  clusterDrawerVisible.value = false
  // 原始事件流由工作台承载（已不再是独立 tab），定位条件传给它
  activeTab.value = 'workspace'
  workspaceFocus.value = { sdkId: componentId, keyword: value, at: Date.now() }
}

function eventRowClass({ row }: { row: any }): string {
  return highlightValue.value && row.api === highlightValue.value ? 'evidence-highlight' : ''
}

// ============ 展示辅助 ============
function evidenceKindLabel(t: string): string {
  const m: Record<string, string> = {
    ACTIVITY: 'Activity', SERVICE: 'Service', RECEIVER: 'Receiver',
    PROVIDER: 'Provider', PACKAGE_PREFIX: '包名前缀', CLASS: '类名',
    RESOURCE: '资源文件', PERMISSION: '权限',
  }
  return m[t] || t || '-'
}

function typeStatText(stat: any): string {
  if (!stat || typeof stat !== 'object') return '-'
  const parts = Object.entries(stat)
    .map(([k, v]) => `${evidenceKindLabel(k)} ${v}`)
  return parts.length ? parts.join(' · ') : '-'
}

function handleEventFilterChange() {
  eventPage.value = 1
  highlightValue.value = ''
  loadEvents()
}

async function loadFindings() {
  const res: any = await taskApi.findings(taskId.value)
  findings.value = res.data || []
}

async function loadEvidence() {
  const res: any = await taskApi.evidence(taskId.value)
  evidenceList.value = res.data || []
}

async function loadAll() {
  loading.value = true
  try {
    await loadTask()
    await Promise.all([loadScenarios(), loadEvents(), loadFindings(), loadEvidence(),
                       loadSdkHits(), loadClusters()])
  } finally {
    loading.value = false
  }
  syncPolling()
}

// ============ 运行中 5s 轮询（任务详情 + 子任务/场景） ============
let pollTimer: ReturnType<typeof setInterval> | undefined

function syncPolling() {
  if (RUNNING_STATUSES.includes(task.value.status) && !pollTimer) {
    pollTimer = setInterval(pollRunning, 5000)
  } else if (!RUNNING_STATUSES.includes(task.value.status) && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function pollRunning() {
  try {
    await loadTask()
    await loadScenarios()
  } catch {
    /* 轮询失败静默，等待下次 */
  }
  syncPolling()
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// ============ 操作 ============
async function handleRetry() {
  await taskApi.retry(taskId.value)
  ElMessage.success('任务已重新提交')
  await loadAll()
}

async function handleCancel() {
  try {
    await ElMessageBox.confirm('确认取消该检测任务？取消后可通过"重试"重新执行。', '取消任务', {
      confirmButtonText: '确认取消',
      cancelButtonText: '再想想',
      type: 'warning',
    })
  } catch {
    return // 用户放弃取消
  }
  await taskApi.cancel(taskId.value)
  ElMessage.success('任务已取消')
  await loadAll()
}

async function handleGenerateReport() {
  generating.value = true
  try {
    await reportApi.generate(taskId.value)
    ElMessage.success('报告已生成，可前往报告中心查看')
  } finally {
    generating.value = false
  }
}

// ============ 事件详情抽屉 ============
const eventDrawerVisible = ref(false)
const currentEvent = ref<any>(null)

const eventTypeOptions = Object.entries(EVENT_TYPE).map(([value, item]) => ({
  value,
  label: item.label,
}))

const eventDataJson = computed(() => {
  if (!currentEvent.value?.event_data) return ''
  try {
    return JSON.stringify(currentEvent.value.event_data, null, 2)
  } catch {
    return String(currentEvent.value.event_data)
  }
})

function openEventDrawer(row: any) {
  currentEvent.value = row
  eventDrawerVisible.value = true
}

// ============ 证据下载 ============
function evidenceTypeLabel(t: string): string {
  const m: Record<string, string> = {
    screenshot: '截图', api_call_stack: '调用栈', network_request: '报文',
    traffic_capture: '抓包', log_file: '日志', engine_output: '引擎输出',
    human_note: '人工说明', screen_recording: '录屏',
  }
  return m[t] || t || '-'
}

async function downloadEvidence(row: any) {
  try {
    const blob: any = await api.get(`/evidence/${row.id}/download`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([blob]))
    const link = document.createElement('a')
    link.href = url
    link.download =
      row.metadata_json?.filename || row.evidence_uid || `evidence-${row.id}`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch {
    ElMessage.error('下载失败')
  }
}

// ============ 证据预览 ============
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewKind = ref<'' | 'image' | 'text' | 'unsupported'>('')
const previewUrl = ref('')
const previewContent = ref('')
const previewTruncated = ref(false)
const previewTitle = ref('证据预览')
const previewRow = ref<any>(null)

function clearPreviewUrl() {
  if (previewUrl.value) {
    window.URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

async function openPreview(row: any) {
  previewRow.value = row
  previewTitle.value = `证据预览 · ${evidenceTypeLabel(row.evidence_type)}`
  previewVisible.value = true
  previewLoading.value = true
  previewKind.value = ''
  previewContent.value = ''
  previewTruncated.value = false
  clearPreviewUrl()
  try {
    // 先按 JSON 请求；图片类型后端直接返回文件流（axios 会当文本解析，需按扩展名预判）
    const filename = (row.metadata_json?.filename || '').toLowerCase()
    const isImage = /\.(png|jpe?g|gif|webp|bmp)$/.test(filename) || row.evidence_type === 'screenshot'
    if (isImage) {
      const blob: any = await api.get(`/evidence/${row.id}/preview`, { responseType: 'blob' })
      previewUrl.value = window.URL.createObjectURL(new Blob([blob]))
      previewKind.value = 'image'
    } else {
      const res: any = await api.get(`/evidence/${row.id}/preview`)
      const d = res.data || {}
      if (d.kind === 'text') {
        previewKind.value = 'text'
        previewContent.value = d.content || ''
        previewTruncated.value = !!d.truncated
      } else {
        previewKind.value = 'unsupported'
      }
    }
  } catch {
    previewKind.value = 'unsupported'
  } finally {
    previewLoading.value = false
  }
}

watch(previewVisible, (v) => {
  if (!v) clearPreviewUrl()
})

// ============ 预览框拖拽调整大小 ============
const previewSize = reactive({ w: 880, h: 620 })

function startResize(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startY = e.clientY
  const startW = previewSize.w
  const startH = previewSize.h
  const onMove = (ev: MouseEvent) => {
    previewSize.w = Math.min(Math.max(startW + (ev.clientX - startX), 480), window.innerWidth - 60)
    previewSize.h = Math.min(Math.max(startH + (ev.clientY - startY), 240), window.innerHeight - 140)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ============ 工具 ============
function summaryText(summary: any): string {
  if (!summary) return '-'
  if (typeof summary === 'string') return summary
  try {
    return JSON.stringify(summary)
  } catch {
    return '-'
  }
}

/** 检测阶段Tab的引擎列：显示实际执行的引擎名（如 AppShark），而非子任务类型 static/dynamic */
function engineNames(subTask: any): string {
  const engines = subTask.result_summary?.engines
  if (Array.isArray(engines) && engines.length) {
    return engines.map((e: any) => e.engine || e.type).join('、')
  }
  return subTask.engine_type || '-'
}

// 同组件内切换任务 id 时重新加载
watch(taskId, (id, old) => {
  if (id && id !== old) loadAll()
})

onMounted(loadAll)
</script>

<style scoped>
.mb16 { margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.info-card { height: 100%; }
.mono { font-family: monospace; font-size: 12px; }
.break-all { word-break: break-all; }
.error-text { color: var(--el-color-danger); }
.failed-reason {
  margin-top: 8px;
  padding: 8px 12px;
  background: #FEF0F0;
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-color-danger);
}
.failed-label { font-weight: 600; }
.clickable-table :deep(.el-table__row) { cursor: pointer; }
/* 事件流 SDK 关联 */
.sdk-option-count { float: right; font-size: 12px; color: var(--el-text-color-secondary); }
.sdk-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-wrap: wrap;
}
.sdk-summary-tag { cursor: pointer; }
.sdk-summary-tag:hover { opacity: 0.8; }
.sdk-summary-more { font-size: 12px; }
.sdk-link-tag { cursor: pointer; max-width: 100%; }
.sdk-link-tag:hover { opacity: 0.8; }
.no-sdk { color: var(--el-text-color-placeholder); }
.perm-sub { font-size: 12px; color: var(--el-text-color-secondary); }
/* 事件流列设置 */
.col-setting-btn { margin-left: auto; }
.col-setting-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.col-setting :deep(.el-checkbox-group) { display: flex; flex-direction: column; }
.col-setting :deep(.el-checkbox) { height: 28px; }
/* 事件高亮（证据跳转定位） */
:deep(.el-table .evidence-highlight td) {
  background: #FFF7E6 !important;
}
/* SDK识别 */
.score-cell { display: flex; align-items: center; gap: 8px; }
.score-cell .el-progress { flex: 1; }
.score-num { font-weight: 600; font-variant-numeric: tabular-nums; }
.cluster-tip { margin-bottom: 12px; }
.linked-name { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
/* SDK详情证据汇总卡片 */
.ev-stat-cards {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.ev-stat-card {
  min-width: 90px;
  padding: 10px 16px;
  background: #F7F8FA;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  text-align: center;
}
.ev-stat-num {
  font-size: 20px;
  font-weight: 600;
  color: #2B5AED;
  font-variant-numeric: tabular-nums;
}
.ev-stat-type { margin-top: 2px; font-size: 12px; color: var(--el-text-color-secondary); }
.ev-jump-tip { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
/* 抽屉 SDK 卡片 */
.sdk-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #FAFBFC;
  cursor: pointer;
  transition: all 0.15s;
}
.sdk-card:hover { border-color: #2B5AED; background: #F5F8FF; }
.sdk-card-main { flex: 1; min-width: 0; }
.sdk-card-name {
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sdk-card-vendor {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.sdk-card-tags { display: flex; gap: 6px; flex-shrink: 0; }
.sdk-card-arrow { color: var(--el-text-color-placeholder); }
/* 证据预览 */
.preview-body { position: relative; min-height: 200px; }
.preview-image {
  display: block;
  max-width: 100%;
  max-height: 100%;
  margin: 0 auto;
  border-radius: 6px;
  object-fit: contain;
}
.preview-body .preview-text {
  height: 100%;
  max-height: none;
  box-sizing: border-box;
}
.preview-truncated {
  position: absolute;
  bottom: 8px;
  left: 12px;
  font-size: 12px;
  color: var(--el-color-warning);
  background: #FFFBEB;
  padding: 2px 8px;
  border-radius: 4px;
}
.resize-grip {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: nwse-resize;
  color: var(--el-text-color-placeholder);
  border-radius: 4px;
}
.resize-grip:hover { color: #2B5AED; background: #EEF3FE; }
.json-title {
  margin: 16px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.json-pre {
  background: #F7F8FA;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.6;
  max-height: 360px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
