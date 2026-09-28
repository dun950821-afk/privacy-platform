# 权限知识库扩充为多平台

## 1. 背景

`privacy_kb.permission` 现在只有 103 条，且全部是 Android。作为「App 拿得到什么」的判定依据，
这个量级不够——Android 平台自己定义的权限就有上千条。

同时平台要扩到 iOS 与鸿蒙，而三种平台的权限命名体系完全不同：

```text
Android    android.permission.CAMERA
鸿蒙        ohos.permission.CAMERA
iOS        NSCameraUsageDescription
```

### 1.1 表里没有「平台」这个维度

```text
privacy_kb.permission
  permission_name  varchar(500)  UNIQUE   ← 只有名字，没有平台
  category / capability / permission_type / risk_level / grant_mode / ...
```

靠名字前缀去猜平台是个陷阱：`NS*UsageDescription` 这种规则容易误判，而且约定散在代码里，
以后加平台还得改推断逻辑。所以加一个显式的 `platform` 列。

### 1.2 权限知识库目前不可复现

来源是 `privacy_kb` 的一次性导入，**源文件已丢失、仓库里没有导入脚本**（见
`backend/sql/` 只有建表 DDL）。这次要顺手把这个坑填上：抓下来的原始来源文件入仓，解析脚本入仓，
数据能从零重建。

### 1.3 上一轮踩过的两个坑，本设计要避开

- **臆造权限名**：库里曾有 `android.permission.API` / `.SDK` / `.SMS` 这类不存在的权限，
  以及 `android.permission.BACKGROUND_LOCATION`（真名是 `ACCESS_BACKGROUND_LOCATION`）。
  根因是从短名表拼出来的。**本设计只从平台自己的定义文件取，不从任何二手清单取。**
- **受控词表失控**：`permission_type` 曾攒到 39 个自由文本取值。上一轮收敛成 8 个，
  所以这次扩充**必须有写入侧校验**，不能因为数据量大就放行自由文本。

## 2. 数据模型

新增一列，走 alembic 迁移：

```sql
ALTER TABLE privacy_kb.permission
  ADD COLUMN platform varchar(20) NOT NULL DEFAULT 'ANDROID';
CREATE INDEX idx_permission_platform ON privacy_kb.permission (platform);
```

- 现有 103 条靠 `DEFAULT 'ANDROID'` 自动回填（它们确实全是 Android）。
- 取值受控：`ANDROID` / `IOS` / `HARMONYOS`。写入侧校验，非法值拒绝。
- `permission_name` 仍是全局唯一键。三个平台的命名空间天然不重叠，不会撞车。

**为什么不塞进 `permission_type` 或 `category`**：平台与「权限级别」「功能分类」是三个正交维度。
上一轮刚把被覆盖的功能分类从 `category` 里恢复出来（`AD_ID` 的分类一度被写成「三方声明权限」），
再塞平台进去会把刚理干净的字段又搅浑。

## 3. 取数来源

三个来源都实测过可达、且是机器可读的。

| 平台 | 来源 | 实测 |
|---|---|---|
| Android | AOSP `core/res/AndroidManifest.xml` | master 分支 **1007** 条 |
| 鸿蒙 | `openharmony/docs` → `zh-cn/application-dev/security/AccessToken/permissions-for-*.md` | 按授权级别分 8 个文件 |
| iOS | Apple「Protected resources」文档 JSON | **58** 个 `*UsageDescription` 键 |

### 3.1 Android

从 `aosp-mirror/platform_frameworks_base` 取 `core/res/AndroidManifest.xml`（实测 **1018** 条
`<permission>`），解析 `android:name` 与 `android:protectionLevel`。

**这三个实测数字决定了本节的取舍，不要绕开它们：**

```text
protectionLevel 分布        可拿到的其它字段
  signature   752           permissionGroup  962 条缺失
  internal    120           描述文本          仅 16 条能解出
  normal      100
  dangerous    43
  role/system/module 3
```

- **1018 条里只有 143 条（normal + dangerous）是普通 App 真能申请的**，另外 875 条是签名/系统级。
- `permissionGroup` 962 条缺失，**不能**用来做功能分类。
- 描述文本基本拿不到：清单里只有 16 条引用的 `@string/permdesc_*` 能在
  `core/res/res/values/strings.xml` 解出来。AOSP 把权限描述放在各模块自己的资源里。
  **因此不得为这 1018 条编造「能力说明」——宁可留空。**

**处理方式（已与需求方确认）：全量收 1018 条，但把级别标清，界面上默认过滤掉签名/系统级。**

- 全收，不丢信息。
- `permission_type` 直接承载级别的区分（见 §4 的映射），页面上据它默认只看可达的那批。
- `capability` 留空是**正确结果，不是缺陷**；界面显示「—」，不得填占位文案。

**已知缺口（必须显式标注，不得假装收全）**：模块定义的权限不在 core 清单里。
实例：`android.permission.ACCESS_ADSERVICES_AD_ID` 真实存在（Android 13+ 隐私沙盒），
但定义在 AdServices 模块的清单中，core 里查不到。

- **模块清单尽力而为，不作承诺**。实测 `aosp-mirror` 组织下**没有** AdServices 模块的镜像仓库
  （`platform_packages_modules_AdServices` 返回 404），所以模块清单能否拿到、从哪拿，
  实现时才定。拿到就收，拿不到就不收。
- **无论收到与否，报告里必须写明「模块级权限未穷尽」，并逐条列出已收的模块与尝试失败的模块。**
  不允许把 core 的 1018 条说成「Android 全量」。

### 3.2 鸿蒙

`openharmony/docs` 的 AccessToken 目录下按授权级别分文件：
`permissions-for-all.md`、`permissions-for-all-user.md`、`permissions-for-system-apps.md`、
`permissions-for-system-apps-no-acl.md`、`permissions-for-system-apps-user.md`、
`permissions-for-enterprise-apps.md`、`permissions-for-mdm-apps.md`、`restricted-permissions.md`。

格式是每权限一个小节，结构化字段齐全，好解析：

```markdown
## ohos.permission.ACCESS_BLUETOOTH

允许应用接入蓝牙并使用蓝牙功能。

**权限级别**：normal
**授权方式**：用户授权（user_grant）
**起始版本**：10
```

映射：`##` 标题 → `permission_name`；正文 → `capability`；权限级别 → `permission_type`；
授权方式 → `grant_mode`；起始版本 → `raw_data.since_api`。

> 抓取注意：`raw.githubusercontent.com` 上 `openharmony/docs` 拉不动（实测 60s 超时）。
> 走 GitHub API 的 `Accept: application/vnd.github.raw` 头可以正常拿到。

### 3.3 iOS

本轮**只收 `NS*UsageDescription`**（58 个）。理由：这是开发者面对的隐私声明，
与 Android 权限语义最对等。

**不收** entitlements（`com.apple.developer.*`）与 TCC 服务名——它们的语义是「能力授权」
而非「用户隐私授权」，混进来会让 `permission_type` 的语义再次变浑。另开一轮。

## 4. 受控词表按平台

`permission_type` 从「一套全局词表」改成「按平台各一套」。这是加平台的直接后果：
Android 的「危险权限/签名权限」在 iOS 上不存在。

| 平台 | `permission_type` 取值 | 来源 |
|---|---|---|
| ANDROID | 危险权限 / 危险权限（受限）/ 普通权限 / 签名权限 / 特殊权限 / 已弃用权限 / 三方声明权限 / 未标注 | 现有 8 个，取自 `protectionLevel` |
| HARMONYOS | `normal` / `system_basic` / `system_core` | 文档的「权限级别」 |
| IOS | 用法描述键 | 58 个都是这一类 |

`protectionLevel` → `permission_type` 的映射（`|` 后跟的附加标志如 `privileged`、
`development` 只记进 `raw_data`，不影响主级别）：

```text
dangerous                     → 危险权限
normal                        → 普通权限
signature                     → 签名权限
internal / system / role / module → 特殊权限
```

**「普通 App 可达」的判定**收敛成一个函数，供 API 与页面共用，不各自硬编码：

```text
ANDROID:    permission_type ∈ {危险权限, 危险权限（受限）, 普通权限}
HARMONYOS:  grant_mode 含 user_grant  或  权限级别为 normal
IOS:        全部（用法描述键都是开发者要声明的）
```

`grant_mode`：Android 用现有写法；鸿蒙用文档的「授权方式」（`user_grant` / `system_grant`）；
iOS 留空（用法描述键没有「授予」动作，它决定的是调用受保护资源时系统是否弹窗）。

`/permissions/meta` 加 `platform` 参数，按平台返回该平台的受控词表。

## 5. 导入流程

```text
scripts/fetch_permission_sources.py   抓原始文件 → data/kb/<platform>/
scripts/import_permissions.py         解析 → UPSERT → privacy_kb.permission
```

### 5.1 原始文件入仓

`data/kb/android/AndroidManifest.xml`、`data/kb/harmonyos/permissions-for-*.md`、
`data/kb/ios/protected-resources.json`，连同 `data/kb/SOURCES.json`（记录每个文件的
来源 URL、抓取时间、sha256）。

抓取与导入分离：**导入脚本只读仓库里的文件，不联网**。这样数据可从零重建，且复现不依赖网络。

### 5.2 幂等

- 按 `permission_name` UPSERT。
- **不覆盖人工编辑过的行**。判定方式具体化为：取 `privacy_kb.import_batch` 中
  `source_file = 'permission-import:<平台>'` 的**最近一行的 `finished_at`** 作为基线，
  凡 `permission.updated_at` 晚于该基线的行一律跳过，并计数。首次导入时基线不存在，全量写入。
  否则每次重跑都会把界面上改过的说明冲掉。
- 写 `privacy_kb.import_batch` 审计（`source_file` 按平台命名，供上面取基线），
  统计新增/更新/跳过数。

### 5.3 大 `permission_name` 的去重

Android 的 core 清单里同名 `<permission>` 可能声明多次（不同 protectionLevel），
解析时按 name 归并，取更宽的 protectionLevel，并在 `raw_data` 里保留全部出现。

## 6. API 与页面

- `GET /api/v1/permissions` 加 `platform` 与 `applicable` 两个筛选参数。
  `applicable=true` 表示只返回「普通 App 可达」的条目（判定见 §4）。
- `GET /api/v1/permissions/meta` 加 `platform` 参数，返回该平台的词表。
- `POST` / `PUT` 校验 `platform` 与 `permission_type` 的**组合**合法（类型必须属于该平台）。
- 页面：平台下拉（全部 / Android / iOS / 鸿蒙），表格加「平台」列，新建时平台必填。
  **默认勾选「只看应用可申请」**——Android 那 875 条签名/系统级默认不占版面，取消勾选才显示。

## 7. 测试

- 解析器单测：三平台各一个样本文件 → 断言解析出的条数与关键字段。
- Android `protectionLevel` → `permission_type` 的映射：四种主级别各一例，
  `dangerous|privileged` 这类带附加标志的也能正确归到「危险权限」。
- 导入幂等：连跑两次，第二次新增为 0。
- 不覆盖人工编辑：手工改一行 → 重跑导入 → 该行不被冲掉。
- `permission_type` 按平台校验：给 iOS 行写「危险权限」应被拒。
- 平台筛选：`?platform=IOS` 只返回 iOS 行。
- 可达性筛选：`?platform=ANDROID&applicable=true` 不含「签名权限」行。
- **`capability` 为空的行必须能正常入库与返回**（Android 大多数如此），不得因为空值报错或填空占位。
- 迁移：升级后 103 条旧行的 `platform` 均为 `ANDROID`。

## 8. 不做的事

- **entitlements / TCC 服务名**（iOS）：语义不同，另开一轮。
- **Android 模块级权限穷尽**：本轮只收 core + 已确认的少数模块，缺口写进报告。
- **动态抓取**：导入脚本不联网，抓取是独立的一次性脚本。
- **把权限关联到组件**（`component_permission` 的批量维护）：那是组件侧的事。
