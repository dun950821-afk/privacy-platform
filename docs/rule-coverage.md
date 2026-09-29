# 规则覆盖度矩阵

**标准编号已于 2026-09-29 逐条核实，本文件不再把编号标 `待核实`。**

原先这里写的是「本环境无法访问 MASWE 官方站点与相关仓库（网络策略拦截，已实测），
任何具体编号在核对之前都不得以确定语气引用」。**这个前提是错的**：`OWASP/maswe` 与
`OWASP/owasp-mastg` 两个仓库都能直接拉到，匿名 GitHub API 即可，不需要任何凭证。
（当年大概是在稳、beta 两个目录结构上找偏了——MASWE 的弱点在 `weaknesses/<MASVS 分类>/`，
MASTG 的隐私测试只在 `tests-beta/` 下，稳定版 `tests/` 里一条都没有。）

核实纠正了两处编号，都是这一版之前就写在库里的：

| 原值 | 问题 | 现取值 |
|---|---|---|
| `MASWE-0001` | 实为「Sensitive Data Stored Unencrypted in Private Storage」，归 **MASVS-STORAGE**，讲落盘加密；挂在通讯录外传规则上属张冠李戴 | `MASWE-0067`「Lack of Anonymization or Pseudonymisation Measures」（MASVS-PRIVACY-2） |
| `MASTG-TEST-PRIVACY-1` | **MASTG 中不存在这个编号**。MASTG 稳定版没有任何隐私测试；beta 版隐私测试编号形如 `MASTG-TEST-0206`，没有 `PRIVACY` 段的编号形式 | 删去（留空），不做替换性发明 |

十条判定规则原先**没有 `standards` 块**，本次一并补上，取值取自各条 MASWE 自己的
frontmatter（`maswe` / `masvs-v2` / `cwe`），与 OWASP 上游一致。

状态只取四个取值（设计文档 §1.6）：

| 取值 | 含义 |
|---|---|
| `已验证` | 已有真实样本证明成立 |
| `待验证` | 尚无真实样本，未验证 |
| `静态不可表达` | 已证明当前引擎规则语言无法表达（能力边界） |
| `未覆盖` | 枚举/能力上存在，但当前没有任何规则产出 |

**「真实命中」列是本矩阵的证据列。** 覆盖度矩阵必须区分「枚举存在」与「引擎可产出」
（设计 §4.3），而区分二者的唯一依据是真实样本上的命中记录，不是规则文件写了什么。

> ### ⚠️ 读这一列之前：AppShark 的结果**不可复现**（2026-09-29 实测）
>
> 同一份规则、同一个样本（app_version 11）连跑两次，结果不同：
>
> | 规则 | 第一次 | 第二次 |
> |---|---|---|
> | `DeviceId_FileWrite` | 44 | 42 |
> | `DeviceId_Log` | 41 | 40 |
> | `Location_NetworkTransfer` | 30 | 35 |
>
> **差异不只在数量，报出的调用点集合也不同**——`DeviceId_NetworkTransfer` 两次同为
> 18 条，但 position 不同。差异集中在百度 SDK 的类
> （`com.baidu.lbsapi`、`com.baidu.sec.privacy`、`com.baidu.location.b.t`）。
>
> 已排除指针分析时间预算：`adapters/appshark.py` 默认 `maxPointerAnalyzeTime=300s`，
> 实测整轮约 90s，没到预算。差异在 AppShark 自身输出里，不是归一化引入的——
> `engine_artifacts` 里两次的 `results.json` 大小就差 79KB。
>
> **因此：**
> - **「有没有命中」是稳的**（0 与几十的差别远超噪声），据此判「已验证 / 未命中」成立；
> - **「命中几条」不稳**，下表括号里的数字是**某一次运行**的记录，不是该规则的性质，
>   不得当作可复现的事实引用，更不得用来证明两次改动等价；
> - 要证明「改动不降覆盖」，依据只能是**规则文件的划分关系**（可 diff 验证），
>   不能是两次运行的数字对拍。
>
> 未查清成因。若要定位，下一步应在同一 APK 上直接跑 AppShark CLI（绕开平台管线）
> 复现两次，再看是否与 JVM 并发或切片顺序有关。

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
| device_information | **database** | `DeviceId_Database` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_DATABASE` | 12(3) | 已验证 |
| device_information | **webview** | `DeviceId_WebView` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_WEBVIEW` | 11(10) | 已验证 |
| device_information | **clipboard** | `DeviceId_Clipboard` | `dataflow.privacy` | `PRIVACY_DEVICE_INFORMATION_CLIPBOARD` | — | 未命中 |
| advertising_identifier | file | `AdvertisingId_FileWrite` | `dataflow.privacy` | `PRIVACY_ADVERTISING_IDENTIFIER_FILE` | — | 未命中 |
| advertising_identifier | log | `AdvertisingId_Log` | `dataflow.privacy` | `PRIVACY_ADVERTISING_IDENTIFIER_LOG` | — | 未命中 |
| advertising_identifier | network | `AdvertisingId_NetworkTransfer` | `dataflow.privacy` | `PRIVACY_ADVERTISING_IDENTIFIER_NETWORK` | — | 未命中 |
| advertising_identifier | database | `AdvertisingId_Database` | `dataflow.privacy` | `PRIVACY_ADVERTISING_IDENTIFIER_DATABASE` | — | 未命中 |
| advertising_identifier | webview | `AdvertisingId_WebView` | `dataflow.privacy` | `PRIVACY_ADVERTISING_IDENTIFIER_WEBVIEW` | — | 未命中 |
| advertising_identifier | clipboard | `AdvertisingId_Clipboard` | `dataflow.privacy` | `PRIVACY_ADVERTISING_IDENTIFIER_CLIPBOARD` | — | 未命中 |

> 加粗的三个流向与六条 `AdvertisingId_*` 规则是 2026-09-29 加的，详见下方说明。
> 表内括号数字是**某一次运行**的记录，不可复现，读法见文首的警示框。

> `DeviceId_Log` 与 `serial_Log` 产出**同一个结论码** `PRIVACY_DEVICE_INFORMATION_LOG`：
> 二者证明的是同一个结论（设备标识流向日志），与哪条规则命中无关——结论码由平台语义
> 字段构成、不含 Provider 规则名（设计 §3.1）。同任务内两条规则都命中时，观察会按
> 结论码合并进同一条 Finding，而不是产出两条同义结论。

### 1.1 2026-09-29 新增

**三个新流向（database / webview / clipboard）**——此前是零产出，不是待验证。
`DeviceId_Database` 与 `DeviceId_WebView` 在真实样本上命中并产出了新结论；
`DeviceId_Clipboard` 两个样本都没命中，标「未命中」而非「已验证」。

**广告标识符与设备标识分家（六条 `AdvertisingId_*`）**。原先 `device_id_to_*` 六条
规则的 source 里混着 `getAdvertisingIdInfo` / `getOAID`，于是 OAID 流向网络会被报成
「设备标识外传」——按平台自己的枚举 OAID 属于 `advertising_identifier`，这是错误归因，
与 `DeviceId_APICall` 那处同源（L2 侧已先修），只是更深一层：用户看到的是结论而非证据。

修法是**等价替换，不是新增能力**：六条 device 规则各移除那两个 source，新增六条
镜像规则（sink 集合逐字节复制自对应 device 规则，source 只有那两个广告标识符方法）。

**这次无法用运行结果证明等价**——原因见文首警示框：AppShark 结果不可复现，拆分前后的
数字差异（FileWrite 42/44、Log 40/41）落在同规则两次运行自身的噪声带里。等价性的依据
只能是规则文件的划分关系（可 diff 验证），不依赖运行。六条镜像规则在两个样本上均
0 命中，标「未命中」。

**camile 规则包并入**：`bytedance/appshark` tag `v0.1.2` 的 `config/rules/camile.json`
（8 条规则 52 个 sink，由 `zhengjim/camille` 的 `script.js` 生成；**`main` 分支上没有这个
文件**，只有 tag 里有）。**没有按上游分组原样引入**：上游「获取电话相关信息」把设备标识
与基站信息装在同一条规则里、「获取系统信息」把 WiFi MAC 与剪贴板装在一起，照搬会重演
OAID 那种错误归类。只取 sink 签名，按平台类目重新分组，落成四条新规则
（`Bluetooth_APICall`、`Cell_APICall`、`Carrier_APICall`、`PermissionRequest_APICall`）
与四处既有规则的扩充。四条新规则在两个样本上均 0 命中，标「未命中」。

## 2. 无数据类目的安全结论

安全类规则没有数据类目，但观察本身仍是完整结论——这正是「是否成结论不由类目决定」
的证据（设计 §3.4）。**这 4 条全部来自上游官方规则**（`bytedance/appshark`
commit `487fa2175c4a`）。

官方 7 条规则的逐条核实已于 2026-09-28 完成（Task 7）：沿规则报告的方法签名定位到
**真实 APK 字节码**，确认所声称的问题是否真实存在。「规则触发过」不构成已验证——
`ContentProviderPathTraversal` 的命中经核实为误报，正是这条原则的反例。

**这四条规则已于 2026-09-28 降为 `supporting_evidence`**：它们的论断是「存在某个漏洞」，
而污点分析只证明了「外部输入流到了 sink」（见 `appshark-rule-capability.md` 能力边界 2、
`docs/rule-coverage.md` 上文的说明）。降级依据是**论断类型**，不是「来源是官方」——
同为官方规则的 `IMEI_SendBroadcast` 与 `serial_Log` 声称的只是「存在 source→sink 路径」，
命中即论断，仍是 `direct_finding`。

| 风险 | AppShark Rule | 真实命中 | 核实取样 | 核实结论 | Finding | 状态 |
|---|---|---|---|---|---|---|
| 路径穿越（file） | `ContentProviderPathTraversal` | 11(3) | 1/1 | **误报**：Uri→File 经 `FileProvider$a` 接口完成，其唯一实现 `FileProvider$b.a(Uri)` 会 `getCanonicalFile()` 并做包含校验（`startsWith(root)`，否则抛 `SecurityException("Resolved path jumped beyond configured root")`），`../` 会被拒绝。规则看不穿接口调用，只见到 Uri 流入 `open` | —（只作证据） | 待验证 |
| Intent 重定向（ipc） | `IntentRedirectionBabyVersion` | 11(6) | 1/2 | 真阳性：`getIntent().getExtras().getParcelable("resolution")` 直接 `startActivityForResult`，无校验 | —（只作证据） | 已验证 |
| PendingIntent 可变（ipc） | `PendingIntentMutable` | 11(192)、12(9) | 1/44 | 真阳性：`PendingIntent.getBroadcast(ctx, 0, intent, 0)`，flags=0 未带 `FLAG_IMMUTABLE`，且交给了 `SmsManager.sendTextMessage` | —（只作证据） | 已验证 |
| 解压路径穿越（file） | `unZipSlip` | 11(15)、12(9) | 2/5 | 真阳性 + 1 处误报：`ZipUtil.unzip` 直接以 `destDir + separator + entry.getName()` 作输出路径，无规范化 → 真阳性；`WXFileUtils.extractSo` 只取条目名最后一段 → 误报 | —（只作证据） | 已验证 |

> **降级的代价，必须明说**：这四类弱点**不再产出任何结论**——v2 DSL 的 `action: create`
> 尚未实现，`supporting_evidence` 目前没有规则能把它提升成结论。这是刻意的取舍：宁可
> 不出结论，也不要出一个把误报当真、把真阳性说得比证据更强（`SECURITY_UNZIPSLIP` 看上去
> 像"确认存在解压路径穿越"，而引擎只证明了"存在数据流"）的结论。
> 恢复它们的可见性需要先实现组合推导规则（设计 §7.2），届时可要求「引擎判定 + 人工核实」
> 两个条件同时满足才成结论。

**核实取样**列记录的是「命中的多个调用点中实际核实了几个」。未核实的调用点不得当作
已核实——把 2/5 说成「该规则已验证」而不写取样覆盖，就是本文件开头禁止的那种冒充。
完整证据（方法签名、字节码事实、可利用性保留意见）记在
`backend/appshark/upstream-provenance.json` 的 `verification_note`。

> `ContentProviderPathTraversal` 保持 `待验证`：它确实触发，但已核实的命中不成立，
> 因此**该弱点类目的覆盖没有被证明**。`verified` 为 false 的规则不计入覆盖度。

## 3. 敏感 API 事实（只做证据增强，不产出结论）

| 类别 | AppShark Rule | Observation | Finding | 真实命中 | 状态 |
|---|---|---|---|---|---|
| device_information | `DeviceId_APICall` | `security.sensitive_api` | —（增强） | 11(426)、12(216)、13(7) | 已验证 |
| device_information | `MAC` | `security.sensitive_api` | —（增强） | 11(66)、12(63) | 已验证 |
| installed_apps | `InstalledApps_APICall` | `security.sensitive_api` | —（增强） | 11(885)、12(342) | 已验证 |
| location | `Location_APICall` | `security.sensitive_api` | —（增强） | 11(957) | 已验证 |
| network_information | `Network_APICall` | `security.sensitive_api` | —（增强） | 11(450)、12(171) | 已验证 |
| network_information | `Wifi_APICall` | `security.sensitive_api` | —（增强） | 11(171)、12(72) | 已验证 |
| sensor | `Sensor_APICall` | `security.sensitive_api` | —（增强） | 11(87)、12(63) | 已验证 |
| clipboard | `Clipboard_APICall` | `security.sensitive_api` | —（增强） | 11(18)、12(18) | 已验证 |
| camera | `Camera_APICall` | `security.sensitive_api` | —（增强） | 11(27)、12(4) | 已验证 |
| media | `Media_APICall` | `security.sensitive_api` | —（增强） | 11(12) | 已验证 |
| advertising_identifier | `AdvertisingId_APICall` | `security.sensitive_api` | —（增强） | — | 未命中 |
| account | `Account_APICall` | `security.sensitive_api` | —（增强） | — | 未命中 |
| bluetooth | `Bluetooth_APICall` | `security.sensitive_api` | —（增强） | — | 未命中 |
| cell | `Cell_APICall` | `security.sensitive_api` | —（增强） | — | 未命中 |
| network_information | `Carrier_APICall` | `security.sensitive_api` | —（增强） | — | 未命中 |
| （无类目） | `PermissionRequest_APICall` | `security.sensitive_api` | —（增强） | — | 未命中 |
| photos | `Photos_APICall` | `security.sensitive_api` | —（增强） | 11(3) | 已验证 |

> `MAC` 同为官方规则，其核实见 §2：它声称的只是「调用了取 MAC 地址的 API」，命中即
> 成立——已核实 `WifiInfo.getMacAddress()` 与 `NetworkInterface.getHardwareAddress()` 两处。
>
> 2026-09-29 新增的六条（含从 `DeviceId_APICall` 拆出的 `AdvertisingId_APICall`）在两个
> 样本上均 0 命中。**样本已用尽**：可分析的只有 11/12/13 三个（8 是 360 加固、分析退化），
> 所以「未命中」不是「多跑几次就能消掉」的状态，要拿到命中证据必须新增 APK。
>
> `PermissionRequest_APICall` 的 `data_category` 有意留空——它记录的是「发起过运行时权限
> 申请」这个事实，不是「采集了某类数据」。空类目意味着它不参与任何 join，只作证据。

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

`data_category` 枚举共 **22** 个取值（原 20 个，2026-09-29 增加 `bluetooth`、`cell`）。
**有规则映射不等于有产出**：

| 来源 | 取值 |
|---|---|
| AppShark 有规则（13） | device_information、location、camera、media、clipboard、network_information、installed_apps、sensor、advertising_identifier、account、bluetooth、cell、photos |
| Androguard 有映射（7） | location、phone、files、contacts、camera、microphone、sms |
| 有规则映射（18） | 上列并集，去重后 18 个 |
| **无任何引擎规则（4）** | biometric、calendar、personal_information、unknown |

`sink_type` 枚举共 9 个取值，当前有规则产出的 **7** 个：`file`、`ipc`、`log`、`network`、
`database`、`webview`、`clipboard`（后三个是 2026-09-29 补的）。
其余（`third_party_sdk`、`unknown`）无任何规则产出。

**状态：未覆盖。** 这 5 个类目与 2 个流向不是「待验证」，是当前引擎能力下根本没有规则
覆盖——两者混为一谈会让覆盖度看起来比实际高。

> **2026-09-29 更正一处枚举错误**：本节原写「无任何引擎产出（7）」并把 `calllog` 列为
> 枚举取值。**枚举里没有 `calllog`**——`compliance_profile.py::DATA_CATEGORY_CN` 与前端
> `complianceDict.ts` 的实际取值是 **`phone`**（电话状态），全仓库 grep `calllog` 在代码里
> 零命中，只有本文档写过它。上一版据此算出「7 个无产出」，多算了 `calllog`（它不在枚举里）、
> 漏了 `advertising_identifier` 与 `account`（当时确实无产出）。数量看着对是巧合，不是抵消。
> 通话记录（calllog）**在枚举里根本没有对应取值**，这是另一处独立缺口，见 §6。

## 6. 能力边界：静态不可表达

| 数据类目 | 流向 | 状态 | 依据 |
|---|---|---|---|
| contacts | network | 静态不可表达 | Task 1 实验：URL 常量作 sink 零命中（APIMode 只匹配方法签名）；`ContentResolver.query` 作 source 在 LibraryOnly + InstantDefault 模型下不传播到网络 sink |
| sms | network | 静态不可表达 | 同 Task 1 结论（与 contacts 同类，共用 `ContentResolver` 调用点） |
| 通话记录 | network | 静态不可表达 | 同上。注意这行的类目名**不是枚举取值**——枚举里没有 `calllog`（见 §5 的更正），也就是说通话记录既不可静态表达、也没有类目落点 |
| photos | network | 静态不可表达 | 2026-09-29 实验，见下 |
| calendar | network | **无法判定** | **不是「静态不可表达」**——三个样本都完全不涉及日历，见下 |

### 6.1 photos 的能力边界实验（2026-09-29）

按 Task 1 的同一套判定分支做，但**先确认样本真的调用了这些 API**，否则「零命中」与
「不可表达」分不开。

**样本侧取证**（app_version 11，DEX 字符串池 + 方法/字段引用）：

```text
MediaStore$Images$Media;->getBitmap          ← 被调用
MediaStore$Images$Thumbnails;->getThumbnail  ← 被调用
MediaStore$Images$Media;->EXTERNAL_CONTENT_URI / INTERNAL_CONTENT_URI  ← 被读取
MediaStore$Images$Media;->query / getContentUri  ← 未被调用
```

**实验**（绕开平台管线直接跑 AppShark CLI，独立规则目录，避免污染规则集与注册表）：

| 试验 | 规则 | 命中 |
|---|---|---|
| L2 事实 | `EXPL2_PhotosRead`（APIMode，sink 用上面实际被调用的签名） | **3** |
| L3 数据流 | `EXPL3_PhotosToNetwork`（Return source 用 `getBitmap`/`getThumbnail`/`query`，sink 用网络栈） | 0 |
| 对照探针 | `EXPL4_ContentResolverProbe`（Return source 用通用 `ContentResolver.query`） | 0 |

L2 命中的 3 个真实调用点：

```text
com.dahuatech.utilslib.SpanUtils$CustomIconMarginSpan.uri2Bitmap(Uri)
n.k.a.o.f(n.k.a.w,int)                                    （混淆类，调 Thumbnails）
com.yitong.mbank.app.utils.webview.d.h(int,int,Intent)     （WebView 文件选择回调）
```

**判定：L2 命中 + L3 不命中 → 读取可检出、流向不可检出。** 于是
`photos × network` 标「静态不可表达」，同时**保留 L2**：`Photos_APICall` 就是据此补的
正式规则，已在平台管线里对同一任务复现 3 条命中（`data_category=photos`、
`result_semantics=supporting_evidence`），「只跑隔离 CLI 不算过管线」这条也一并验了。

`EXPL4` 零命中复现了 Task 1 在 contacts 上的结论：通用 `ContentResolver.query` 的返回值
在 `LibraryOnly` + 默认模型下不传播到网络 sink。所以这不是相册独有的问题。

> **source 只用「返回值即数据」的接口**：`MediaStore$Images$Media.getContentUri` 返回的是
> Uri，按本项目对 Field source 的语义约定（URI 常量是查询条件、不是数据）不算数据，
> 故既不作 source 也不作 sink。实验里**没有**用 `EXTERNAL_CONTENT_URI` 当 Field source
> ——那正是设计文档 §10 推翻 v1 计划时点名的错误构造。

### 6.2 calendar：不能写「静态不可表达」

**三个样本都完全不涉及日历**：`CalendarContract` 在 DEX 字符串池里零命中，
三个 APK 也都没声明任何 CALENDAR 权限（`READ_CALENDAR` 一条都没有）。既没有 source
使用，就无从判断「读取能不能检出、流向能不能表达」——**任何结论都拿不到证据**。

因此这一格写「无法判定」，不写「静态不可表达」。这两者混同正是本文件开头要防的那类
错误：`ContentProviderPathResolver` 那次「触发过就算覆盖」，以及把没查证的环境限制
（「本环境无法访问 MASWE」）当成事实写进设计文档，都是同一个毛病的不同形态。

要判定它，需要一个**真的读写日历**的样本。

**「静态不可表达」不是覆盖缺口，是能力边界**，不能靠为每个类目写规则来解决（设计 §1.3）。
G3 记录了试图用字面值匹配绕过它所带来的后果。

但**「无法判定」与「静态不可表达」必须分开**：前者是样本不覆盖、没有证据，后者是有证据
的能力边界。把它俩写成同一个状态，等于用「测过没测出来」冒充「证明了做不到」——
calendar 一行就是这么处理的（写「无法判定」）。同理，本表任何一格如果要写
「静态不可表达」，都必须能指向一次**source 确实被使用**的实验。

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
| v1 关联规则 `PRIVACY_CONTACTS_NETWORK` 曾写 `MASWE-0001` | **2026-09-29 已改**：`MASWE-0001` 讲的是落盘加密（MASVS-STORAGE），与本规则无关，已改为 `MASWE-0067`；同时删去不存在的 `MASTG-TEST-PRIVACY-1`。库中以新版本 `1.2` 承载，`1.0`/`1.1` 原样保留（历史 Finding 的 `rule_version_id` 指着它们） |
| 十条判定规则（`PRIV-*`）原先没有 `standards` 块 | 2026-09-29 补齐。但要注意：这十条**不参与任何求值**——关联器只加载 `category == "correlation"`，而这十条的 category 是 consent/sdk/...，且 `when` 那套 DSL 不在 `validate_rule_content` 支持范围内。它们是规则库的目录条目，不是会命中的规则 |
| 官方 7 条规则的 `detail` / `complianceCategoryDetail` 已中文化 | 2026-09-29。原文逐条用新增的 `detail_en` 保留在同一个 `desc` 里。**副作用要知情**：AppShark 会把规则的 `detail` 原样带进 `results.json` 的 `details`（实测产物里已经是中文），所以这不只是界面文案，引擎输出也变了 |
| 本矩阵的「真实命中」数字不可复现 | 已于 2026-09-29 实测确认（同规则同样本连跑两次结果不同，含调用点集合），详见文首警示框。该列应读作「某一次运行的记录」，不是该规则的性质 |
