# Task 2 报告：平台词表与可达性判定

**Status: DONE**
Commit: `58beace` feat(kb): 权限平台词表与可达性判定
基线 `cececf2` → HEAD `58beace`

---

## 1. 实现了什么

新建 `backend/app/services/permission_taxonomy.py`（80 行），纯模块、无数据库依赖。
严格按 brief 逐字实现，未增删任何接口或分支：

**导出接口（brief 的 5 项全部落地）**

| 名称 | 内容 |
|---|---|
| `PLATFORMS` | `("ANDROID", "IOS", "HARMONYOS")` |
| `PERMISSION_TYPES_BY_PLATFORM` | 三平台各自的受控词表；ANDROID 8 个、HARMONYOS 3 个、IOS 1 个 |
| `ANDROID_PROTECTION_LEVEL_MAP` | 7 个 protectionLevel 主级别 → permission_type |
| `map_android_protection_level(raw)` | 取 `\|` 前主级别、strip+lower；未见过 → `「未标注」`（不猜） |
| `is_applicable(platform, permission_type, grant_mode)` | Android 白名单 / 鸿蒙 `user_grant` 或 `normal` / iOS 恒 True / 未知平台 False |
| `validate_permission_type(platform, permission_type)` | 非法平台与非法取值均抛 `ValueError`，`None` 放行；写入侧唯一校验点 |

关键设计意图（照 brief 落地）：
- **校验只有一处**：词表收敛在此，`validate_permission_type` 是唯一入口，后续 T3–T6、T8 都消费它。
- **不得编造**：`map_android_protection_level` 对没见过的级别返回「未标注」，不猜主级别。
- 附加标志（`privileged` 等）不进主级别映射，只影响 `raw_data`（由 T3 落盘）。

## 2. 测了什么与结果

`backend/tests/test_permission_taxonomy.py`（67 行，brief 逐字），10 个测试：

1. `test_platforms_are_exactly_three` — 三平台常量与词表键集一致
2. `test_android_map_covers_the_four_real_levels` — dangerous/normal/signature/internal 四个实测主级别
3. `test_android_map_ignores_trailing_flags` — `dangerous|privileged`、`signature|privileged` 取主级别
4. `test_android_map_of_unknown_level_is_undecided_not_fabricated` — `brand_new_level` → 「未标注」
5. `test_applicable_true_for_dangerous_and_normal` — 危险/危险（受限）/普通 可达
6. `test_applicable_false_for_signature_and_special` — 签名/特殊 不可达
7. `test_harmonyos_applicable_needs_user_grant_or_normal` — user_grant 可达、system_grant 不可达
8. `test_ios_usage_keys_are_all_applicable` — iOS 全可达
9. `test_validate_rejects_android_type_on_ios` — 跨平台取值被拒、本平台取值放行
10. `test_validate_rejects_unknown_platform` — 未知平台被拒

**结果**
- 聚焦：`10 passed in 0.02s`（无 warning）
- 全量：`281 passed, 34 warnings in 12.15s`
  - 281 = 基线 271 + 新增 10，**与 brief 预期完全一致**
  - 34 warnings 与改动前基线数量相同，全部为仓库既有 SQLAlchemy `LegacyAPIWarning`，非本任务引入

**未使用 mock**：模块是纯函数，测试全部直接断言真实返回值，无一处 mock。

## 3. TDD 证据

### RED
命令：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_taxonomy.py -v`

```
collected 0 items / 1 error
ERROR collecting tests/test_permission_taxonomy.py
tests/test_permission_taxonomy.py:8: in <module>
    from app.services.permission_taxonomy import (
E   ModuleNotFoundError: No module named 'app.services.permission_taxonomy'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.18s ===============================
```

**为什么预期失败**：测试模块在导入期就 `from app.services.permission_taxonomy import ...`，
而该生产模块此时**尚不存在**，导入必然失败、收集阶段即报错——这正是 brief Step 2 预期的
`ModuleNotFoundError`。（此处是纯新增模块，没有"已存在但逻辑错"的中间态，所以 RED 表现为收集失败而非断言失败。）

### GREEN
命令：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_taxonomy.py -v`

```
collected 10 items

tests/test_permission_taxonomy.py::test_platforms_are_exactly_three PASSED [ 10%]
tests/test_permission_taxonomy.py::test_android_map_covers_the_four_real_levels PASSED [ 20%]
tests/test_permission_taxonomy.py::test_android_map_ignores_trailing_flags PASSED [ 30%]
tests/test_permission_taxonomy.py::test_android_map_of_unknown_level_is_undecided_not_fabricated PASSED [ 40%]
tests/test_permission_taxonomy.py::test_applicable_true_for_dangerous_and_normal PASSED [ 50%]
tests/test_permission_taxonomy.py::test_applicable_false_for_signature_and_special PASSED [ 60%]
tests/test_permission_taxonomy.py::test_harmonyos_applicable_needs_user_grant_or_normal PASSED [ 70%]
tests/test_permission_taxonomy.py::test_ios_usage_keys_are_all_applicable PASSED [ 80%]
tests/test_permission_taxonomy.py::test_validate_rejects_android_type_on_ios PASSED [ 90%]
tests/test_permission_taxonomy.py::test_validate_rejects_unknown_platform PASSED [100%]

============================== 10 passed in 0.02s ==============================
```

### 额外：变异测试（证明测试断言真实行为，非空跑）
除 RED/GREEN 外，我临时篡改生产模块两处、确认测试能抓到，随后从 git 还原
（`git checkout --`；还原后 `git diff HEAD` 为空、全量复跑仍 281 passed）：

| 变异 | 后果 | 抓住的测试 |
|---|---|---|
| 未知级别回退改 `「普通权限」`（即"猜"） | 1 failed, 9 passed | `test_android_map_of_unknown_level_is_undecided_not_fabricated` |
| 把 `签名权限` 加进 Android 可达白名单 | 2 failed, 8 passed | `test_applicable_false_for_signature_and_special` + 上一条 |

说明测试确实钉住了 brief 最强调的两条约束（不编造、签名权限不可达），不是恒真的空断言。

## 4. 改了哪些文件

仅两个新文件，无任何既有文件改动：

- `backend/app/services/permission_taxonomy.py`（新增，80 行）
- `backend/tests/test_permission_taxonomy.py`（新增，67 行）

`git show --stat 58beace` = 2 files changed, 147 insertions(+)。

**未提交**：工作树里有一个与任务无关的未跟踪文件
`backup/privacy_platform_20260928_pre_kb_fix.sql.gz`（会话早先的数据库备份）。
它不是我建的、也不在 brief 的 add 列表内，**刻意未提交**，保持原位不动。

## 5. 自审发现

用新鲜眼光重读 diff 后的结论：

- **完整性**：brief 的 5 个 Produces 接口全部存在且签名一致；与 progress.md 中
  T3/T6/T8 的消费约定（`map_android_protection_level`、`validate_permission_type(platform, type)`、
  `is_applicable(platform, type, grant_mode)`）逐一比对，一致。
- **命名**：常量与函数名逐字照 brief，与下游任务约定无出入。
- **YAGNI**：实现是 brief 逐字版本，**零额外代码**——没有多加平台、没有给 `is_applicable`
  加默认分支之外的兜底、没有提前抽出"未来可能需要"的辅助函数。这是本任务最容易镀金的地方
  （比如顺手加个 `is_platform` 或给鸿蒙加 `system_core` 特判），我都没有做。
- **测试验证行为而非 mock**：见上，纯函数直断言，另有变异测试佐证。
- **测试输出干净**：聚焦运行无 warning；全量 34 warnings 与基线数量逐一相同，非本任务引入。
- **一处已知瑕疵（不修，见下）**：测试文件 import 了 `ANDROID_PROTECTION_LEVEL_MAP`
  但从未断言它。这是 brief 逐字给定的 import 行，且本仓库**无 ruff/flake8/CI lint 配置**
  （已确认无 `pyproject.toml`/`setup.cfg`/`.flake8`/pre-commit），未使用 import 不会挂任何门禁。
  改它反而偏离"逐字使用 brief 值"的指令，故保留。

## 6. 遗留顾虑

1. **`validate_permission_type` 的 `None` 语义**：函数对 `permission_type=None` 直接放行，
   即"未标注/不适用"永远合法。这符合本模块"只拦非法取值"的定位，但意味着**词表无法强制非空**；
   若 T6 导入或 T8 API 需要"必须填"的约束，得由调用方另做，不能指望这个校验。已确认与本任务
   测试一致（无 `None` 用例），属设计取舍而非缺陷，仅提请下游注意。
2. **`is_applicable` 对未知平台返回 False** —— 静默失败。暂无测试覆盖（brief 未要求）。
   好处是 fail-safe（未知平台不会被误判为可达），代价是拼错平台名时不会报错、只会"全部不可达"。
   平台名的合法性由 `validate_permission_type` 在写入侧兜住，故可接受；若 T8 的查询路径
   先过滤后校验，需留意此差异。
3. **鸿蒙判定的宽松性**：`grant_mode` 用子串匹配 `"user_grant"`，只要该串出现在任意位置即判可达，
   不校验整体格式。对文档原文（如 `用户授权（user_grant）`）够用，但若 T4 抓到脏串
   （例如同时含 `user_grant` 与 `system_grant`）会**偏向可达**。brief 如此规定，未改；
   提请 T4/T6 在写 `grant_mode` 时保证取值干净。
4. 无阻塞项，无需 HELP。

---

**下游可直接消费**：T3 用 `map_android_protection_level`；T6 导入用 `validate_permission_type`
（注意 progress.md Ruling D：导入侧应逐行校验、非法行跳过计数，不整体中止）；
T8 用 `is_applicable` 做 Python 侧可达性筛选。
