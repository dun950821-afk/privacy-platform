# 规则覆盖度矩阵

**MASWE 版本固定 `1.0.0`。所有 MASWE / MASTG 编号一律标 `待核实`**——本环境无法访问
MASWE 官方站点与相关仓库（网络策略拦截，已实测），任何具体编号在核对之前都不得以
确定语气引用（设计文档 §9.2）。此处包括此前已有的 `MASWE-0001`。

状态只取四个取值（设计文档 §1.6）：

| 取值 | 含义 |
|---|---|
| `已验证` | 已有真实样本证明成立 |
| `待验证` | 尚无真实样本，未验证 |
| `静态不可表达` | 已证明当前引擎规则语言无法表达（能力边界） |
| `未覆盖` | 枚举/能力上存在，但当前没有任何规则产出 |

**「真实命中」列是本矩阵的证据列。** 覆盖度矩阵必须区分「枚举存在」与「引擎可产出」
（设计 §4.3），而区分二者的唯一依据是真实样本上的命中记录，不是规则文件写了什么。

样本口径：`11` = 门户测试 3.4.24、`12` = 营口银行 4.5.1、`13` = 营行企业银行 1.4.2。
`8`（360 加固）**不计入检测证据**——该样本 AppShark 只产出 16 个事件（12 号样本 139、
11 号样本 1259），属分析退化，只能用于引擎失败诊断（实施计划 Task 9 Step 5）。

---

## 1. 隐私数据流 → 直接结论

规则命中即证明「该类数据存在通往该流向的路径」，观察本身已是完整结论，
不经关联器直接产出 Finding（设计 §3.1）。

| 类别 | 流向 | AppShark Rule | Observation | Finding | 真实命中（app_version(条数)） | 状态 |
|---|---|---|---|---|---|---|
| device_information | file | `DeviceId_FileWrite` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_FILE` | 11(132)、12(18) | 已验证 |
| device_information | log | `DeviceId_Log` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_LOG` | 11(118)、12(117) | 已验证 |
| device_information | network | `DeviceId_NetworkTransfer` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_NETWORK` | 11(109) | 已验证 |
| location | network | `Location_NetworkTransfer` | `dataflow.privacy` | `PRIVACY_LOCATION_NETWORK` | 11(179) | 已验证 |
| device_information | log | `serial_Log` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_LOG` | — | 待验证 |
| device_information | ipc | `IMEI_SendBroadcast` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_IPC` | — | 待验证 |
| clipboard | log | `Clipboard_Log` | `dataflow.privacy` | `PRIVACY_CLIPBOARD_LOG` | — | 待验证 |

> `DeviceId_Log` 与 `serial_Log` 产出**同一个结论码** `PRIVACY_DEVICE_INFORMATION_LOG`：
> 二者证明的是同一个结论（设备标识流向日志），与哪条规则命中无关——结论码由平台语义
> 字段构成、不含 Provider 规则名（设计 §3.1）。同任务内两条规则都命中时，观察会按
> 结论码合并进同一条 Finding，而不是产出两条同义结论。

## 2. 无数据类目的安全结论

安全类规则没有数据类目，但观察本身仍是完整结论——这正是「是否成结论不由类目决定」
的证据（设计 §3.4）。**这 4 条全部来自上游官方规则**（`bytedance/appshark`
commit `487fa2175c4a`，见 `backend/appshark/upstream-provenance.json`），因此其安全
论断是否成立需逐条核实，属实施计划 Task 7；本矩阵只记录**检测是否在真实样本上触发**。

| 类别 | 风险 | AppShark Rule | Observation | Finding | 真实命中 | 状态 |
|---|---|---|---|---|---|---|
| — | 路径穿越（file） | `ContentProviderPathTraversal` | `security.other` | `SECURITY_CONTENTPROVIDERPATHTRAVERSAL` | 11(3) | 待验证 |
| — | Intent 重定向（ipc） | `IntentRedirectionBabyVersion` | `security.other` | `SECURITY_INTENTREDIRECTIONBABYVERSION` | 11(6) | 待验证 |
| — | PendingIntent 可变（ipc） | `PendingIntentMutable` | `security.other` | `SECURITY_PENDINGINTENTMUTABLE` | 11(192)、12(9) | 待验证 |
| — | 解压路径穿越（file） | `unZipSlip` | `security.other` | `SECURITY_UNZIPSLIP` | 11(15)、12(9) | 待验证 |

> **为什么有命中却仍是「待验证」**：命中证明的是「规则触发了」，不是「论断成立」。
> 官方的 7 条规则在 `upstream-provenance.json` 里 `verified` 全为 `false`，而按计划
> Task 7，只有逐条核实过论断的才计入覆盖度。把「触发」写成「已验证」就是拿检测
> 覆盖度冒充安全结论的正确性——本项目此前吃过一次同类亏（设计 §1.1）。

## 3. 敏感 API 事实（只做证据增强，不产出结论）

| 类别 | AppShark Rule | Observation | Finding | 真实命中 | 状态 |
|---|---|---|---|---|---|
| device_information | `DeviceId_APICall` | `security.sensitive_api` | —（增强） | 11(426)、12(216)、13(7) | 已验证 |
| device_information | `MAC` | `security.sensitive_api` | —（增强） | 11(66)、12(63) | 待验证 |
| installed_apps | `InstalledApps_APICall` | `security.sensitive_api` | —（增强） | 11(885)、12(342) | 已验证 |
| location | `Location_APICall` | `security.sensitive_api` | —（增强） | 11(957) | 已验证 |
| network_information | `Network_APICall` | `security.sensitive_api` | —（增强） | 11(450)、12(171) | 已验证 |
| network_information | `Wifi_APICall` | `security.sensitive_api` | —（增强） | 11(171)、12(72) | 已验证 |
| sensor | `Sensor_APICall` | `security.sensitive_api` | —（增强） | 11(87)、12(63) | 已验证 |
| clipboard | `Clipboard_APICall` | `security.sensitive_api` | —（增强） | 11(18)、12(18) | 已验证 |
| camera | `Camera_APICall` | `security.sensitive_api` | —（增强） | 11(27)、12(4) | 已验证 |
| media | `Media_APICall` | `security.sensitive_api` | —（增强） | 11(12) | 已验证 |

> `MAC` 同为官方规则，论断核实同 Task 7，故标 `待验证`。

## 4. 跨引擎：Androguard 敏感权限

映射表：`backend/app/services/appshark_semantic_registry.py::ANDROGUARD_PERMISSION_CATEGORIES`
（键取自 runner 的 `SENSITIVE_PERMISSIONS`，测试断言两者集合相等）。

| Androguard 分组 | data_category | 观察类型 | 真实命中 | 状态 |
|---|---|---|---|---|
| LOCATION | location | `fact.sensitive_permission` | 11(6) | 已验证 |
| PHONE_STATE | phone | `fact.sensitive_permission` | 11(6) | 已验证 |
| STORAGE | files | `fact.sensitive_permission` | 11(6) | 已验证 |
| CONTACTS | contacts | `fact.sensitive_permission` | 11(3) | 已验证 |
| CAMERA | camera | `fact.sensitive_permission` | 11(3) | 已验证 |
| MICROPHONE | microphone | `fact.sensitive_permission` | 11(3) | 已验证 |
| SMS | sms | `fact.sensitive_permission` | — | 待验证 |

跨引擎增强已在真实样本上达成（task 862，app_version 11）：`PRIVACY_LOCATION_NETWORK`
得到 Androguard 的 location 权限（不同引擎）后置信度为 `high`，而同任务里只有同引擎
证据的 `PRIVACY_DEVICE_INFORMATION_*` 停在 `medium_high`。MobSF 的观察仍不带
`data_category`，不参与 join。

## 5. 枚举覆盖：枚举存在 ≠ 引擎可产出

设计 §4.3 的 `data_category` 枚举共 20 个取值。**有映射不等于有产出**：

| 来源 | 取值 |
|---|---|
| AppShark 可产出（8） | device_information、location、camera、media、clipboard、network_information、installed_apps、sensor |
| Androguard 可产出（7） | location、phone、files、contacts、camera、microphone、sms |
| 有真实命中（12） | 上列并集去掉 sms |
| 仅映射、无真实样本（1） | sms |
| **无任何引擎产出（7）** | advertising_identifier、account、calendar、photos、biometric、personal_information、unknown |

`sink_type` 枚举共 9 个取值，当前有产出的只有 4 个：`file`、`ipc`、`log`、`network`。
其余（`database`、`webview`、`clipboard`、`third_party_sdk`、`unknown`）无任何规则产出。

**状态：未覆盖。** 这 7 个类目与 5 个流向不是「待验证」，是当前引擎能力下根本没有规则
覆盖——两者混为一谈会让覆盖度看起来比实际高。

## 6. 能力边界：静态不可表达

| 数据类目 | 流向 | 状态 | 依据 |
|---|---|---|---|
| contacts | network | 静态不可表达 | Task 1 实验：URL 常量作 sink 零命中（APIMode 只匹配方法签名）；`ContentResolver.query` 作 source 在 LibraryOnly + InstantDefault 模型下不传播到网络 sink |
| sms | network | 静态不可表达 | 同 Task 1 结论（与 contacts 同类，共用 `ContentResolver` 调用点） |
| calllog | network | 静态不可表达 | 同上 |

**这不是覆盖缺口，是能力边界**，不能靠为每个类目写规则来解决（设计 §1.3）。
G3 记录了试图用字面值匹配绕过它所带来的后果。

---

## 已知缺口

### G1：非 AppShark 观察不带 `data_category`，跨引擎 join 无法成立

**状态：已验证（2026-09-28 修复）**

原问题：语义注册表按 `payload.rule` 查表，而只有 AppShark 的事件带这个字段
（Androguard 的分类在 `payload.category`）。修复后按 `engine_type` 分派，见 §4。

### G2：相机与音视频采集的类目归属

**状态：已验证（2026-09-28 拆分）**

原问题：`CameraMic_APICall` 一条规则同时覆盖相机与麦克风，注册表标为 `media`，而枚举
里只有 `camera` / `microphone`，与 Androguard 永远 join 不上。

先取命中分布再决定拆法——该规则的 4 个 sink 在真实样本上的分布：

```text
android.hardware.Camera: open                    27   → 开相机，无歧义
android.media.AudioRecord: startRecording         7
android.media.MediaRecorder: setAudioSource       3
android.media.MediaRecorder: setVideoSource       2
```

后 12 条**不能确证**用了摄像头或麦克风：`MediaRecorder` 的音源/视频源是通配参数
（可传 Surface 录屏、REMOTE_SUBMIX 录系统声），`AudioRecord` 的音源在构造时决定。
按设计 §4.2「命名不得扩大」，把它们算作 camera/microphone 就是拿结论掩盖引擎实际
的证据强度。

处置：拆成 `Camera_APICall`（Camera.open → camera）与 `Media_APICall`
（MediaRecorder + AudioRecord → media），`media` 补入设计 §4.3 枚举。

验证（真实样本对拍）：

```text
app_version 11  前 CameraMic_APICall 39 条
                后 Camera_APICall(camera) 27 + Media_APICall(media) 12 = 39   ← 无覆盖损失
                结论 8 条，与拆分前逐条一致
app_version 12  命中规则仍 12 条，仅一次有意的改名，无规则消失
```

**遗留取舍（已接受）**：`media` 侧的 12 条无法与 Androguard 的 camera/microphone
join。要消掉这个分裂，只能把不能确证的也算成 camera/microphone，不做。

### G3：v1 字面匹配规则产出跨类目错误结论

**状态：已验证并停用（2026-09-28）**

`PRIVACY_CONTACTS_NETWORK` 的第 2 个条件是 `payload.rule contains _NetworkTransfer`，
把设备标识与位置信息的网络流一并匹配进来。实测 task 810（app_version 11，无任何通讯录
数据流）该规则产出的结论由「1 条通讯录权限 + 18 条 device_information 流 + 30 条
location 流」组成。

**设计 §10 关于这条规则的前提是错的**：那里写「其条件不可能成立」。真实数据证明条件
成立，只是匹配到了错误的类目——它不是惰性规则，是错误规则。原先的误判来自观测面
不全：早期任务只跑 AppShark，缺 Androguard 的通讯录权限观察，规则确实不命中。
**「没命中」与「不可能命中」是两件事**，前者不足以支撑停用决策，也不足以支撑「已覆盖」。

处置：`status=disabled`；历史 Finding #45 / #53 保留不动。

---

## 数据完整性备注

| 现象 | 说明 |
|---|---|
| `EXP_ContentResolverQuery` 有 76 条观察记录，但规则目录与注册表中都不存在 | Task 1 能力实验的残留：实验规则跑过任务 565（app_version 12），按计划「结论产出后删除」已从规则目录移除。库中观察按「不得删除开发库既有真实数据」保留，其 `data_category` 为空、不参与关联。**不是漏登记**，是退役的实验数据 |
| `CameraMic_APICall` 有 239 条历史观察，规则已拆分 | 见 G2。注册表用 `RETIRED_REGISTRY` 保留其语义（media），使历史产物重新归一化时语义不变 |
| v1 关联规则 `PRIVACY_CONTACTS_NETWORK` 的 `MASWE-0001` 仍为 `待核实` | 设计 §9.2：本地无法核对官方站点，此前写入的编号同样未经核实 |
