# API接口设计

## 1. 设计原则

- REST/JSON，长任务异步提交+查询
- 写操作带 request_id 实现幂等
- 文件上传分片或预签名URL
- 任务进度 WebSocket/SSE 推送
- 统一响应格式

## 2. 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_xxx"
}
```

错误码:
- 0: 成功
- 40001: 参数错误
- 40101: 未认证
- 40301: 无权限
- 40401: 资源不存在
- 40901: 资源冲突
- 50001: 服务器错误

## 3. 认证接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/auth/login | POST | 登录获取JWT |
| /api/v1/auth/refresh | POST | 刷新Token |
| /api/v1/auth/me | GET | 获取当前用户 |
| /api/v1/auth/logout | POST | 登出 |

### POST /api/v1/auth/login
```json
// Request
{ "username": "admin", "password": "admin123" }
// Response
{
  "code": 0, "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": { "id": 1, "username": "admin", "role": "platform_admin", "full_name": "管理员" }
  }
}
```

## 4. 项目管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/projects | POST | 新建项目 |
| /api/v1/projects | GET | 项目列表(分页) |
| /api/v1/projects/{id} | GET | 项目详情 |
| /api/v1/projects/{id} | PUT | 更新项目 |
| /api/v1/projects/{id} | DELETE | 删除项目 |
| /api/v1/projects/{id}/members | GET | 项目成员 |
| /api/v1/projects/{id}/members | POST | 添加成员 |
| /api/v1/projects/{id}/members/{userId} | DELETE | 移除成员 |
| /api/v1/projects/{id}/dashboard | GET | 项目看板 |

## 5. App资产管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/apps | POST | 新建App |
| /api/v1/apps | GET | App列表 |
| /api/v1/apps/{id} | GET | App详情 |
| /api/v1/apps/{id} | PUT | 更新App |
| /api/v1/apps/{id} | DELETE | 删除App |
| /api/v1/apps/{id}/versions | GET | 版本列表 |
| /api/v1/apps/{id}/versions/upload | POST | 上传APK创建版本 |
| /api/v1/apps/{id}/versions/{vid} | GET | 版本详情 |
| /api/v1/apps/{id}/versions/compare | GET | 版本对比 |
| /api/v1/apps/{id}/privacy-policies | GET | 隐私政策列表 |
| /api/v1/apps/{id}/privacy-policies | POST | 上传隐私政策 |
| /api/v1/apps/{id}/privacy-policies/{pid} | GET | 隐私政策详情 |
| /api/v1/apps/{id}/privacy-policies/{pid}/parse | POST | 触发政策解析 |
| /api/v1/apps/{id}/sdks | GET | App关联SDK列表 |

### POST /api/v1/apps/{id}/versions/upload
```
Content-Type: multipart/form-data
file: <APK文件>
version_name: 1.0.0
version_code: 1
channel: official
upload_notes: 首次上传
```
```json
// Response
{
  "code": 0, "data": {
    "id": 1, "version_name": "1.0.0", "version_code": 1,
    "sha256": "abc123...", "file_size": 52428800,
    "package_name": "com.example.app",
    "signature_info": { "subject": "CN=Example", "algorithm": "RSA" }
  }
}
```

## 6. 检测任务接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/tasks | POST | 创建检测任务 |
| /api/v1/tasks | GET | 任务列表(分页+过滤) |
| /api/v1/tasks/{id} | GET | 任务详情 |
| /api/v1/tasks/{id}/submit | POST | 提交任务(冻结配置) |
| /api/v1/tasks/{id}/cancel | POST | 取消任务 |
| /api/v1/tasks/{id}/retry | POST | 重试任务 |
| /api/v1/tasks/{id}/events | GET | 查询标准事件 |
| /api/v1/tasks/{id}/scenarios | GET | 任务场景列表 |
| /api/v1/tasks/{id}/scenarios/{sid} | PUT | 更新场景状态(动态操作) |
| /api/v1/tasks/{id}/progress | GET | 任务进度(SSE) |
| /api/v1/tasks/{id}/log | GET | 任务日志 |
| /api/v1/tasks/{id}/findings | GET | 任务发现的问题 |

### POST /api/v1/tasks
```json
{
  "app_version_id": 1,
  "detection_type": "full",
  "rule_pack_version": "1.0",
  "config": {
    "dynamic_scenarios": ["first_launch", "rejected", "consented"],
    "device_requirements": { "android_version": "13", "root": true },
    "timeout_minutes": 30,
    "retry_policy": { "static_retries": 2, "dynamic_retry": "manual" }
  }
}
```

### GET /api/v1/tasks/{id}/events
Query: event_type, scenario_id, data_type, page, page_size
```json
{
  "code": 0, "data": {
    "items": [{
      "event_uid": "evt_01J...",
      "task_id": 1, "scenario_id": 2,
      "event_type": "sensitive_api_call",
      "timestamp": "2026-07-31T15:20:12.318+08:00",
      "consent_status": "NOT_AGREED",
      "data_type": "ANDROID_ID",
      "api": "android.provider.Settings$Secure.getString",
      "caller": "com.vendor.analytics.DeviceUtil.getId",
      "sdk": { "id": 5, "name": "某统计SDK", "vendor": "Vendor" },
      "trace_id": "trace_abc",
      "evidence_refs": ["stack_001", "screen_021"]
    }],
    "total": 42, "page": 1, "page_size": 20
  }
}
```

## 7. 问题(Finding)接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/findings | GET | 问题列表(分页+多维过滤) |
| /api/v1/findings/{id} | GET | 问题详情 |
| /api/v1/findings/{id} | PUT | 更新问题(状态/分派) |
| /api/v1/findings/{id}/evidence | GET | 问题关联证据 |
| /api/v1/findings/{id}/events | GET | 问题关联事件 |
| /api/v1/findings/{id}/remediations | GET | 整改记录 |
| /api/v1/findings/{id}/remediations | POST | 提交整改 |
| /api/v1/findings/{id}/assign | POST | 分派问题 |
| /api/v1/findings/{id}/close | POST | 关闭问题 |

## 8. 证据接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/tasks/{taskId}/evidence | GET | 任务证据列表 |
| /api/v1/evidence/{id} | GET | 证据详情 |
| /api/v1/evidence/{id}/download | GET | 下载证据文件 |
| /api/v1/evidence/{id}/preview | GET | 预览(截图/报文) |

## 9. 规则接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/rules | GET | 规则列表 |
| /api/v1/rules | POST | 新建规则 |
| /api/v1/rules/{id} | GET | 规则详情 |
| /api/v1/rules/{id}/versions | GET | 规则版本列表 |
| /api/v1/rules/{id}/versions | POST | 新建规则版本 |
| /api/v1/rules/{id}/versions/{vid}/publish | POST | 发布规则版本 |
| /api/v1/rules/{id}/versions/{vid}/test | POST | 测试规则 |
| /api/v1/rule-packs | GET | 规则包列表 |

## 10. SDK知识库接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/sdks | GET | SDK列表 |
| /api/v1/sdks | POST | 新建SDK条目 |
| /api/v1/sdks/{id} | GET | SDK详情 |
| /api/v1/sdks/{id} | PUT | 更新SDK |
| /api/v1/sdks/{id}/fingerprints | GET | SDK指纹列表 |
| /api/v1/sdks/{id}/fingerprints | POST | 添加指纹 |

## 11. 报告接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/reports/{taskId}/generate | POST | 生成报告 |
| /api/v1/reports/{taskId} | GET | 获取报告状态 |
| /api/v1/reports/{taskId}/download | GET | 下载报告 |

## 12. 复测接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/retests | POST | 创建复测 |
| /api/v1/retests/{id} | GET | 复测详情 |

## 13. Agent通信接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /agent/v1/register | POST | Agent注册 |
| /agent/v1/heartbeat | POST | 心跳上报 |
| /agent/v1/tasks/{taskId}/claim | POST | 领取任务 |
| /agent/v1/tasks/{taskId}/progress | POST | 上报进度 |
| /agent/v1/tasks/{taskId}/result | POST | 上报结果 |
| /agent/v1/tasks/{taskId}/events | POST | 上报事件 |
| /agent/v1/tasks/{taskId}/evidence | POST | 上传证据文件 |
| /agent/v1/tasks/{taskId}/cancel | POST | 确认取消 |

### POST /agent/v1/heartbeat
```json
{
  "agent_id": "agt_001",
  "version": "1.0.0",
  "capabilities": ["ADB", "FRIDA", "MITMPROXY", "UIAUTOMATOR2"],
  "tools_info": { "frida": "16.0.0", "adb": "1.0.41" },
  "devices": [
    { "serial": "ABC123", "status": "IDLE", "android": "13", "brand": "Pixel", "model": "7" }
  ]
}
```

## 14. 系统管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/system/users | GET/POST | 用户管理 |
| /api/v1/system/users/{id} | GET/PUT/DELETE | 用户CRUD |
| /api/v1/system/roles | GET | 角色列表 |
| /api/v1/system/dict | GET/POST | 字典管理 |
| /api/v1/system/nodes | GET | 节点列表 |
| /api/v1/system/devices | GET | 设备列表 |
| /api/v1/system/audit-logs | GET | 审计日志 |
| /api/v1/system/dashboard | GET | 全局看板 |

## 15. WebSocket / SSE 事件

### 任务进度 SSE: GET /api/v1/tasks/{id}/progress
```json
{ "type": "progress", "stage": "RUNNING_STATIC", "percent": 45, "message": "AppShark数据流分析中" }
{ "type": "stage_change", "from": "RUNNING_STATIC", "to": "WAITING_DYNAMIC" }
{ "type": "event", "event": { "event_type": "sensitive_api_call", "data_type": "ANDROID_ID" } }
{ "type": "finding", "finding": { "severity": "HIGH", "title": "..." } }
{ "type": "completed", "task_id": 1, "status": "completed" }
```
