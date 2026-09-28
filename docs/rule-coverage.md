# 规则覆盖度

状态只取四个取值（设计文档 §1.6）：`已验证` / `待验证` / `静态不可表达` / `未覆盖`。
**不得**出现「理论支持」「预计覆盖」这类冒充已覆盖的写法。

MASWE 编号一律标 `待核实`（本环境无法访问官方站点），详见设计文档 §9。

> 完整的「数据/安全类别 · 流向 · 规则 · Observation · Finding · MASWE · MASTG」矩阵
> 见实施计划 Task 8，尚未产出。本文件先记录**已经在真实样本上暴露的能力缺口与缺陷**。

## G1：非 AppShark 观察不带 `data_category`，跨引擎 join 无法成立

**状态：已验证（2026-09-28 修复）**

原问题：`Rule Semantic Registry` 按 `payload.rule` 查表，而只有 AppShark 的事件带这个
字段（Androguard 的分类在 `payload.category`）。Androguard / MobSF 的观察归一化后
`data_category` 恒为 NULL，导致设计 §8 置信度阶梯的最高一档「＋另一引擎独立印证 →
high」不可达，设计 §7.1 的示例增强规则永不命中。

修法：注册表增加 Androguard 的敏感权限分组映射（键取自 runner 的
`SENSITIVE_PERMISSIONS`，测试断言两者集合完全一致）。归一化时按 `engine_type` 分派，
不按 `observation_type` —— 否则「同一种观察类型来自不同引擎」会借用别人的映射。

验证（task 862，app_version 11 门户测试 3.4.24，AppShark + Androguard 双引擎）：

```text
PRIVACY_LOCATION_NETWORK   high        ← 跨引擎印证达成
  证据：androguard/fact.sensitive_permission/location  × 2
        appshark/dataflow.privacy/location             × 30
        appshark/security.sensitive_api/location       × 319
PRIVACY_DEVICE_INFORMATION_{FILE,LOG,NETWORK}  medium_high
        ← 只有同引擎证据，未升到 high：阶梯确实按证据独立性判别，不是一律拉满
```

各类目映射的验证状态：

| Androguard 分组 | data_category | 状态 |
|---|---|---|
| LOCATION / PHONE_STATE / CONTACTS / CAMERA / MICROPHONE / STORAGE | location / phone / contacts / camera / microphone / files | 已验证（真实样本出现且类目正确区分） |
| SMS | sms | 待验证（runner 有该分组，现有样本未出现 READ_SMS） |

## G2：同一个概念在两家 Provider 下是两个类目（相机/麦克风 vs media）

**状态：已验证（2026-09-28 拆分）**

原问题：AppShark 的 `CameraMic_APICall` 一条规则同时覆盖相机与麦克风，注册表把它标为
`media`；而设计 §4.3 的枚举里**没有 `media`**，只有 `camera` 与 `microphone`。
Androguard 能区分，映射成 `camera` / `microphone` —— 同一个 App 的相机使用，两侧
落在不同类目，永远 join 不上。

先取证据再决定怎么拆。该规则的 4 个 sink 在真实样本上的命中分布
（app_version 11，累计 39 条）：

```text
android.hardware.Camera: open                    27   → 开相机，无歧义
android.media.AudioRecord: startRecording         7
android.media.MediaRecorder: setAudioSource       3
android.media.MediaRecorder: setVideoSource       2
```

后 12 条**不能确证**用了摄像头或麦克风：`MediaRecorder` 的音源/视频源是通配参数
（可传 Surface 录屏、REMOTE_SUBMIX 录系统声），`AudioRecord` 的音源在构造时决定。
按设计 §4.2「观测命名不得扩大」，把它们算作 camera/microphone 就是拿结论掩盖引擎
实际的证据强度。

处置：按 API 拆成两条，**能确证的不与不能确证的混在一个桶里**：

| 规则 | sink | data_category |
|---|---|---|
| `Camera_APICall`（`api_camera.json`） | `Camera: open` | `camera` |
| `Media_APICall`（`api_media.json`） | `MediaRecorder: setAudioSource/setVideoSource`、`AudioRecord: startRecording` | `media`（设计 §4.3 已补入该取值） |

验证（真实样本对拍）：

```text
app_version 11  拆分前 CameraMic_APICall 39 条
                拆分后 Camera_APICall(camera) 27 + Media_APICall(media) 12 = 39   ← 无覆盖损失
                结论数 8 条，与拆分前逐条一致
app_version 12  命中规则仍为 12 条，仅 CameraMic_APICall → Camera_APICall 这一次
                有意的改名，无规则消失（回归基线要求的比对）
```

**遗留的取舍（已接受）**：`media` 侧的 12 条观察仍无法与 Androguard 的
camera/microphone join。要消掉这个分裂，只能把不能确证的也算成 camera/microphone，
那是拿结论掩盖证据强度，不做。

**退役规则的语义如何复现**：`CameraMic_APICall` 已不存在于规则目录，但 task 553 回归
基线与库中既有观察都记着它。注册表保留 `RETIRED_REGISTRY` 别名（值为拆分前的
`media`），否则重新归一化历史产物会得到与当时不同的语义，历史结论不可复现。

## G3：v1 字面匹配规则产出跨类目错误结论

**状态：已验证并停用（2026-09-28）**

`PRIVACY_CONTACTS_NETWORK` 的第 2 个条件是 `payload.rule contains _NetworkTransfer`，
它把**设备标识**与**位置信息**的网络流一并匹配进来。

实测 task 810（app_version 11，无任何通讯录数据流）该规则产出的结论由
「1 条通讯录权限 + 18 条 device_information 流 + 30 条 location 流」组成，即在一个
没有通讯录数据流的样本上断言「通讯录信息存在潜在网络传输路径」。

**设计 §10 关于这条规则的前提是错的**：那里写的是「其条件不可能成立」。真实数据
证明条件成立，只是匹配到了错误的类目 —— 它不是惰性规则，是错误规则。（该结论曾
被「关联层产出 0 条结论」掩盖：早期任务只有 AppShark、没有 Androguard 的通讯录
权限观察，规则确实不命中；一旦双引擎同跑就会命中。）

处置：`status=disabled`，不再产出新结论；历史 Finding #45 / #53 保留不动
（其 `correlation_rule_id=147` 仍指向该规则行，删行会让结论失去依据）。
通讯录的「读取→外传」在当前引擎能力下不可静态表达（Task 1 结论），这条规则改不对。
