# Agent通信协议

## 1. 通信模型

Agent采用主动注册 + 心跳 + 长轮询模式。

```
┌─────────┐         注册/心跳/领取/上报          ┌──────────┐
│  Agent  │ ◄──────────────────────────────────► │  平台    │
│ (动态)  │    HTTP POST (JSON)                  │ (FastAPI)│
└────┬────┘                                      └──────────┘
     │
     │ ADB/Frida
     ▼
┌─────────┐
│ Android │
│  设备   │
└─────────┘
```

## 2. Agent生命周期

```
启动 → 注册 → 心跳循环 → 领取任务 → 执行 → 上报进度 → 上报结果 → 心跳循环
                                         ↓
                                    上报事件(流式)
                                    上传证据文件
```

## 3. 接口定义

### 3.1 注册
POST /agent/v1/register
```json
// Request
{
  "agent_id": "agt_001",
  "node_name": "lab-workstation-01",
  "node_type": "dynamic_agent",
  "version": "1.0.0",
  "capabilities": ["ADB", "FRIDA", "MITMPROXY", "UIAUTOMATOR2"],
  "tools_info": {
    "frida": "16.0.0",
    "adb": "1.0.41",
    "mitmproxy": "10.0.0",
    "uiautomator2": "3.0.0"
  },
  "devices": [
    {
      "serial": "ABC123",
      "brand": "Google",
      "model": "Pixel 7",
      "android_version": "13",
      "is_rooted": true,
      "is_frida_ready": true
    }
  ]
}
// Response
{ "code": 0, "data": { "agent_id": "agt_001", "registered": true, "heartbeat_interval": 15 } }
```

### 3.2 心跳
POST /agent/v1/heartbeat
```json
// Request
{
  "agent_id": "agt_001",
  "timestamp": "2026-07-31T15:20:00+08:00",
  "status": "idle",  // idle/busy/error
  "current_task_id": null,
  "devices": [
    { "serial": "ABC123", "status": "IDLE", "temperature": 35, "battery": 80 }
  ],
  "resources": { "cpu": 12.5, "memory": 45.2, "disk": 60.0 }
}
// Response
{
  "code": 0,
  "data": {
    "pending_tasks": ["task_001", "task_002"],
    "cancel_tasks": [],
    "commands": []
  }
}
```

### 3.3 领取任务
POST /agent/v1/tasks/{taskId}/claim
```json
// Response
{
  "code": 0,
  "data": {
    "task_id": "task_001",
    "sub_tasks": [
      {
        "sub_task_id": "st_001",
        "engine_type": "frida_agent",
        "stage": "execute",
        "config": {
          "apk_download_url": "/api/v1/files/apk/task_001",
          "package_name": "com.example.app",
          "scenarios": [
            {
              "scenario_id": 1,
              "scenario_type": "first_launch",
              "consent_status": "NOT_PRESENTED",
              "duration_seconds": 30
            },
            {
              "scenario_id": 2,
              "scenario_type": "rejected",
              "consent_status": "REJECTED"
            },
            {
              "scenario_id": 3,
              "scenario_type": "consented",
              "consent_status": "CONSENTED"
            }
          ],
          "hook_scripts": ["device_id", "location", "contacts", "network"],
          "frida_script_version": "1.0.0",
          "capture_traffic": true,
          "proxy_port": 8888,
          "screenshot_enabled": true,
          "recording_enabled": false
        }
      }
    ],
    "upload_credentials": {
      "evidence_upload_url": "/agent/v1/tasks/task_001/evidence",
      "expires_at": "2026-07-31T18:00:00+08:00"
    }
  }
}
```

### 3.4 上报进度
POST /agent/v1/tasks/{taskId}/progress
```json
{
  "agent_id": "agt_001",
  "sub_task_id": "st_001",
  "stage": "RUNNING_DYNAMIC",
  "percent": 45,
  "message": "场景S2(拒绝)采集中",
  "scenario_id": 2,
  "timestamp": "2026-07-31T15:22:00+08:00"
}
```

### 3.5 上报事件 (流式)
POST /agent/v1/tasks/{taskId}/events
```json
{
  "agent_id": "agt_001",
  "events": [
    {
      "event_uid": "evt_01J...",
      "scenario_id": 1,
      "event_type": "consent_state_change",
      "timestamp": "2026-07-31T15:20:00+08:00",
      "consent_status": "NOT_PRESENTED",
      "event_data": { "page": "splash", "dialog_shown": true }
    },
    {
      "event_uid": "evt_01J...002",
      "scenario_id": 1,
      "event_type": "sensitive_api_call",
      "timestamp": "2026-07-31T15:20:05.318+08:00",
      "consent_status": "NOT_PRESENTED",
      "data_type": "ANDROID_ID",
      "api": "android.provider.Settings$Secure.getString",
      "caller": "com.vendor.analytics.DeviceUtil.getId",
      "trace_id": "trace_abc",
      "value_fingerprint": "hmac_sha256:xxxx",
      "event_data": {
        "call_stack": [
          "com.vendor.analytics.DeviceUtil.getId",
          "com.vendor.analytics.SDK.init",
          "com.example.app.App.onCreate"
        ],
        "args_summary": "content://settings/secure, android_id",
        "return_summary": "a1b2c3d4e5f6..."
      }
    },
    {
      "event_uid": "evt_01J...003",
      "scenario_id": 1,
      "event_type": "network_request",
      "timestamp": "2026-07-31T15:20:06.000+08:00",
      "consent_status": "NOT_PRESENTED",
      "event_data": {
        "method": "POST",
        "url": "https://api.vendor.example/v1/report",
        "domain": "api.vendor.example",
        "path": "/v1/report",
        "request_headers": { "Content-Type": "application/json" },
        "request_body_preview": "{\"id\":\"a1b2c3d4e5f6...\"}",
        "response_status": 200,
        "is_sensitive": true,
        "matched_sensitive": ["device_id"]
      }
    }
  ]
}
```

### 3.6 上传证据文件
POST /agent/v1/tasks/{taskId}/evidence
```
Content-Type: multipart/form-data
file: <screenshot.png / stack_trace.json / traffic.pcap / logcat.txt>
evidence_type: screenshot / api_call_stack / traffic_capture / log_file
scenario_id: 1
metadata: {"page": "splash", "timestamp": "2026-07-31T15:20:05"}
```
```json
// Response
{
  "code": 0,
  "data": {
    "evidence_id": 42,
    "evidence_uid": "evi_01J...",
    "artifact_path": "/data/evidence/task_001/screenshot/evi_01J....png",
    "artifact_hash": "sha256:abc123..."
  }
}
```

### 3.7 上报最终结果
POST /agent/v1/tasks/{taskId}/result
```json
{
  "agent_id": "agt_001",
  "task_id": "task_001",
  "status": "completed",  // completed/failed
  "summary": {
    "scenarios_executed": 3,
    "events_collected": 42,
    "evidence_uploaded": 15,
    "errors": []
  },
  "error_message": null
}
```

## 4. 平台→Agent指令 (通过心跳返回)

```json
{
  "commands": [
    { "type": "cancel_task", "task_id": "task_001" },
    { "type": "update_config", "config": {} },
    { "type": "device_reset", "serial": "ABC123" }
  ]
}
```

## 5. 安全机制

- Agent携带短期令牌(agent_token)，每次请求校验
- 令牌过期后通过refresh接口续期
- Agent只能访问分配给它的任务
- 证据上传URL带过期时间
- APK下载URL带过期时间
