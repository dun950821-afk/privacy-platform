# LibChecker 规则导入评估与执行

2026-09-29。工具：`scripts/import_libchecker_rules.py`（默认干跑）。
来源：`LibChecker/LibChecker-Rules` 分支 `v4` 的编译产物 `cloud/rules/v4/rules.db`
（176KB 单文件，2832 条规则）。许可 **Apache-2.0**，与我们已引的 AppShark 同许可。

## 一、结论先说

**可以用，而且能补到不少我们没有的 SDK。但卡住导入的不是指纹，是「组件身份」。**

先把那 72 处「取值已存在、但归属别的组件」看清楚：它们**绝大多数是同一个实体的
两种写法**，不是两套来源真的打架。

```
Jetpack WorkManager   × AndroidX WorkManager        12 处
HUAWEI Push           × 华为推送服务                  5 处
MiPush                × 小米推送 SDK                  4 处
个推                   × 个推消息推送 SDK               3 处
Jetpack Room          × AndroidX Room                2 处
极光推送                × 极光推送 SDK                  1 处
vivo Push             × vivo 推送 SDK                1 处
网易云通信 SDK          × 网易云信 IM SDK               1 处
```

所以导入的前置不是「解指纹冲突」，而是**建一张组件别名/层级映射表**：

1. **同名异写** → 直接映射到现有组件，不新建
2. **伞形 vs 模块** → 决定归属，或建父子关系
   （`Firebase` ⊃ `Google Data Transport`、`百度地图 SDK` ⊃ `百度定位 SDK`、
   `高德地图 SDK` ⊃ `高德定位 SDK`、`ML Kit` ⊃ `Google ML Kit Common`）
3. **聚合关系** → 两边都对，要建模而不是二选一

第 3 类在 LibChecker 那边是**显式写出来的**，比我们清楚：
`OPPO Push(GeTui Proxy)`、`MiPush(GeTui Proxy)` —— 它直接在名字里标了「这是经由个推接入的」。

## 二、数字

```
LibChecker 规则总数           2832
  可直接映射                  1222
  类型未映射                  1604   （native 1491、intent action 99、未知 type6 14）
  regex 无法证明等价而拒收        6   （见 §4）

与现有知识库对照（1222 条）
  同组件、完全一致               13
  **冲突**（取值已有、归属别的组件）  72   ← 见 §1，多为同名异写
  新增指纹                     1137
  其中涉及的新组件名              288
```

**新增指纹涉及的新组件里有不少我们完全没有的**（按指纹数）：

```
Stripe SDK 38、Pangle SDK 30、智齿客服 SDK 28、Intune App SDK 27、Nebula SDK 26、
Intercom 26、mPaaS 21、极光推送 20、GMP Push SDK 20、友盟推送 19、MSAL 19、
阿里移动推送 16 …
```

## 三、type 映射

LibChecker 靠 `type` 区分规则对象（v5 契约文档）：

| type | 数量 | 我们的指纹类型 |
|---|---|---|
| 0 native | **1491** | **无对应类型**（也不从 APK 取库名）→ 本期不收 |
| 1 service | 288 | `MANIFEST_SERVICE` |
| 2 activity | 554 | `MANIFEST_ACTIVITY` |
| 3 receiver | 137 | `MANIFEST_RECEIVER` |
| 4 provider | 167 | `MANIFEST_PROVIDER` |
| 5 DEX | 82 | `PACKAGE_PREFIX`（存的是包名，语义为前缀） |
| 9 intent action | 99 | 无对应类型 → 本期不收 |
| 6 未知 | 14 | 契约文档未列明 → 保守不收 |

**native 占 1491/2832（53%）**，是我们没有的一整块：需要新增指纹类型 + 从 APK 的
`lib/` 取候选来源，属于功能开发，单列一期。

## 四、regex 只收可证明等价的，其余拒收

LibChecker 的 regex 是**锚定**语义（`re.fullmatch`），所以 `X(.*)` 这类模式与我们
的 PREFIX `X` 等价。转换器只接受「字面前缀 + `(.*)`」这一种形状，带分支、字符类、
量词、或 `(.*)` 后面还有字面量的一律**拒收并列出**——不做尽力而为的翻译。

拒收 6 条，全是字节跳动 Mira 壳的混淆 Activity：

```
com\.bytedance\.mira\.stub\.p[0-9]*\.StubTranslucentActivity
com\.bytedance\.mira\.stub\.p[0-9]*\.StubService[0-9]*$
...（共 6 条，完整清单见 --report 输出）
```

总共 123 条 regex 里，**非 native 的部分几乎都转成了前缀**，只有这 6 条落在可证明
范围之外。

## 五、组件映射表 + 口径已定，冲突全部落地（**仍需处理 0**）

`data/kb/libchecker_component_map.tsv`（人工资产，同 `curated_permission_snapshot.tsv`
的做法）。覆盖全部 45 个会撞车的 label，校验过：**45 行逐个对得上知识库里的组件名，
0 个写错**。

### 口径：**取更细的身份，用关系表达包含/聚合**

粗的那个身份会掩盖信息，与仓库既有的「命名不得扩大」一致。落到两类：

**UMBRELLA_BUNDLES（5 处）——保留我们的细粒度**
```
Firebase        --BUNDLES--> Google Data Transport
HMS Core        --BUNDLES--> 华为 HMS Core 基础 Activity
ML Kit          --BUNDLES--> Google ML Kit Common
百度地图 SDK      --BUNDLES--> 百度定位 SDK
高德地图 SDK      --BUNDLES--> 高德定位 SDK
```
另建 LibChecker 那个伞形组件，挂 `BUNDLES` 关系。**不合并**——否则会丢掉
「只用了定位、没用地图」这类区分。

**PROXY_DEPENDS_ON（4 处）——采用 LibChecker 更细的身份**
```
HUAWEI/MiPush/OPPO/vivo Push(GeTui Proxy)  --DEPENDS_ON--> 个推消息推送 SDK
```
LibChecker 把「经由个推接入的厂商推送」单列成一个身份。**两者不是二选一**：
「装了 OPPO 推送且经个推接入」与「只装了 OPPO 推送」是不同结论。所以另建代理通道
组件并挂 `DEPENDS_ON`。

关系落在 `privacy_kb.component_relation`——该表的 `relation_type` 约束**已经含**
`BUNDLES` / `DEPENDS_ON` / `PART_OF` / `PUSH_CHANNEL`，**不需要改 schema**
（该表此前 0 行，和 `data_finding` 一样是「有结构没用过」，但这次有明确用途了）。

### 干跑出的导入计划（执行结果见 §6.2）

```
LibChecker 规则                      2832
  可直接映射                          1222
  类型未映射（native/intent/未知）      1604
  regex 无法证明等价而拒收                6

对着现有知识库：
  同组件、完全一致                       13
  冲突 72 → 并入现有组件 58 + 另建组件并建关系 14
  仍需处理                              0   ← 口径定完，全部落地
  新增指纹                            1137
  其中涉及的新组件名                     288
```

## 六、建议的推进顺序

1. ~~定那 14 处的口径~~ —— **已定，见 §5**
2. **导入 type 1-5 共 1222 条**：清单类 + DEX，正好补我们最薄的 `MANIFEST_*`（现 225 条）
3. **native 单列一期**：加指纹类型与候选来源
4. 导入时**沿用 `upstream-provenance.json` 那套来源登记**
   （repo / commit / rulesVersion / license），与 AppShark 规则一致

## 六之二、导入已执行（2026-09-29）

```
组件  506 → 773   (+267)
指纹 2867 → 4012  (+1145)
关系    0 → 5     (BUNDLES ×5)
```

来源登记挂在知识库里**原有的** `LibChecker Rules` source 行上（`source:577e149c…`，
类型「开源规则库」、信任度「中高」——不是本轮新建的），批次 `libchecker-rules:v4`
记了 `source_sha256`。跑第二遍是 0 新增 / 1216 跳过，**幂等**。

### 但**在现有样本上看不出成效**，只有 1 条正命中

索引从 948 条涨到 **2093 条**，新指纹确实生效；可是 task 2348 的命中数
**64 → 64 不变**。把全部样本都过一遍：

```
本次导入的 267 个组件里，在任何样本上命中过的: 1  —— Weex
```

那一条是真阳性：app_version 12 的 `static_component` 事件
`com.alibaba.android.bindingx.plugin.weex.WXBindingXModuleService`，命中的是
`MANIFEST_SERVICE/EXACT`，确实是阿里 Weex 框架的 BindingX 模块服务。

**其余 266 个没命中，不是导入有问题，是样本里没有那些 SDK**——LibChecker 补的是
Stripe、Pangle、智齿客服、Intune、Nebula、Intercom、mPaaS、MSAL、阿里移动推送
这类，三家银行 App 都不用。要看到这批规则的价值，需要**用得上它们的样本**
（与 `rule-coverage.md` 里「样本已用尽」是同一件事）。

### deferred_proxy（6 条指纹）没有导入

定「采用更细的身份」这条口径时还不知道那些指纹长什么样。实际查下来，它们全在
`com.igexin.sdk.*` 命名空间下——**那是个推自己的代码**（igexin = 个推）。
LibChecker 的 `OPPO Push(GeTui Proxy)` 描述的是「这个类干什么」（OPPO 通道的个推
实现），不是「它属于谁」。**所以归给个推本来就对**，不该搬走、也不该另建组件
（那些组件会没有任何指纹、永远匹配不到）。

这条与先前拍板的口径冲突，**留待重新决定**，脚本里显式跳过并计数（`deferred_proxy`），
不替人做这个决定。

## 七、这次**没有**做的事

- 没有导入 native（1491 条）、intent action（99 条）、未知 type6（14 条）——
  前两者我们没有对应的指纹类型与候选来源
- 没有导入 `deferred_proxy` 那 6 条（理由见 §6.2，与已定口径冲突，留待重决）
- 没有把 LibChecker 的能力类信息接进归属（它是描述性标签，同
  `docs/kb-dedup-report.md` §3 的 PERMISSION 教训）
- 没有因为「导入方便」而放宽 `MATCHABLE_TYPES`
- 没有为看成效而挑样本——现有样本只有 1 条正命中，就如实写 1 条
