# SDK 知识库「包名前缀 ↔ 厂商」归属复核（2026-09-28）

独立子 agent 全量复核的结果。**全程只读**（SELECT + 外部抓取），未改动任何数据。
待权限知识库多平台那轮（`docs/superpowers/plans/2026-09-28-permission-kb-multi-platform.md`）
跑完后集中处理。

## 覆盖面与前提

| 项 | 数量 |
|---|---|
| 库内 `PACKAGE_PREFIX` 总数 | 648 |
| 在 LibChecker 规则库中找到对应 | 144（22%） |
| 找不到对应 | 504（78%） |

**前提，别误读成「错」**：LibChecker **没有** AppsFlyer / Amplitude / Flurry / CleverTap / Branch /
Chartboost 等大量海外 SDK 的规则，也**没有** `com.fhvideo`、`me.iwf.photopicker`、`org.sana`、
`preview`、`com.hanlyjiang.*`、`com.sina.deviceidjnisdk`、`com.sunyard.*`、`com.byazt`、
`com.linecorp.line.admolin`、`cn.com.union.fido` 的任何规则。
「LibChecker 里查不到」是常态，**只有找到正面矛盾才判错**。

## 一、【错误】11 处（每条有亲眼看到的证据）

### 1. 三网合一键登录的四个前缀全部挂错厂商（最严重）

现有条目「创蓝闪验」/「友盟+智能认证」把移动、电信、联通、阿里四家的包都算到了自己头上。

| 前缀 | 当前登记 | **应为** | 依据 |
|---|---|---|---|
| `com.cmic.sso` | 创蓝闪验 / 创蓝云智 | **中国移动「移动认证」（中移互联网）** | LibChecker label=`移动号码认证`、dev_team=`中国移动`、icon=`ic_lib_cmcc`；中国移动官方 SDK 文档正文含 `com.cmic.sso.sdk.activity.LoginAuthActivity` |
| `cn.com.chinatelecom.account` | 创蓝闪验 / 创蓝云智 | **中国电信「天翼账号认证 SDK」（天翼数字生活科技）** | `id.189.cn` 官方页写明 SDK 名与开发者；集成文档含 `cn.com.chinatelecom.account.sdk.ui.AuthActivity` |
| `com.unicom.xiaowo` | 创蓝闪验 / 创蓝云智 | **中国联通「小沃账户」（小沃科技/联通在线）** | 三网 proguard 并列证据；**创蓝自己的混淆规则**里联通槽位是 `com.unicom.online.account.*`，全文 `xiaowo` 出现 0 次 |
| `com.mobile.auth` | 友盟+智能认证 / 友盟同欣 | **阿里云号码认证服务** | 阿里云官方接入文档逐字给出 `com.mobile.auth.gatewayauth.LoginAuthActivity`；LibChecker dev_team=`Alibaba`；友盟官方 FAQ 自认「使用了阿里通信相关服务的合作 SDK」 |

注：`com.mobile.auth.gatewayauth` 已单独挂在「阿里云号码认证服务」下，父前缀 `com.mobile.auth` 却挂友盟——父子矛盾。

### 2. 其余 7 处

| 组件 | 当前登记 | **应为** | 依据 |
|---|---|---|---|
| TBS 文件预览封装组件 | 腾讯 | **个人开发者 hanlyjiang**（开源 `AndroidDocumentViewer`） | 仓库源码首行 `package com.hanlyjiang.library.fileviewer;` |
| Sign in with Apple Android | Apple/第三方 | **WillowTree, LLC** | Maven POM 的 url/developer 指向 willowtreeapps；GitHub org name 即 `WillowTree, LLC` |
| 华为广告联盟 Openalliance | 华为（`com.huawei.hianalytics`） | 厂商华为**对**，但产品名错——`com.huawei.hianalytics` 是 **HMS Analytics Kit** | 华为官方 codelab 混淆段含 `-keep class com.huawei.hianalytics.**{*;}`；LibChecker label=`HMS Analytics Kit` |
| Sign in with Apple Android | Apple/第三方（`com.apple.android.sdk.authentication`） | 确是苹果的，但不是 Sign in with Apple，是 **Apple Music 的 MusicKit 认证模块** | 苹果官方 API 文档页标题即 `com.apple.android.sdk.authentication (Apple Music - Android MusicKit)` |
| OpenMediation | OpenMediation | **AdTiming（图数科技）** | AdTiming 官网 OpenMediation 落地页写明仓库与联系邮箱 `openmediation@adtiming.com`、©AdTiming |
| PhotoPicker 开源图片选择库 | 开源社区（厂商待核验） | **donglua** | 上游 README 逐字给出 `me.iwf.photopicker:PhotoPicker:0.9.12@aar` |
| Xposed API | rovo89/LSPosed（复合） | **两个不同项目被合成一个**：`de.robv.android.xposed` 属 rovo89/XposedBridge；`io.github.libxposed` 是独立的 Modern Xposed API。libxposed 是否即 LSPosed 团队维护**无法确证** | 各自源码/POM |

## 二、结构性脏数据（归属不算错，但会污染「按厂商聚合」的画像）

1. **父子前缀跨两家厂商 13 处**，其中真问题 3 处：
   - `com.mobile.auth`（友盟同欣）→ `.gatewayauth`（阿里云）：父子都是阿里云的包，父挂友盟是错的
   - `com.dahuatech`（大华股份）→ `.favoritecomponent` / `com.mm.dss.*`（大华技术）：**同一家公司两个 vendor 行**，应合并
   - `com.fhvideo`（飞虎互动（需进一步核验））→ `.bankui.*`（飞虎互动（待确认））：**同一家公司两个占位名**
2. **占位/复合厂商名待清理**：`待核验`、`NUI（开源作者待核验）`、`SANA（厂商待核验）`、
   `开源社区（厂商待核验）`、`开源作者待核验`（0 组件）、`XinLan/开源作者`（0 组件）、
   `飞虎互动（待确认）`、`飞虎互动（需进一步核验）`；复合名 `Apple/第三方`、`Apache/Alibaba`、
   `阿里巴巴/UC`、`rovo89/LSPosed`、`8x8/Jitsi`、`ZXing/屹通`、`屹通/个推`、`信雅达/百度地图`、
   `LuckSiege / StarForLuck`、`siwangqishiq / XinLan`、`Agora 声网`/`声网`、
   `每日互动（个推）`/`每日互动`、`Mobvista`/`汇量科技`、`大华股份`/`大华技术`、`网易云`/`网易云信`
   - 其中 `LuckSiege / StarForLuck` 的后半、`siwangqishiq / XinLan` 的后半**均无法确证**
3. `com.tencent.mobileqq.qfix` → 「腾讯云移动应用安全」存疑（qfix 是 QQ 客户端热修复框架），**未确证**

## 三、【无法确证】——保持原样，不要臆断

| 组件 | 前缀 | 情况 |
|---|---|---|
| FIDO UAF 指纹认证客户端 | `cn.com.union.fido` | 能确证的只有「它不是开源」（开源 UAF 用 `org.ebayopensource.fido.uaf.*`）。最像 CFCA「FIDO+」，但**没有官方页面把两者直接挂钩**，且 CFCA 云证通自己用 `cn.com.cfca.*` |
| SANA 音视频通话 SDK | `org.sana*` | 全网找不到任何 `org.sana` 的 VoIP SDK 或厂商 |
| MultiPhotoPicker | `com.nui.multiphotopicker` | GitHub 上同名仓库用的是**不同包名**，不能据此归因 |
| 自动裁边预览组件 | `preview` | **不存在包名叫 `preview.*` 的库**，高度疑似从 manifest 误抽的伪前缀（误报风险极高）。**注：该前缀已在早前清理中删除** |
| 微博 DeviceID | `com.sina.deviceidjnisdk` | 字符串全网 0 命中；微博官方 AAR 解包后只有 `com.sina.weibo` |
| LINE Admolin | `com.linecorp.line.admolin` | 「Admolin」在 LINE 官方文档/Maven/GitHub/LibChecker **全部 0 命中** |
| 信雅达百度地图适配组件 | `com.sunyard.baidumapapi` | 具体包名 0 命中；`com.sunyard` 属信雅达可立，但**复合厂商名「信雅达/百度地图」在归因上不成立**（百度只是被引用的依赖） |
| 飞虎互动 及 3 个子组件 | `com.fhvideo*` | 厂商实体确证（飞虎互动科技（北京），feihu365.com）；但**没有任何来源写出 `com.fhvideo` 包名**，绑定属推断。另：描述写「银行场景直播」与已确证的「视频银行/云柜台/智能双录」不符 |
| Glide | `com.bumptech.glide` | 「Bumptech」是 GitHub 组织名（其 `name` 字段为 `Bump Technologies`，已停业），不是现行主体；现行维护者邮箱均为 `@google.com`，但**没有来源明写厂商=Google**，故不判错 |

## 四、最可疑但未确证（按可疑度排序）

1. **`com.byazt` → 穿山甲广告 SDK / 字节跳动**。全网搜不到该包名与穿山甲的关联；穿山甲标准命名空间是
   `com.bytedance.sdk.openadsdk` / `com.bytedance.pangle` / `com.pangle.cn:ads-sdk-pro`。
   **可疑度高，但无反证**。**这条前缀是本次知识库整理时新加的**，需重点复核。
2. `s.h.e.l.l` → 爱加密：只有论坛帖，证据等级太弱
3. `com.bumptech.glide` → Bumptech（见上）
4. `com.linecorp.line.admolin` → LY Corp（「Admolin」无踪迹）
5. `com.sina.deviceidjnisdk` / `preview` / `com.nui.multiphotopicker` / `org.sana` / `com.sunyard.baidumapapi`：包名本身查不实，疑似误抽
6. `cn.com.union.fido`：旁证指向 CFCA，非官方声明
7. `com.fhvideo` 的包名↔厂商绑定
8. `com.tencent.mobileqq.qfix` → 腾讯云移动应用安全
