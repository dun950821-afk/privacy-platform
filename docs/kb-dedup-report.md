# 知识库指纹体检：重复登记与「共性当特征」

2026-09-29。起因是匹配器里 `ComponentIndex.duplicate_count` 报出 **744 处**重复登记，
于是逐条查了一遍。**结论是那个数字不能直接用，真正要处理的只有 15 处 + 一类建模错误。**

## 一、先把三个口径分清楚

| 口径 | 数字 | 含义 |
|---|---|---|
| 匹配器的 `duplicate_count` | 744 | 索引构建时**逐条**计数，同一取值被 3 个组件登记会记 2 次；且包含不参与匹配的类型 |
| 按 (类型, 取值) 去重后 | **138** | 真正「同一个取值被多个组件登记」的取值个数，涉及 343 个组件 |
| 其中**会造成归属分歧**的 | **41 → 修正后 15** | 见下 |

138 处的分布，决定了哪些要管：

```
API_SIGNATURE     97   ← 不是冲突，见下
PERMISSION        26   ← 建模错误，已修
MANIFEST_ACTIVITY 12   ← 真实冲突
MANIFEST_SERVICE   2
MANIFEST_PROVIDER  1
```

## 二、`API_SIGNATURE` 的 97 处不是冲突

它的取值是**中文能力标签**：

```
'socket/websocket'              被 13 个组件共享（腾讯云 IM、声网 Agora RTM、即构 ZEGO、火山引擎 RTC…）
'音视频采集'                    被 13 个共享
'编解码'                        被 13 个共享
'sqlite/orm/键值存储/加密数据库'  被 9 个 ORM 共享（Realm、ObjectBox、greenDAO、ORMLite…）
```

**多个 RTC SDK 都有「音视频采集」能力，这是正常的，不是冲突。** 这类取值本就不参与
匹配（见 `component_matcher.MATCHABLE_TYPES`），它们该待在展示层。

## 三、建模错误：权限被当成了指纹（已修）

`PERMISSION` 那 760 条指纹，与 `privacy_kb.component_permission` 表的 760 条关系
**一一对应**——是同一份数据在错误位置的一份副本。

拿它做归属**在建模上就不成立**：权限是**共性**，不是**特征**。

```
android.permission.INTERNET              关联 229 个组件
android.permission.ACCESS_NETWORK_STATE  关联 103 个
android.permission.CAMERA                关联  74 个
android.permission.RECORD_AUDIO          关联  68 个
```

从「App 声明了 INTERNET」推不出「229 个里哪一个在 App 里」。实测把权限接进匹配后，
`ACCESS_FINE_LOCATION` 同时挂在高德定位 SDK 与百度定位 SDK 上，匹配器只能按组件 id
抛硬币——产出的是**看着像结论的噪声**。

**处置：已从 `MATCHABLE_TYPES` 移除。** 权限关系继续留在 `component_permission` 表，
用于展示与「谁需要什么权限」的分析；要参与归属必须与更强证据组合（如权限 + 代码级
指纹同时命中），不能单凭权限定归属。

## 四、同一个毛病：通用后缀（**待处理**）

查权限时顺带发现，`SUFFIX` 模式的指纹里也混着一批通用名。它们本身有可比字符串，
但**指认不出唯一组件**：

| 取值 | 归属组件 | 问题 |
|---|---|---|
| `mainactivity` | 屹通移动银行框架 (Ares 平台) | **几乎每个 App 都有 MainActivity** |
| `loginactivity` | 屹通移动银行框架 (Ares 平台) | 同上 |
| `webviewactivity` | 屹通移动银行框架 (Ares 平台) | 同上 |
| `pushservice` | 个推消息推送 SDK | 各厂商推送服务常叫这个 |
| `statservice` | 百度移动统计 / 腾讯移动分析 MTA | 两家共用同一个通用名 |
| `authactivity` / `assistactivity` | QQ 互联 SDK | |
| `initprovider` / `pushprovider` / `pushreceiver` | 华为推送服务 | |
| `resultactivity` | Face++ 活体检测 SDK | |
| `tencent` | QQ 互联 SDK | **CLASS/SUFFIX，匹配任何以 tencent 结尾的类** |
| `gson` / `glide` / `retrofit` / `route` | Gson / Glide / Retrofit / ARouter | 库名当后缀，命中面过宽 |

这些目前**没有造成实测错误**，只是因为样本里的应用没踩上。`mainactivity` 那条尤其危险：
任何应用的主界面 Activity 都会被判给「屹通移动银行框架」。

**处置建议**：这类取值应从「归属指纹」降级为「提示」——或者删除，或者只用于人工
排查时的线索。判定信号很直接：**长度过短、是通用词、或与组件名无关的库名**。

## 五、真实冲突：15 处重复登记

### 5.1 同一个 App 自身模块之间的边界重叠（11 处）

全是 `com.yitong.mbank.app.*`——同一个厂商把「基础模块」和「业务模块」的指纹划重了：

```
com.yitong.mbank.app.android.activity.mainactivity          → 屹通移动门户业务 Activity × 屹通移动门户基础模块
com.yitong.mbank.app.android.activity.splashactivity        → 同上
...（menuSearch / setIp / welcomeGuide / ytPdfReader 同形）...
com.yitong.mbank.app.android.activity.contacts.contactsactivity  → 屹通移动门户业务 Activity × 屹通通讯录业务模块
com.yitong.mbank.app.android.fragment...addresslistinfodetailactivity → 屹通地址簿业务模块 × 屹通移动门户业务 Fragment
com.yitong.mbank.app.flutter.portalflutteractivity          → 屹通移动门户 Flutter 集成模块 × 屹通移动门户基础模块
com.yitong.mbank.app.utils.webview.webviewtohomeactivity    → 屹通移动门户 WebView 模块 × 屹通移动门户基础模块
```

**这是知识库的粒度问题，不是匹配器的问题**：同一个厂商的模块边界该由维护者定，不该由
匹配器猜。目前匹配器按「谁的代码级指纹更贴近这个类」裁决，实测这 11 条都落到了更具体的
模块上（ContactsActivity → 通讯录业务模块、PortalFlutterActivity → Flutter 集成模块）。

### 5.2 跨厂商的真冲突（4 处）

```
com.hanlyjiang.library.fileviewer.tbs.tbsfileviewactivity
    TBS 文件预览封装组件 × 腾讯 X5/TBS            ← 包装库 vs 上游 SDK，两者都成立
io.flutter.plugins.imagepicker.imagepickerfileprovider
    Flutter × Flutter Image Picker 插件          ← 伞形框架 vs 具体插件
oppopushservice
    OPPO/HeyTap 推送 SDK × 个推消息推送 SDK       ← 个推聚合厂商通道，重叠是真实的
statservice
    百度移动统计 × 腾讯移动分析 MTA（旧版）        ← 通用名，见 §4
```

前两条是「伞形 vs 具体」，**归给具体的一方**（已由代码级具体性实现）。第三条是聚合关系，
两者都对，属于建模层面要表达「个推接入 OPPO 通道」而不是二选一。第四条是 §4 的通用名问题。

## 六、裁决策略（可执行）

接新指纹（含从 LibChecker 导入）时按这三条判：

1. **能不能指认唯一组件？** 不能就不是指纹，是**关系**或**标签**。
   权限（§3）、能力标签（§2）、通用后缀（§4）都栽在这一条上。
2. **伞形/聚合 与 具体 重叠时，归给更具体的一方。** 现由「代码级指纹对候选串的匹配长度」
   裁决（`ComponentIndex._resolve_duplicates`）。
3. **判不出来时，匹配器给确定性结果（组件 id 较小者），并把该处标记进本报告等待人工复核。**
   **确定性 ≠ 正确**——不能用「结果是稳定的」冒充「结果是准的」。

## 七、对「引入 LibChecker 规则」的前置含义

LibChecker-Rules（Apache-2.0，规则约 1133 条清单类 + 1440 条 native）能补我们最薄的
`MANIFEST_*`（现有 225 条），重叠度也低（抽样 activity 全类名 60 个里只有 1 个已有）。
**但导入前必须先过第六节的第 1 条**：

- LibChecker 的 DEX 规则里同样有 `androidx.collection`、`com.facebook.fresco` 这类包名，
  与我们现有前缀会有交叠——导入时必须按第 2 条定谁优先，且**不能引入 §4 那种通用取值**
- 它的 `PERMISSION` 类信息（如果有）**不得**接进归属，理由同 §3
- native（type 0，占其规则一半以上）我们**没有对应指纹类型与候选来源**，单列一期
