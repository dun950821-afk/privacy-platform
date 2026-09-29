# permission_descriptions_zh.json 翻译自查报告

- 输入：`data/kb/android/permission_descriptions.json`（365 条，未改动，mtime 不变）
- 输出：`data/kb/android/permission_descriptions_zh.json`（365 条）
- 生成方式：以权限常量为键逐条手写译文，脚本校验键集合后落盘；未按英文原文匹配，避免同文异条被合并。

## 1. 键集合校验

| 检查项 | 结果 |
| --- | --- |
| 条目数 src / dst | 365 / 365 |
| 键集合相等（不多不少） | 是 |
| 键顺序一致（与输入同构同序） | 是（`list(src) == list(dst)`） |
| 空值 / 含换行 / 首尾空白 | 0 / 0 / 0 |
| 值仍为纯 ASCII（疑似漏译） | 0 |
| 值与英文原文完全相同（疑似漏译） | 0 |
| 译文重复条数 | 3 组（见下），均为原文即完全相同 |

3 组重复译文，源英文本来就一字不差，属正确行为：

- `BODY_SENSORS` / `BODY_SENSORS_BACKGROUND`
- `GET_ACCOUNTS` / `GET_ACCOUNTS_PRIVILEGED`
- `SHOW_POWER_MENU` / `SHOW_POWER_MENU_PRIVILEGED`

## 2. 标识符保留校验

用正则从英文原文抽出 160 个「类名/包名/常量名」形式的 token（含 `.` `#` 的限定名、CamelCase 名，如 `WallpaperService`、`android.content.pm.UserProperties#PROFILE_API_VISIBILITY_HIDDEN`、`WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY`），逐条确认在对应译文中原样出现。结果：**全部保留，0 丢失**。

另有 7 个 token 未“原样出现”，均为应译的英文缩写/名词，非标识符：`SMS`→短信、`MMS`→彩信、`IR`→红外、`TV`→电视、`RW`→读写、`e.g.`→例如、`i.e.`→即。

## 3. 结构与计数一致性

- `ERROR(` 出现次数：src 3 / dst 3（`APPLY_PICTURE_PROFILE` 一条内含 3 处，原样保留未拆解）
- `Protection level` → `保护级别`：src 8 / dst 8（数值串 `signature|privileged|development` 等原样未译）
- `&nbsp;` 实体：src 5 处，dst 0 —— 统一还原为普通空格（仅 HTML 标记，非文案内容）

## 4. 不确定条目（共 9 条，已按要求尽量直译）

| 键 | 英文原文 | 不确定点 |
| --- | --- | --- |
| `ACCESS_HIDDEN_PROFILES` | ...user property, e.g. | 原文在 "e.g." 处截断，译文照实以「例如」收尾，语义未完结 |
| `CREDENTIAL_MANAGER_SET_ORIGIN` | ...on behalf of another RP. | `RP` 缩写不明，按规则 5 保留字面并附（原文：RP），未猜「依赖方」 |
| `MODIFY_PHONE_STATE` | ...power on, mmi, etc. | `mmi` 缩写不明，按规则 5 附（原文：mmi），未猜「人机接口」 |
| `MANAGE_DEVICE_POLICY_FUN` | policy related to fun. | `fun` 无上下文（AOSP 中为功能限制），取字面「娱乐」，可能偏离本意 |
| `READ_DROPBOX_DATA` | access the data in Dropbox. | `Dropbox` 字面保留。Android 内部 dropbox 日志服务与消费级 Dropbox 同名，直译会误导，未擅自改写 |
| `BIND_VISUAL_VOICEMAIL_SERVICE` | by a link VisualVoicemailService | 原文 "a link" 疑为 "a linked" 笔误，照字面译「链接 VisualVoicemailService」 |
| `USE_PINNED_WINDOWING_LAYER` | ...typically requested via )">ActivityManager... | 原文含 `)">` 乱码残留（抓取时截断的 HTML），按规则未增删，原样保留 |
| `READ_HOME_TIME_ZONE` | read the home time zone. | "home" 取中文惯用的「主」（如主目录），即「主时区」，亦可作「本地时区」 |
| `MANAGE_DEVICE_LOCK_STATE` | financed device kiosk apps | "financed device" 直译「分期设备」，指分期付款设备方案，未补背景 |

## 5. 原文本身极短 / 有歧义（共 6 条）

| 键 | 英文原文 | 说明 |
| --- | --- | --- |
| `MASTER_CLEAR` | Not for use by third-party applications. | 仅一句禁令，无功能描述 |
| `UNINSTALL_SHORTCUT` | Don't use this permission in your app. | 同上，是劝阻而非描述 |
| `SET_ANIMATION_SCALE` | Modify the global animation scaling factor. | 无主语，祈使句直译 |
| `SET_DEBUG_APP` | Configure an application for debugging. | 无主语 |
| `FACTORY_TEST` | Run as a manufacturer test application, running as the root user. | 无主语，两个 "running as" 叠用 |
| `CONFIGURE_WIFI_DISPLAY` | ...connect to Wifi displays | 原文句末无句号，译文亦未补 |
| `PERSISTENT_ACTIVITY` | ...please do not use. Allow an application to... | 一条里混了弃用声明与功能描述，按原文顺序与断句照译 |

## 6. 术语处理

app→应用、permission→权限、device→设备、user→用户、package→包、service→服务、
provider→提供程序、activity→Activity、manifest→清单；keyguard→键盘锁、scoped storage→分区存储、
instant app→免安装应用、profile→配置文件、app→应用。
专名保留英文：`WallpaperService`、`AccountAuthenticator`、`HidManager`、`AppSearch`、`Thread`、
`Assistant`、`Private Compute Core`、`SystemUI`、`Beam`；`bluetooth`/`wifi` 等一律作专名保留原大小写。
