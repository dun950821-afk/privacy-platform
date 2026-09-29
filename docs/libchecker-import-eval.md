# LibChecker 规则导入评估（干跑，未写库）

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

## 五、建议的推进顺序

1. **先建组件别名/层级映射表**（§1 的三类）——这是唯一的前置，且工作量可控
   （冲突 72 处，涉及的新组件 288 个里大部分是纯新增，不需要映射）
2. **导入 type 1-5 共 1222 条**：清单类 + DEX，正好补我们最薄的 `MANIFEST_*`（现 225 条）
3. **native 单列一期**：加指纹类型与候选来源
4. 导入时**沿用 `upstream-provenance.json` 那套来源登记**
   （repo / commit / rulesVersion / license），与 AppShark 规则一致

## 六、这次的导入**没有**做的事

- **没有写库**：`--apply` 目前直接报错退出，不是忘了实现，是刻意的
- 没有把 LibChecker 的 PERMISSION/能力类信息接进归属（它没有这类规则，但这条原则
  同样适用，见 `docs/kb-dedup-report.md` §3）
- 没有因为「导入方便」而放宽 `MATCHABLE_TYPES`
