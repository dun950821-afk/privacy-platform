# AppShark 规则能力边界（实测）

样本：营口银行 v4.5.1（`app_version_id=12`），未加固，DEX 引用了 `ContactsContract`。
每次实验均为真实任务，结果取自 `engine_observations`。

## 能力矩阵

| # | 能力 | 状态 | 依据 |
|---|---|---|---|
| 1 | API Fact：识别 `ContentResolver.query()` 调用 | **VERIFIED** | `APIMode: true` + 方法签名作 sink → 命中 76 次 |
| 2 | URI Fact：识别 Contacts URI 常量 | **FAILED** | `Field` source 用 `Contacts.CONTENT_URI` → 未命中 |
| 3 | URI → query：证明该 URI 是 query 的参数 | **NOT_VERIFIED** | 依赖 #2，未单独验证 |
| 4 | query → Cursor：保持返回对象语义 | **NOT_VERIFIED** | 未验证 |
| 5 | Contacts Data → Sink | **NOT_EXPRESSIBLE** | 见「关键失败」 |
| 6 | 跨类目隔离 | **NOT_CONDUCTIBLE** | 四类均无信号，无从隔离（见下） |

## 关键失败

### 失败 1：URI 常量不能作为 APIMode 的 sink

```text
错误写法  "APIMode": true, sink: {"<ContactsContract$Contacts: * CONTENT_URI>": {}}
结果      零命中
原因      APIMode 的 sink 列表只匹配方法签名，不识别静态字段常量
对照      DeviceId_APICall（方法签名作 sink）同次运行命中 18 次
```

### 失败 2：URI 常量作为 Field source 无法传播到 sink

```text
写法      source.Field = [Contacts.CONTENT_URI...]，sink = Log.d/i/e
结果      零命中
```

### 失败 3：`ContentResolver.query` 作 Return source 无法传播到网络

```text
写法      source.Return = [<ContentResolver: * query(*)>]，sink = 网络栈
结果      零命中
原因      污点在 LibraryOnly + InstantDefault 模型下不传播到 sink
```

## 由实验 A 得出的关键推论

实验 A 命中的是 `ContentResolver.query` —— 这是**所有内容提供者共用的唯一调用点**：

```text
76 次命中
  ├── 其中可能包含通讯录查询
  ├── 也可能包含日历、媒体、通话记录、设置等一切查询
  └── 该观测无法区分是哪一个
```

因此：

```text
正确命名  fact.content_resolver_query        ✓ 只声明「调用了查询 API」
错误命名  fact.contacts_read / contacts_data_read  ✗ 语义扩大
```

同时说明：**不给 #6 跨类目隔离做验证，就无法把 `ContentResolver.query` 用于任何类目专属结论。**

## 结论

contacts / sms / calllog 的「读取 → 外传」在当前 AppShark 规则语言与引擎配置下 **不可静态表达**。

- 检测「调用了查询 API」：可以（类目无关）
- 检测「查询目标是通讯录」：**不能**（URI 常量既不能作 sink，也不能作可传播的 source）
- 因此无法形成「通讯录数据 → 网络」的 source→sink 规则

这不是规则库缺口，是能力边界。不得通过扩大 Source 范围（例如用 `ContentResolver.query` 冒充通讯录来源）来制造覆盖假象。

### 实验 E：跨类目隔离 —— 无法进行

四类合并为一次运行（task 576，规则数 21，引擎 completed 无报错）：

```text
EXP_Iso_ContactsUri   (Contacts.CONTENT_URI)        未命中
EXP_Iso_CalendarUri   (CalendarContract.Events)     未命中
EXP_Iso_CallLogUri    (CallLog.Calls)               未命中
EXP_Iso_MediaUri      (MediaStore.Images.Media)     未命中
```

四类**一致**未命中，说明 URI 常量作 source 的失效不是通讯录特有，而是该机制对所有内容提供者均不生效。

**因此隔离无法验证**：没有信号，就没有可被误分类的对象。把它记作「隔离 VERIFIED」会是空通过（vacuous pass）——测试通过是因为什么都没发生，而不是因为隔离正确。

故状态记为 `NOT_CONDUCTIBLE`（前提不成立，测试无法产生信号），不记为 VERIFIED，也不记为 FAILED。

**这条结论的实际约束**：只要 URI 常量机制不生效，`ContentResolver.query` 观测（#1，类目无关）就**没有配套的类目限定手段**，因而不得用于任何类目专属结论。

## 能力边界 2：看不穿接口/多态调用，因此「X 流入 Y」型规则系统性高报

**状态：VERIFIED（2026-09-28，Task 7 逐条核实官方规则时发现）**

前一条边界说的是「检测不到」，这一条相反：**检测得到，但把「存在数据流」当成「存在漏洞」**。

污点分析只跟踪值与调用点，不进入被调用方的实现。当校验逻辑藏在接口的实现类里时，
规则看到的是「外部输入流入 sink」，看不到「实现里已经校验过」，于是报出漏洞。

实测（app_version 11 门户测试 3.4.24，task 810）

```text
规则      ContentProviderPathTraversal        命中 3 条，1 个调用点
调用点    <com.tencent.smtt.utils.FileProvider: ParcelFileDescriptor openFile(Uri, String)>
规则报告  @parameter0 (Uri) → $r4 = FileProvider$a.a(Uri) → ParcelFileDescriptor.open($r4)
```

规则只看到 Uri 流入 `open`。但 `FileProvider$a` 是接口，其**唯一实现** `FileProvider$b.a(Uri)`
里做了标准的包含校验：

```text
v5 = new File(root, attackerPath)
v5 = v5.getCanonicalFile()                      ← 解析 ../
if (v5.getPath().startsWith(root.getPath())) return v5
else throw new SecurityException("Resolved path jumped beyond configured root")
```

`../` 会被规范化后拒绝，**该命中是误报**。

### 影响范围与诠释方式

- 这不是某一条规则写错了，而是**该类型的规则都如此**：凡是「外部输入 → sink」的
  断言，其成立与否取决于被调用方是否校验，而这一点污点分析不覆盖
- 反过来也不成立：`unZipSlip` 在同一批样本上确实检出了真阳性
  （`ZipUtil.unzip` 直接以 `dest_dir + "/" + entry.getName()` 作输出路径，无规范化）。
  所以命中**既不是**「必为漏洞」**也不是**「无意义」
- 正确的诠释：**命中是一条线索，不是一条结论**。判定命中的真伪必须下沉到实现字节码
  （Task 7 的做法），平台层面不得把「引擎报了这个规则」直接当成「存在该漏洞」

### 对平台的一处直接后果（待决策，尚未改动）

`ContentProviderPathTraversal` 这类官方安全规则在语义注册表里的
`result_semantics = direct_finding`，于是平台会**直接把它转成用户可见的结论**——
包括这个已被证实的误报。而本平台自有的数据流规则（`DeviceId_FileWrite` 等）不同：
它们声称的只是「存在一条 source→sink 路径」，命中即为该论断本身，不存在同一问题。

因此「哪些观察配得上 `direct_finding`」需要在官方安全规则上重新审视：可选做法是把它
降为 `supporting_evidence`（只做证据、不直接成结论），或引入「引擎判定未核实」这一
中间态。**这是语义层改动，会影响 Finding 生成与覆盖矩阵，需先定策略再动。**

同类受影响规则（同属官方安全规则且论断为「漏洞存在」）：`IntentRedirectionBabyVersion`、
`PendingIntentMutable`、`unZipSlip`。其中后两条已分别在真实样本上确认为真阳性，但
**这条边界意味着它们同样可能报出误报**，只是本次取样中未遇到。

## 未完成

- #6 跨类目隔离记为 `NOT_CONDUCTIBLE`：前提机制（URI 常量作 source）不生效，测试无信号。
  若将来该机制被启用（例如通过 EngineConfig 的 PointerFlowRule），**必须重新执行本实验**，不得沿用当前结论。
