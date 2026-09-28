# 权限知识库扩充为多平台 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `privacy_kb.permission` 从 103 条纯 Android 扩充为覆盖 Android / 鸿蒙 / iOS 三平台的知识库，且数据可从仓库里的原始来源文件重建。

**Architecture:** 加一个 `platform` 列承载平台维度，`permission_type` 的受控词表按平台各一套。抓取与导入分离——抓取脚本联网把平台原始文件落到 `data/kb/`，导入脚本**不联网**、只读仓库文件解析后 UPSERT。解析器是纯函数（文件文本 → 行字典），导入逻辑独立成服务，两者都能单测。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic / pytest；前端 Vue 3 + element-plus + vue-tsc。

**Spec:** `docs/superpowers/specs/2026-09-28-permission-kb-multi-platform-design.md`

## Global Constraints

- 平台取值只有三个：`ANDROID` / `IOS` / `HARMONYOS`。写入侧必须校验。
- **不得编造任何权限名或说明文本。** 查不到就留空；`capability` 为空是正确结果，界面显示「—」，不许填占位文案。
- **不得为 Android 那 1018 条编造「能力说明」**——AOSP core 清单不提供描述文本（实测仅 16 条可解出）。
- Android 实测 1018 条 `<permission>`：signature 752 / internal 120 / normal 100 / dangerous 43 / role+system+module 3。`permissionGroup` 有 962 条缺失，**不得**用它做功能分类。
- 导入脚本**不联网**；联网只发生在抓取脚本里。
- 导入**不得覆盖人工编辑过的行**（判定见 Task 6）。
- 测试基线：改动前 `cd backend && /tmp/venv/bin/python -m pytest tests/ -q` 为 **269 passed**，收尾时必须仍全绿。
- 后端跑在 `/tmp/venv`，服务无 `--reload`，要验证接口必须先重启 uvicorn。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `backend/alembic/versions/20260928_permission_platform.py` | 加 `platform` 列 + 索引，回填旧行 |
| `backend/app/models/kb.py` | `KBPermission` 加 `platform` 字段 |
| `backend/app/services/permission_taxonomy.py` | 平台词表、`protectionLevel` 映射、可达性判定 |
| `backend/app/services/permission_sources.py` | 三个平台的解析器（纯函数，无 IO） |
| `backend/app/services/permission_import.py` | UPSERT + 幂等 + 不覆盖人工编辑 |
| `scripts/fetch_permission_sources.py` | 联网抓原始文件到 `data/kb/`（一次性） |
| `scripts/import_permissions.py` | CLI：读 `data/kb/` → 调 import 服务 |
| `data/kb/SOURCES.json` | 每个源文件的 URL / 抓取时间 / sha256 |
| `backend/tests/fixtures/permission_sources/` | 三平台样本文件 |
| `backend/tests/test_permission_taxonomy.py` | 词表与映射 |
| `backend/tests/test_permission_sources.py` | 三个解析器 |
| `backend/tests/test_permission_import.py` | 幂等 / 不覆盖人工编辑 |
| `backend/tests/test_permission_platform_api.py` | 平台与可达性筛选、组合校验 |
| `backend/app/api/v1/permissions.py` | 加 `platform` / `applicable` 筛选与平台词表 |
| `backend/app/schemas/__init__.py` | `PermissionCreate` 加 `platform` |
| `frontend/src/utils/dict.ts` | `PLATFORM` 字典 |
| `frontend/src/api/permissions.ts` | 无需改（参数透传） |
| `frontend/src/views/Permissions.vue` | 平台下拉、平台列、「只看应用可申请」 |

---

### Task 1: `platform` 列与迁移

**Files:**
- Create: `backend/alembic/versions/20260928_permission_platform.py`
- Modify: `backend/app/models/kb.py`（`KBPermission` 类，在 `permission_name` 之后加字段）
- Test: `backend/tests/test_permission_platform_migration.py`

**Interfaces:**
- Produces: `privacy_kb.permission.platform` 列（`varchar(20) NOT NULL DEFAULT 'ANDROID'`）；
  模型属性 `KBPermission.platform`。

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_permission_platform_migration.py
"""迁移后旧行必须全部落在 ANDROID 上——它们确实全是 Android 权限。"""
from sqlalchemy import text


def test_platform_column_is_backfilled_to_android(db):
    """迁移时已有的行全部回填 ANDROID。

    **不断言「全表只有 ANDROID」**——后续任务会导入鸿蒙/iOS 的行，那样断言会让
    这条测试在导入之后必然失败（T1 与 T7 都会跑全套回归）。
    """
    nulls = db.execute(text("""
        select count(*) from privacy_kb.permission
        where platform is null or platform = ''
    """)).scalar()
    assert nulls == 0, "不允许有 platform 为空的行"

    legacy = db.execute(text("""
        select platform from privacy_kb.permission
        where permission_name = 'android.permission.CAMERA'
    """)).scalar()
    assert legacy == "ANDROID", "迁移时已存在的旧行必须回填为 ANDROID"


def test_platform_column_is_not_nullable(db):
    nullable = db.execute(text("""
        select is_nullable from information_schema.columns
        where table_schema='privacy_kb' and table_name='permission' and column_name='platform'
    """)).scalar()
    assert nullable == "NO"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_platform_migration.py -v`
Expected: FAIL — `column "platform" does not exist`

- [ ] **Step 3: 写迁移**

```python
# backend/alembic/versions/20260928_permission_platform.py
"""权限知识库增加平台维度。

平台与「权限级别」「功能分类」是三个正交维度，所以单独一列，不塞进
permission_type 或 category——上一轮刚把被覆盖的功能分类从 category 里恢复出来
（AD_ID 的分类一度被写成「三方声明权限」），再塞平台会把刚理干净的字段又搅浑。

DEFAULT 'ANDROID' 让现有 103 行自动回填：它们确实全是 Android 权限。
"""
from alembic import op
import sqlalchemy as sa

revision = "20260928_permission_platform"
down_revision = "20260928_analysis_coverage"
branch_labels = None
depends_on = None

TABLE = "permission"
COLUMN = "platform"


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns "
        "where table_schema='privacy_kb' and table_name=:t"), {"t": TABLE})}
    if COLUMN not in existing:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(20), nullable=False,
                                       server_default="ANDROID"),
                      schema="privacy_kb")
        op.create_index("idx_permission_platform", TABLE, [COLUMN], schema="privacy_kb")


def downgrade():
    op.drop_index("idx_permission_platform", TABLE, schema="privacy_kb")
    op.drop_column(TABLE, COLUMN, schema="privacy_kb")
```

- [ ] **Step 4: 改模型**

在 `backend/app/models/kb.py` 的 `KBPermission` 里，`permission_name` 之后插入一行：

```python
    platform = Column(String(20), nullable=False, default="ANDROID", server_default="ANDROID")
```

- [ ] **Step 5: 跑迁移**

Run: `cd backend && /tmp/venv/bin/alembic upgrade head`
Expected: 输出包含 `Running upgrade 20260928_analysis_coverage -> 20260928_permission_platform`

- [ ] **Step 6: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_platform_migration.py -v`
Expected: 2 passed

- [ ] **Step 7: 回归**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/ -q`
Expected: 271 passed（269 + 新增 2）

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/20260928_permission_platform.py backend/app/models/kb.py backend/tests/test_permission_platform_migration.py
git commit -m "feat(kb): 权限表增加 platform 列，旧行回填 ANDROID"
```

---

### Task 2: 平台词表与可达性判定

**Files:**
- Create: `backend/app/services/permission_taxonomy.py`
- Test: `backend/tests/test_permission_taxonomy.py`

**Interfaces:**
- Produces:
  - `PLATFORMS: tuple[str, str, str]` = `("ANDROID", "IOS", "HARMONYOS")`
  - `PERMISSION_TYPES_BY_PLATFORM: dict[str, tuple[str, ...]]`
  - `ANDROID_PROTECTION_LEVEL_MAP: dict[str, str]`
  - `map_android_protection_level(raw: str) -> str`
  - `is_applicable(platform: str, permission_type: str | None, grant_mode: str | None) -> bool`
  - `validate_permission_type(platform: str, permission_type: str | None) -> None`（非法时抛 `ValueError`）

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_permission_taxonomy.py
"""平台词表与「普通 App 可达」判定。

Android 实测 1018 条里 875 条是签名/系统级——普通 App 声明了也拿不到。
可达性判定收敛在这个模块，API 与页面共用，不各自硬编码。
"""
import pytest

from app.services.permission_taxonomy import (
    ANDROID_PROTECTION_LEVEL_MAP, PERMISSION_TYPES_BY_PLATFORM, PLATFORMS,
    is_applicable, map_android_protection_level, validate_permission_type,
)


def test_platforms_are_exactly_three():
    assert PLATFORMS == ("ANDROID", "IOS", "HARMONYOS")
    assert set(PERMISSION_TYPES_BY_PLATFORM) == set(PLATFORMS)


def test_android_map_covers_the_four_real_levels():
    # 实测清单里出现的主级别就这些
    assert map_android_protection_level("dangerous") == "危险权限"
    assert map_android_protection_level("normal") == "普通权限"
    assert map_android_protection_level("signature") == "签名权限"
    assert map_android_protection_level("internal") == "特殊权限"


def test_android_map_ignores_trailing_flags():
    # 清单里有 `dangerous|privileged` 这种形态，附加标志不影响主级别
    assert map_android_protection_level("dangerous|privileged") == "危险权限"
    assert map_android_protection_level("signature|privileged") == "签名权限"


def test_android_map_of_unknown_level_is_undecided_not_fabricated():
    """没见过的级别标「未标注」，不猜。"""
    assert map_android_protection_level("brand_new_level") == "未标注"


def test_applicable_true_for_dangerous_and_normal():
    assert is_applicable("ANDROID", "危险权限", None) is True
    assert is_applicable("ANDROID", "危险权限（受限）", None) is True
    assert is_applicable("ANDROID", "普通权限", None) is True


def test_applicable_false_for_signature_and_special():
    assert is_applicable("ANDROID", "签名权限", None) is False
    assert is_applicable("ANDROID", "特殊权限", None) is False


def test_harmonyos_applicable_needs_user_grant_or_normal():
    assert is_applicable("HARMONYOS", "normal", "用户授权（user_grant）") is True
    assert is_applicable("HARMONYOS", "system_basic", "用户授权（user_grant）") is True
    assert is_applicable("HARMONYOS", "system_basic", "系统授权（system_grant）") is False


def test_ios_usage_keys_are_all_applicable():
    assert is_applicable("IOS", "用法描述键", None) is True


def test_validate_rejects_android_type_on_ios():
    with pytest.raises(ValueError):
        validate_permission_type("IOS", "危险权限")
    validate_permission_type("IOS", "用法描述键")  # 不抛


def test_validate_rejects_unknown_platform():
    with pytest.raises(ValueError):
        validate_permission_type("WINDOWS", "普通权限")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_taxonomy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.permission_taxonomy'`

- [ ] **Step 3: 写实现**

```python
# backend/app/services/permission_taxonomy.py
"""权限的平台维度：受控词表与「普通 App 可达」判定。

三个平台的权限命名体系与级别体系都不同，所以词表按平台各一套：

    Android    android.permission.CAMERA
    鸿蒙        ohos.permission.CAMERA
    iOS        NSCameraUsageDescription

`permission_type` 曾是 39 个自由文本取值，收敛成 Android 那 8 个之后又被加平台撑开，
所以这里按平台分别受控，写入侧校验只在 validate_permission_type 一处做。
"""

PLATFORMS = ("ANDROID", "IOS", "HARMONYOS")

# 每个平台的 permission_type 受控词表
PERMISSION_TYPES_BY_PLATFORM: dict[str, tuple[str, ...]] = {
    "ANDROID": ("危险权限", "危险权限（受限）", "普通权限", "签名权限",
                "特殊权限", "已弃用权限", "三方声明权限", "未标注"),
    # 鸿蒙文档给的是「权限级别」；授权方式（user_grant/system_grant）走 grant_mode
    "HARMONYOS": ("normal", "system_basic", "system_core"),
    "IOS": ("用法描述键",),
}

# Android protectionLevel 主级别 → permission_type。
# `|` 之后的附加标志（privileged / development / instant 等）只记进 raw_data，
# 不影响主级别。
ANDROID_PROTECTION_LEVEL_MAP = {
    "dangerous": "危险权限",
    "normal": "普通权限",
    "signature": "签名权限",
    "internal": "特殊权限",
    "system": "特殊权限",
    "role": "特殊权限",
    "module": "特殊权限",
}

# 普通 App 真能申请的 Android 类型。实测 1018 条里只有 143 条落在这里。
_ANDROID_APPLICABLE = {"危险权限", "危险权限（受限）", "普通权限"}

# 各平台**解析器自己能产出**的 permission_type 取值。
#
# 导入时用它判「库里已有的值要不要让机器覆盖」：值在集合里 → 机器能自己算出来，
# 让它更新（否则 AOSP 的重新分类永远进不来，全库冻结）；不在集合里 → 那是人工判定的、
# 机器推不出来的知识（如 `已弃用权限`/`危险权限（受限）`/`三方声明权限`），不得覆盖。
PARSER_PRODUCIBLE_TYPES: dict[str, set[str]] = {
    "ANDROID": set(ANDROID_PROTECTION_LEVEL_MAP.values()) | {"未标注"},
    "HARMONYOS": set(PERMISSION_TYPES_BY_PLATFORM["HARMONYOS"]),
    "IOS": set(PERMISSION_TYPES_BY_PLATFORM["IOS"]),
}


def map_android_protection_level(raw: str | None) -> str:
    """protectionLevel → permission_type。

    没见过的级别返回「未标注」——**不猜**。清单里出现过 role/system/module 这类
    只占个位数的级别，猜错比留白更糟。
    """
    if not raw:
        return "未标注"
    main = raw.split("|")[0].strip().lower()
    return ANDROID_PROTECTION_LEVEL_MAP.get(main, "未标注")


def is_applicable(platform: str, permission_type: str | None, grant_mode: str | None) -> bool:
    """这条权限普通 App 有没有可能申请到。

    Android：签名/系统级普通 App 声明了也拿不到，不算可达。
    鸿蒙：用户授权类可达；系统授权类不可达。
    iOS：用法描述键都是开发者要声明的，全可达。
    """
    if platform == "ANDROID":
        return (permission_type or "") in _ANDROID_APPLICABLE
    if platform == "HARMONYOS":
        if grant_mode and "user_grant" in grant_mode:
            return True
        return (permission_type or "") == "normal"
    if platform == "IOS":
        return True
    return False


def validate_permission_type(platform: str, permission_type: str | None) -> None:
    """写入侧校验。非法值抛 ValueError，由 API 层转成 400。"""
    if platform not in PERMISSION_TYPES_BY_PLATFORM:
        raise ValueError(f"platform 只能是：{'、'.join(PLATFORMS)}")
    if permission_type is None:
        return
    allowed = PERMISSION_TYPES_BY_PLATFORM[platform]
    if permission_type not in allowed:
        raise ValueError(
            f"{platform} 的 permission_type 只能是：{'、'.join(allowed)}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_taxonomy.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/permission_taxonomy.py backend/tests/test_permission_taxonomy.py
git commit -m "feat(kb): 权限平台词表与可达性判定"
```

---

### Task 3: Android 解析器

**Files:**
- Create: `backend/app/services/permission_sources.py`
- Create: `backend/tests/fixtures/permission_sources/android_manifest_sample.xml`
- Test: `backend/tests/test_permission_sources.py`

**Interfaces:**
- Consumes: `map_android_protection_level`（Task 2）
- Produces: `parse_android_manifest(xml_text: str) -> list[dict]`，
  每项形如 `{"permission_name", "permission_type", "capability",
  "grant_mode", "official_reference", "raw_data"}`。
  `capability` 恒为 `None`（见 Global Constraints）。

- [ ] **Step 1: 写样本 fixture**

```xml
<!-- backend/tests/fixtures/permission_sources/android_manifest_sample.xml -->
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="android">
    <permission android:name="android.permission.CAMERA"
        android:permissionGroup="android.permission-group.UNDEFINED"
        android:label="@string/permlab_camera"
        android:description="@string/permdesc_camera"
        android:protectionLevel="dangerous" />
    <permission android:name="android.permission.CAMERA"
        android:protectionLevel="dangerous|privileged" />
    <permission android:name="android.permission.ACCESS_NETWORK_STATE"
        android:protectionLevel="normal" />
    <permission android:name="android.permission.BIND_ACCESSIBILITY_SERVICE"
        android:protectionLevel="signature" />
    <permission android:name="android.permission.MANAGE_APP_OPS_MODES"
        android:protectionLevel="signature|privileged|development" />
    <permission android:name="android.permission.CONFIGURE_WIFI_DISPLAY"
        android:protectionLevel="internal" />
</manifest>
```

- [ ] **Step 2: 写失败的测试**

```python
# backend/tests/test_permission_sources.py
"""三个平台的来源文件解析器。纯函数：文本进、行字典出，不碰 IO 也不碰库。"""
from pathlib import Path

from app.services.permission_sources import parse_android_manifest

FIXTURES = Path(__file__).parent / "fixtures" / "permission_sources"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_android_parse_dedupes_by_name():
    """同一权限名在清单里可能出现多次（不同 protectionLevel），按名归并。"""
    rows = parse_android_manifest(_read("android_manifest_sample.xml"))
    names = [r["permission_name"] for r in rows]
    assert len(names) == len(set(names)), "同名不该出两行"
    assert names.count("android.permission.CAMERA") == 1


def test_android_parse_maps_protection_level():
    rows = {r["permission_name"]: r for r in parse_android_manifest(_read("android_manifest_sample.xml"))}
    assert rows["android.permission.CAMERA"]["permission_type"] == "危险权限"
    assert rows["android.permission.ACCESS_NETWORK_STATE"]["permission_type"] == "普通权限"
    assert rows["android.permission.BIND_ACCESSIBILITY_SERVICE"]["permission_type"] == "签名权限"
    assert rows["android.permission.CONFIGURE_WIFI_DISPLAY"]["permission_type"] == "特殊权限"


def test_android_parse_keeps_all_protection_levels_in_raw_data():
    """归并时取更宽的主级别，但出现过哪些级别要留在 raw_data 里备查。"""
    rows = {r["permission_name"]: r for r in parse_android_manifest(_read("android_manifest_sample.xml"))}
    raw = rows["android.permission.CAMERA"]["raw_data"]
    assert sorted(raw["protection_levels_seen"]) == ["dangerous", "dangerous|privileged"]


def test_android_parse_leaves_capability_empty():
    """AOSP core 清单不提供描述文本。留空是正确结果，不填占位。"""
    rows = parse_android_manifest(_read("android_manifest_sample.xml"))
    assert all(r["capability"] is None for r in rows)


def test_android_parse_sets_official_reference():
    rows = {r["permission_name"]: r for r in parse_android_manifest(_read("android_manifest_sample.xml"))}
    assert rows["android.permission.CAMERA"]["official_reference"].startswith(
        "https://developer.android.com/reference/android/Manifest.permission#")


def test_android_parse_duplicate_name_keeps_the_more_restrictive_level():
    """同名但主级别不同时，取**更严**的那一级。

    方向是刻意的：`is_applicable` 拿 `permission_type` 决定「普通 App 能不能申请」，
    把签名级权限报成可达，会让默认视图里混进根本申请不到的条目。

    fixture 里那条 CAMERA 重复项两次声明的主级别都是 `dangerous`，**触发不了这个分支**
    ——所以必须在这里用不同主级别的重名钉住它，否则把 `>` 写成 `<` 也不会有测试变红。
    """
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="android">'
        '<permission android:name="android.permission.DUP" android:protectionLevel="normal" />'
        '<permission android:name="android.permission.DUP" android:protectionLevel="signature" />'
        '</manifest>'
    )
    rows = {r["permission_name"]: r for r in parse_android_manifest(xml)}
    assert rows["android.permission.DUP"]["permission_type"] == "签名权限"
    assert rows["android.permission.DUP"]["raw_data"]["protection_levels_seen"] == ["normal", "signature"]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.permission_sources'`

- [ ] **Step 4: 写实现**

```python
# backend/app/services/permission_sources.py
"""平台权限来源文件的解析器。

纯函数：输入是文件文本，输出是可直接入库的行字典。不联网、不碰数据库，
所以能拿样本文件单测。

每行统一形状：
    {"permission_name", "permission_type", "capability",
     "grant_mode", "official_reference", "raw_data"}
"""
import json
import re
import xml.etree.ElementTree as ET

from app.services.permission_taxonomy import map_android_protection_level

_ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
_ANDROID_REF = ("https://developer.android.com/reference/android/Manifest.permission#")

# Android protectionLevel 的「宽窄」：归并同名条目时取更宽的那个做主级别
_LEVEL_WIDTH = {"normal": 1, "dangerous": 2, "internal": 3,
                "system": 3, "role": 3, "module": 3, "signature": 4}


def _android_level_width(raw: str) -> int:
    return _LEVEL_WIDTH.get((raw or "").split("|")[0].strip().lower(), 0)


def parse_android_manifest(xml_text: str) -> list[dict]:
    """解析 AOSP `core/res/AndroidManifest.xml`。

    注意 capability 恒为 None：实测 1018 条里只有 16 条引用的
    `@string/permdesc_*` 能在 core 的 strings.xml 解出来，绝大多数描述定义在各
    模块自己的资源里。**不编造描述**，留空。
    """
    root = ET.fromstring(xml_text)
    merged: dict[str, dict] = {}
    for el in root:
        if el.tag != "permission":
            continue
        name = el.get(_ANDROID_NS + "name")
        if not name:
            continue
        level = el.get(_ANDROID_NS + "protectionLevel") or ""
        group = el.get(_ANDROID_NS + "permissionGroup")
        hit = merged.get(name)
        if hit is None:
            merged[name] = {
                "permission_name": name,
                "permission_type": map_android_protection_level(level),
                "capability": None,
                "grant_mode": None,
                "official_reference": _ANDROID_REF + name.split(".")[-1],
                "raw_data": {"platform_source": "aosp_core_manifest",
                             "protection_levels_seen": [level] if level else [],
                             "permission_group": group},
                "_width": _android_level_width(level),
            }
            continue
        if level and level not in hit["raw_data"]["protection_levels_seen"]:
            hit["raw_data"]["protection_levels_seen"].append(level)
        if _android_level_width(level) > hit["_width"]:
            hit["_width"] = _android_level_width(level)
            hit["permission_type"] = map_android_protection_level(level)
        if group and not hit["raw_data"].get("permission_group"):
            hit["raw_data"]["permission_group"] = group
    for row in merged.values():
        row.pop("_width", None)
        row["raw_data"]["protection_levels_seen"].sort()
    return [merged[k] for k in sorted(merged)]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`
Expected: 6 passed（全套应为 287 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/permission_sources.py backend/tests/fixtures/permission_sources/ backend/tests/test_permission_sources.py
git commit -m "feat(kb): Android 权限清单解析器"
```

---

### Task 4: 鸿蒙解析器

**Files:**
- Modify: `backend/app/services/permission_sources.py`（追加）
- Create: `backend/tests/fixtures/permission_sources/harmonyos_sample.md`
- Test: `backend/tests/test_permission_sources.py`（追加用例）

**Interfaces:**
- Consumes: 无（独立函数）
- Produces: `parse_harmonyos_doc(md_text: str) -> list[dict]`，形状同 Task 3。

- [ ] **Step 1: 写样本 fixture**

```markdown
<!-- backend/tests/fixtures/permission_sources/harmonyos_sample.md -->
# 开放权限（用户授权）

此列表内所有权限均为用户授权（user_grant）的开放权限，面向所有应用开放。

## ohos.permission.ACCESS_BLUETOOTH

允许应用接入蓝牙并使用蓝牙功能。

包括扫描和发现外围蓝牙设备、与外围蓝牙设备配对和连接等操作。

**权限级别**：normal

**授权方式**：用户授权（user_grant）

**起始版本**：10

## ohos.permission.MEDIA_LOCATION

允许应用访问用户媒体文件中的地理位置信息。

**权限级别**：normal

**授权方式**：用户授权（user_grant）

**起始版本**：7

## ohos.permission.NOT_A_REAL_EXAMPLE_WITHOUT_FIELDS

这条没有结构化字段，应被解析器跳过而不是编造级别。

## ohos.permission.NO_LEVEL_OF_ITS_OWN

这条自己没有权限级别字段。

## 说明

**权限级别**：normal

上面那段是非权限小节。它的级别**不该被前一条借走**——正文只被下一个
`## ohos.permission.X` 收口的话，这段会被吞进前一条，而级别是 search 出来的，
前一条就会带着这里的级别入库。
```

- [ ] **Step 2: 写失败的测试（追加到 `test_permission_sources.py`）**

```python
from app.services.permission_sources import parse_harmonyos_doc


def test_harmonyos_parse_extracts_name_and_level():
    rows = {r["permission_name"]: r for r in parse_harmonyos_doc(_read("harmonyos_sample.md"))}
    assert set(rows) == {"ohos.permission.ACCESS_BLUETOOTH", "ohos.permission.MEDIA_LOCATION"}
    assert rows["ohos.permission.ACCESS_BLUETOOTH"]["permission_type"] == "normal"


def test_harmonyos_parse_captures_description_and_grant_mode():
    rows = {r["permission_name"]: r for r in parse_harmonyos_doc(_read("harmonyos_sample.md"))}
    bt = rows["ohos.permission.ACCESS_BLUETOOTH"]
    assert bt["capability"].startswith("允许应用接入蓝牙")
    assert "user_grant" in bt["grant_mode"]
    assert bt["raw_data"]["since_api"] == "10"


def test_harmonyos_parse_skips_section_without_fields():
    """缺结构化字段的小节跳过——宁可少收，不编造级别。"""
    rows = parse_harmonyos_doc(_read("harmonyos_sample.md"))
    assert all(r["permission_name"] != "ohos.permission.NOT_A_REAL_EXAMPLE_WITHOUT_FIELDS" for r in rows)


def test_harmonyos_parse_does_not_borrow_neighbour_level():
    """自己没有「权限级别」的权限小节，不得借用后面那个非权限小节里的级别。

    正文若只被下一个 `## ohos.permission.X` 收口，`## 说明` 那段会被吞进上一段，
    而级别是 `.search()` 出来的——前一条就会带着邻居的级别入库。
    这正是「宁可少收，不编造」要挡的事。
    """
    rows = parse_harmonyos_doc(_read("harmonyos_sample.md"))
    assert all(r["permission_name"] != "ohos.permission.NO_LEVEL_OF_ITS_OWN" for r in rows)
    assert all(r["capability"] is None or "非权限小节" not in r["capability"] for r in rows)


def test_harmonyos_parse_accepts_multi_segment_permission_names():
    """`ohos.permission.kernel.X` 这类**多段**名必须收得到。

    正则原先写作 `[A-Za-z0-9_]+`，不容许 `.`，于是 kernel.* / cli.* / securityguard.* /
    hsdr.* / sec.* / radio.* / vehicle.* / atomicService.* 整批被静默跳过——
    **实测真实文档里因此丢了 41 条**（742 应为 783）。而「解析条数 > 0」这种断言挡不住它。
    """
    md = (
        "## ohos.permission.kernel.ALLOW_MMAP_READ_ONLY\n\n"
        "允许只读映射内核内存。\n\n"
        "**权限级别**：system_basic\n\n"
        "**授权方式**：系统授权（system_grant）\n\n"
        "**起始版本**：12\n"
    )
    rows = parse_harmonyos_doc(md)
    assert [r["permission_name"] for r in rows] == ["ohos.permission.kernel.ALLOW_MMAP_READ_ONLY"]
    assert rows[0]["permission_type"] == "system_basic"


def test_harmonyos_parse_leaves_official_reference_empty():
    """拼出来的 huawei 文档链接是猜的，很可能 404——错误的官方链接比没有更误导。"""
    rows = parse_harmonyos_doc(_read("harmonyos_sample.md"))
    assert all(r["official_reference"] is None for r in rows)
    assert all(r["raw_data"]["platform_source"] == "openharmony_docs" for r in rows)
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v -k harmonyos`
Expected: FAIL — `ImportError: cannot import name 'parse_harmonyos_doc'`

- [ ] **Step 4: 写实现（追加到 `permission_sources.py`）**

```python
_HARMONY_SECTION = re.compile(r"^##\s+(ohos\.permission\.[A-Za-z0-9_.]+)\s*$", re.M)
_HARMONY_ANY_HEADING = re.compile(r"^(?=##\s)", re.M)
_HARMONY_LEVEL = re.compile(r"\*\*权限级别\*\*\s*[：:]\s*([A-Za-z_]+)")
_HARMONY_GRANT = re.compile(r"\*\*授权方式\*\*\s*[：:]\s*(\S+)")
_HARMONY_SINCE = re.compile(r"\*\*起始版本\*\*\s*[：:]\s*(\S+)")


def parse_harmonyos_doc(md_text: str) -> list[dict]:
    """解析 OpenHarmony 文档里的权限小节（`## ohos.permission.X` + 结构化字段）。

    文档在 `openharmony/docs` 的 AccessToken 目录下按授权级别分文件：
    permissions-for-all.md / -all-user.md / -system-apps*.md / -enterprise-apps.md /
    -mdm-apps.md / restricted-permissions.md。

    **小节里没有「权限级别」字段的跳过**——那多半是说明性内容而非权限条目，
    给这种小节编一个级别会让整批数据不可信。

    **正文一律被下一个 `##` 标题收口，不管那个标题是不是权限**。只认
    `## ohos.permission.X` 会让夹在中间的非权限小节被吞进上一段，而级别是
    `.search()` 在整段里找的——于是一个自己没有「权限级别」的权限小节会**继承邻居的级别**，
    正是「宁可少收，不编造」要挡的事。
    """
    out = []
    for block in _HARMONY_ANY_HEADING.split(md_text):
        m = _HARMONY_SECTION.match(block)      # 必须以 ## ohos.permission.X 开头
        if not m:
            continue
        name = m.group(1)
        body = block[m.end():]
        level_m = _HARMONY_LEVEL.search(body)
        if not level_m:
            continue
        grant_m = _HARMONY_GRANT.search(body)
        since_m = _HARMONY_SINCE.search(body)
        # 正文取到级别字段**匹配到的位置**为止。不用字面量 split：文档若写成
        # `**权限级别:**`（冒号在加粗内），字面量找不到，capability 会变成整段。
        desc = body[:level_m.start()].strip()
        out.append({
            "permission_name": name,
            "permission_type": level_m.group(1).strip(),
            "capability": desc or None,
            "grant_mode": grant_m.group(1).strip() if grant_m else None,
            # 不拼 URL：拼出来的 huawei 文档链接是猜的，很可能 404，
            # 而「错误的官方链接」比没有更误导。溯源信息留在 raw_data。见 Ruling I。
            "official_reference": None,
            "raw_data": {"platform_source": "openharmony_docs",
                         "since_api": since_m.group(1).strip() if since_m else None},
        })
    return out
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v -k harmonyos`
Expected: 6 passed（全套应为 293 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/permission_sources.py backend/tests/fixtures/permission_sources/harmonyos_sample.md backend/tests/test_permission_sources.py
git commit -m "feat(kb): 鸿蒙权限文档解析器"
```

---

### Task 5: iOS 解析器

**Files:**
- Modify: `backend/app/services/permission_sources.py`（追加）
- Create: `backend/tests/fixtures/permission_sources/ios_protected_resources_sample.json`
- Test: `backend/tests/test_permission_sources.py`（追加用例）

**Interfaces:**
- Consumes: 无
- Produces: `parse_ios_protected_resources(json_text: str) -> list[dict]`，形状同 Task 3。

- [ ] **Step 1: 写样本 fixture**

取自 Apple「Protected resources」文档 JSON 的真实结构（`references` 里每个
`*UsageDescription` 一条，`abstract` 是纯数组）：

```json
{
  "references": {
    "doc://com.apple.bundleresources/documentation/BundleResources/Information-Property-List/NSCameraUsageDescription": {
      "title": "NSCameraUsageDescription",
      "abstract": [{"type": "text", "text": "A message that tells the user why the app is requesting access to the device’s camera."}]
    },
    "doc://com.apple.bundleresources/documentation/BundleResources/Information-Property-List/NSMicrophoneUsageDescription": {
      "title": "NSMicrophoneUsageDescription",
      "abstract": [{"type": "text", "text": "A message that tells the user why the app is requesting access to the device’s microphone."}]
    },
    "doc://com.apple.bundleresources/documentation/BundleResources/Information-Property-List/NSCalendarsUsageDescription": {
      "title": "NSCalendarsUsageDescription",
      "abstract": [{"type": "text", "text": "A message that tells the user why the app is requesting access to the user’s calendar data."}]
    },
    "doc://com.apple.bundleresources/documentation/BundleResources/Information-Property-List/SomeOtherKey": {
      "title": "SomeOtherKey",
      "abstract": [{"type": "text", "text": "不是用法描述键，应被跳过。"}]
    }
  }
}
```

- [ ] **Step 2: 写失败的测试（追加）**

```python
from app.services.permission_sources import parse_ios_protected_resources


def test_ios_parse_only_picks_usage_description_keys():
    rows = parse_ios_protected_resources(_read("ios_protected_resources_sample.json"))
    names = {r["permission_name"] for r in rows}
    assert names == {"NSCameraUsageDescription", "NSMicrophoneUsageDescription",
                     "NSCalendarsUsageDescription"}
    assert "SomeOtherKey" not in names


def test_ios_parse_uses_usage_key_type_and_carries_abstract():
    rows = {r["permission_name"]: r for r in parse_ios_protected_resources(
        _read("ios_protected_resources_sample.json"))}
    cam = rows["NSCameraUsageDescription"]
    assert cam["permission_type"] == "用法描述键"
    assert cam["capability"].startswith("A message that tells the user")


def test_ios_parse_accepts_nfc_reader_key():
    """NFCReaderUsageDescription 不带 NS 前缀，但确实是用法描述键。"""
    payload = json.dumps({"references": {
        "doc://x/NFCReaderUsageDescription": {
            "title": "NFCReaderUsageDescription",
            "abstract": [{"type": "text", "text": "用于 NFC 读取。"}]}}})
    rows = parse_ios_protected_resources(payload)
    assert [r["permission_name"] for r in rows] == ["NFCReaderUsageDescription"]
```

（文件顶部补 `import json`。）

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v -k ios`
Expected: FAIL — `ImportError: cannot import name 'parse_ios_protected_resources'`

- [ ] **Step 4: 写实现（追加）**

```python
_IOS_REF = ("https://developer.apple.com/documentation/bundleresources/"
            "information-property-list/")


def parse_ios_protected_resources(json_text: str) -> list[dict]:
    """解析 Apple「Protected resources」文档 JSON 里的用法描述键。

    只收 `*UsageDescription`。entitlements（`com.apple.developer.*`）与 TCC 服务名
    不收——它们是「能力授权」而非「用户隐私授权」，混进来会让 permission_type 的
    语义变浑（见 spec §3.3）。

    注意 `NFCReaderUsageDescription` 不带 `NS` 前缀，所以用后缀匹配而非前缀匹配。
    """
    data = json.loads(json_text)
    out = []
    seen = set()
    for ref in (data.get("references") or {}).values():
        title = (ref.get("title") or "").strip()
        if not title.endswith("UsageDescription") or title in seen:
            continue
        seen.add(title)
        abstract = ref.get("abstract") or []
        text = "".join(p.get("text", "") for p in abstract if isinstance(p, dict)).strip()
        out.append({
            "permission_name": title,
            "permission_type": "用法描述键",
            "capability": text or None,
            "grant_mode": None,
            "official_reference": _IOS_REF + title.lower(),
            "raw_data": {"platform_source": "apple_protected_resources"},
        })
    return [r for r in sorted(out, key=lambda r: r["permission_name"])]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`
Expected: 14 passed（Task 3 的 6 + Task 4 的 5 + 本任务 3；全套 295 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/permission_sources.py backend/tests/fixtures/permission_sources/ios_protected_resources_sample.json backend/tests/test_permission_sources.py
git commit -m "feat(kb): iOS 用法描述键解析器"
```

---

### Task 6: 导入服务（幂等 + 不覆盖人工编辑）

**Files:**
- Create: `backend/app/services/permission_import.py`
- Test: `backend/tests/test_permission_import.py`

**Interfaces:**
- Consumes: `PLATFORMS`、`validate_permission_type`（Task 2）
- Produces:
  - `SOURCE_LABEL = "permission-import:{platform}"`
  - `import_platform(db, platform: str, rows: list[dict]) -> dict`
    返回 `{"inserted": int, "updated": int, "skipped": int}` 并**自行 commit**。

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_permission_import.py
"""导入服务：幂等，且不覆盖人工编辑过的行。

权限说明是人工在界面上维护的资产，重跑一次导入就把它冲掉是不可接受的。
"""
from sqlalchemy import text

from app.services.permission_import import SOURCE_LABEL, import_platform

P = "test.import.perm."


def _row(name, **kw):
    base = {"permission_name": name, "permission_type": "普通权限", "capability": None,
            "grant_mode": None, "official_reference": None, "raw_data": {}}
    base.update(kw)
    return base


def _cleanup(db):
    db.execute(text("delete from privacy_kb.import_batch where source_file like 'permission-import:test%'"))
    db.execute(text("delete from privacy_kb.permission where permission_name like :p"), {"p": P + "%"})
    db.commit()


def test_import_inserts_then_is_idempotent(db):
    """重跑相同内容必须是无操作。

    注意 `KBPermission.updated_at` 是 default=utcnow 且**没有 onupdate**，ORM 的
    setattr 不会推进它——所以幂等不能靠时间戳，必须靠**内容比较**：
    与库中一致就不算更新。
    """
    _cleanup(db)
    try:
        rows = [_row(P + "a"), _row(P + "b")]
        first = import_platform(db, "ANDROID", rows)
        assert first == {"inserted": 2, "updated": 0, "skipped": 0}

        second = import_platform(db, "ANDROID", rows)
        assert second == {"inserted": 0, "updated": 0, "skipped": 2}, "重跑不该有任何变化"
    finally:
        _cleanup(db)


def test_import_does_not_overwrite_human_edited_row(db):
    """人工改过的行必须被跳过——这是这套导入能被反复执行的前提。"""
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [_row(P + "c", capability="机器写的")])
        db.execute(text("""
            update privacy_kb.permission set capability='人工改的', updated_at=now()
            where permission_name=:n"""), {"n": P + "c"})
        db.commit()

        result = import_platform(db, "ANDROID", [_row(P + "c", capability="机器写的")])
        assert result["skipped"] == 1
        assert result["updated"] == 0

        cap = db.execute(text("select capability from privacy_kb.permission where permission_name=:n"),
                         {"n": P + "c"}).scalar()
        assert cap == "人工改的", "人工编辑被覆盖了"
    finally:
        _cleanup(db)


def test_import_updates_row_that_import_itself_wrote(db):
    """导入自己写的行要能更新（否则第一版写错了就永远修不回来）。"""
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [_row(P + "d", capability="v1")])
        result = import_platform(db, "ANDROID", [_row(P + "d", capability="v2")])
        assert result == {"inserted": 0, "updated": 1, "skipped": 0}
    finally:
        _cleanup(db)


def test_import_writes_audit_batch_named_per_platform(db):
    _cleanup(db)
    try:
        import_platform(db, "IOS", [_row(P + "e", permission_type="用法描述键")])
        n = db.execute(text("select count(*) from privacy_kb.import_batch where source_file=:s"),
                       {"s": SOURCE_LABEL.format(platform="IOS")}).scalar()
        assert n == 1
    finally:
        _cleanup(db)


def test_import_skips_row_with_type_outside_platform_vocabulary(db):
    """一行脏取值不该毁掉整批，但也不许进库——跳过并计数。

    （API 侧是另一回事：用户手工写非法类型直接 400，见 Task 8。）
    """
    _cleanup(db)
    try:
        result = import_platform(db, "IOS", [_row(P + "f", permission_type="危险权限")])
        assert result == {"inserted": 0, "updated": 0, "skipped": 1}
        left = db.execute(text("select count(*) from privacy_kb.permission where permission_name=:n"),
                          {"n": P + "f"}).scalar()
        assert left == 0, "词表外的行不该进库"
    finally:
        _cleanup(db)


def test_import_accepts_rows_with_empty_capability(db):
    """Android 大多数行没有说明文本——空值必须能正常入库。"""
    _cleanup(db)
    try:
        result = import_platform(db, "ANDROID", [_row(P + "g", capability=None)])
        assert result["inserted"] == 1
        cap = db.execute(text("select capability from privacy_kb.permission where permission_name=:n"),
                         {"n": P + "g"}).scalar()
        assert cap is None
    finally:
        _cleanup(db)


def test_import_survives_duplicate_name_in_one_batch(db):
    """同一批里出现同名，不得让整批回滚。

    `autoflush=False` 让循环里的查询看不到本批 pending 的行，第二次 INSERT 会撞
    `permission_name` 的全局唯一键，把**整批连同审计行**一起回滚——查不到、也不知道
    发生过。上游鸿蒙解析器按计划不做去重（跨文件去重留给调用方），所以这道守卫
    必须在导入器里，不能单点依赖调用方。
    """
    _cleanup(db)
    try:
        rows = [_row(P + "dup", capability="第一次"), _row(P + "dup", capability="第二次")]
        result = import_platform(db, "ANDROID", rows)
        assert result == {"inserted": 1, "updated": 0, "skipped": 1}
        n = db.execute(text("select count(*) from privacy_kb.permission where permission_name=:n"),
                       {"n": P + "dup"}).scalar()
        assert n == 1, "同名只该进库一条"
    finally:
        _cleanup(db)


def test_import_lets_parser_recoverable_type_update(db):
    """解析器自己能算出来的取值，机器**应当**能更新它。

    这条与 `test_import_does_not_overwrite_human_permission_type` 是一对，钉住保护的范围：
    保护只该覆盖「机器推不出来」的值。若写成「只要非空就不覆盖」，解析器从不返回空，
    首跑之后每行都非空 —— AOSP 的重新分类永远进不来，全库冻结在这个字段上，
    而 `is_applicable` 正是从它推的。
    """
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [_row(P + "u", permission_type="普通权限")])
        result = import_platform(db, "ANDROID", [_row(P + "u", permission_type="危险权限")])
        assert result == {"inserted": 0, "updated": 1, "skipped": 0}
        got = db.execute(text("select permission_type from privacy_kb.permission where permission_name=:n"),
                         {"n": P + "u"}).scalar()
        assert got == "危险权限", "机器能算出来的值应当可被更新"
    finally:
        _cleanup(db)


def test_import_does_not_blank_existing_value_with_none(db):
    """解析结果为 None 的字段不得把库中已有的值抹掉。

    AOSP 解析器按设计输出 capability=None（清单不提供描述文本），而库里 103 行
    ANDROID 的 capability 与 grant_mode **全部**是人工整理的成果，其中 81 行的
    权限名与 AOSP 清单重叠。少了这层保护，首次导入就会把它们静默抹成 NULL——
    而首次导入没有基线可挡。
    """
    _cleanup(db)
    try:
        import_platform(db, "ANDROID", [
            _row(P + "h", capability="人工整理的能力说明", grant_mode="运行时授权")])

        # 模拟 AOSP 解析器：同一权限名，但 capability/grant_mode 都是 None
        result = import_platform(db, "ANDROID",
                                 [_row(P + "h", capability=None, grant_mode=None)])
        assert result == {"inserted": 0, "updated": 0, "skipped": 1}, "内容没有实质变化，不该算更新"

        row = db.execute(text("""
            select capability, grant_mode from privacy_kb.permission where permission_name=:n
        """), {"n": P + "h"}).mappings().first()
        assert row["capability"] == "人工整理的能力说明", "已有值被 NULL 抹掉了"
        assert row["grant_mode"] == "运行时授权", "已有值被 NULL 抹掉了"
    finally:
        _cleanup(db)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_import.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.permission_import'`

- [ ] **Step 3: 写实现**

```python
# backend/app/services/permission_import.py
"""把解析出来的权限行写进知识库。

两条硬规则：

1. **幂等**——按 permission_name UPSERT，重跑不重复插入。
2. **不覆盖人工编辑**——说明文本是人工在界面上维护的资产。判定基线取
   `import_batch` 里该平台最近一次导入的 finished_at；updated_at 晚于基线即视为
   人工改过，跳过。
"""
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.kb import KBPermission, KBImportBatch
from app.services.permission_taxonomy import PLATFORMS, validate_permission_type

logger = logging.getLogger(__name__)

SOURCE_LABEL = "permission-import:{platform}"

_UPDATABLE = ("permission_type", "category", "capability", "grant_mode",
              "compliance_focus", "official_reference")


def _last_import_finished_at(db: Session, platform: str):
    return db.query(KBImportBatch.finished_at).filter(
        KBImportBatch.source_file == SOURCE_LABEL.format(platform=platform),
        KBImportBatch.finished_at.isnot(None),
    ).order_by(KBImportBatch.finished_at.desc()).limit(1).scalar()


def import_platform(db: Session, platform: str, rows: list[dict]) -> dict:
    """把一个平台的行 UPSERT 进库。自行 commit 并写审计批次。"""
    if platform not in PLATFORMS:
        raise ValueError(f"platform 只能是：{'、'.join(PLATFORMS)}")

    batch = KBImportBatch(source_file=SOURCE_LABEL.format(platform=platform),
                          import_mode="UPSERT", status="RUNNING",
                          statistics={"platform": platform})
    db.add(batch)
    db.flush()

    baseline = _last_import_finished_at(db, platform)
    seen_names: set[str] = set()
    inserted = updated = skipped = 0

    # 本批统一用一个**数据库时钟**时刻：既作 INSERT 行的 updated_at，又作 batch.finished_at。
    #
    # 为什么不能只把 finished_at 换成 `select now()`：`now()` 是**事务开始**时刻，比 flush 还早；
    # 而 INSERT 行的 updated_at 若留在 ORM 的 Python 默认值上（应用时钟、flush 时才求值），
    # 实测会比 finished_at 晚 +14060 µs —— 于是下一轮把**导入自己写的行**判成「人工改过」
    # 而永不再更新（`test_import_updates_row_that_import_itself_wrote` 正是挡这个）。
    #
    # 两处取同一个值后它们恒等，`updated_at > baseline` 不成立即可更新；
    # 且 UPDATE 路径的行由触发器写 `CURRENT_TIMESTAMP`（= 同一个 DB 时钟），
    # 全程只有一个时钟，应用时钟与数据库时钟的偏差窗口消失。
    db_now = db.execute(text("select now()")).scalar()

    for row in rows:
        # 词表外的取值：跳过并计数，**不中止整批**。1018 行的导入不该死在最后一行；
        # 但也不能放它进库——受控词表就是这么失控的。API 侧（用户写）保持严格抛错。
        try:
            validate_permission_type(platform, row.get("permission_type"))
        except ValueError as exc:
            logger.warning("skip %s: %s", row.get("permission_name"), exc)
            skipped += 1
            continue

        name = (row.get("permission_name") or "").strip()
        if not name:
            skipped += 1        # 空名也要计数，否则审计数字对不上 len(rows)
            continue
        if name in seen_names:
            # 同一批里出现同名：`autoflush=False`（core/database.py）让循环里的查询
            # 看不到本批 pending 的行，第二次 INSERT 会撞 permission_name 的全局唯一键，
            # **整批连同审计行一起回滚且不留痕**——查不到、也不知道发生过。
            # 上游解析器（Android/iOS）各自去重，但鸿蒙那支按计划把跨文件去重留给了
            # 调用方；与其单点依赖调用方，不如在这里挡住。
            skipped += 1
            continue
        seen_names.add(name)

        existing = db.query(KBPermission).filter(KBPermission.permission_name == name).first()
        if existing is None:
            db.add(KBPermission(
                permission_name=name,
                normalized_name=name.lower(),
                platform=platform,
                updated_at=db_now,        # 与 batch.finished_at 同源，见上方注释
                permission_type=row.get("permission_type"),
                category=row.get("category"),
                capability=row.get("capability"),
                grant_mode=row.get("grant_mode"),
                compliance_focus=row.get("compliance_focus"),
                official_reference=row.get("official_reference"),
                raw_data=row.get("raw_data") or {},
            ))
            inserted += 1
            continue

        if existing.platform != platform:
            # 同名跨平台：三个平台的命名空间本不该重叠，撞上说明来源有问题，跳过并留痕
            logger.warning("skip %s: 已存在且 platform=%s", name, existing.platform)
            skipped += 1
            continue

        # 解析结果为 None 的字段**不动既有值**。这不是洁癖：AOSP 解析器按设计输出
        # capability=None（清单不提供描述文本），而库里 103 行 ANDROID 的 capability 与
        # grant_mode **全部**是人工/早期整理的成果，其中 81 行的权限名与 AOSP 清单重叠。
        # 少了这层过滤，首次导入会把它们静默抹成 NULL——而首次导入没有基线可挡。
        incoming = {f: row[f] for f in _UPDATABLE if f in row and row[f] is not None}

        # `permission_type` 另有保护，但**只保护解析器产不出来的取值**。
        #
        # 不能写成「只要非空就不覆盖」：解析器从不返回空，首跑之后每一行都非空，
        # 于是 AOSP 的重新分类**永远进不来**，全库冻结在这个字段上——而 `is_applicable`
        # 正是从它推的，错误会是全库级的。
        #
        # 判据：值在 PARSER_PRODUCIBLE_TYPES[platform] 里 → 机器算得出来，让它更新；
        # 不在 → 那是人工判定的知识（`已弃用权限`/`危险权限（受限）`/`三方声明权限`），
        # 覆盖会把信息不可逆地抹掉并翻转 is_applicable（实测 14 行由不可达翻成可达）。
        if existing.permission_type \
                and existing.permission_type not in PARSER_PRODUCIBLE_TYPES[platform]:
            incoming.pop("permission_type", None)

        incoming_raw = row.get("raw_data") or {}

        # 与库中完全一致 → 无操作。幂等**靠内容比较，不靠时间戳**：
        # updated_at 是 default=utcnow 且没有 onupdate，ORM 的 setattr 不会推进它，
        # 拿它当「导入自己写过」的标志会让每次重跑都算成 updated。
        if all(getattr(existing, f) == v for f, v in incoming.items()) \
                and (existing.raw_data or {}) == incoming_raw:
            skipped += 1
            continue

        if baseline is not None and existing.updated_at and existing.updated_at > baseline:
            skipped += 1        # 内容确有差异，但这一行在上次导入之后被人改过，不覆盖
            continue

        for field, value in incoming.items():
            setattr(existing, field, value)
        existing.raw_data = incoming_raw
        updated += 1

    # **先 flush 落盘再标 SUCCESS**：行全部落盘了才算这批做完。
    db.flush()
    batch.status = "SUCCESS"
    batch.statistics = {"platform": platform, "inserted": inserted,
                        "updated": updated, "skipped": skipped}
    batch.finished_at = db_now
    db.commit()
    return {"inserted": inserted, "updated": updated, "skipped": skipped}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_import.py -v`
Expected: 10 passed（全套应为 306 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/permission_import.py backend/tests/test_permission_import.py
git commit -m "feat(kb): 权限导入服务，幂等且不覆盖人工编辑"
```

---

### Task 7: 抓取脚本、原始文件入仓、实跑导入

**Files:**
- Create: `scripts/fetch_permission_sources.py`
- Create: `scripts/import_permissions.py`
- Create: `data/kb/SOURCES.json`（脚本生成）
- Create: `data/kb/android/AndroidManifest.xml`、`data/kb/harmonyos/*.md`、`data/kb/ios/protected-resources.json`（脚本抓取）

**Interfaces:**
- Consumes: `parse_*`（Task 3/4/5）、`import_platform`（Task 6）
- Produces: 落库的三平台数据。

- [ ] **Step 1: 写抓取脚本**

```python
# scripts/fetch_permission_sources.py
"""把三个平台的权限来源抓到 data/kb/。

联网只发生在这里。导入脚本读本地文件，所以数据能从零重建、且复现不依赖网络。

注意：raw.githubusercontent.com 上 openharmony/docs 实测拉不动（60s 超时），
走 GitHub API 的 Accept: application/vnd.github.raw 头可以。AOSP 的走 raw 没问题。
"""
import hashlib
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data" / "kb"
GH_API_RAW = {"Accept": "application/vnd.github.raw"}

SOURCES = [
    ("android", "AndroidManifest.xml",
     "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/master/core/res/AndroidManifest.xml", {}),
    ("harmonyos", "permissions-for-all.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-all.md", GH_API_RAW),
    ("harmonyos", "permissions-for-all-user.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-all-user.md", GH_API_RAW),
    ("harmonyos", "permissions-for-system-apps.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-system-apps.md", GH_API_RAW),
    ("harmonyos", "permissions-for-system-apps-no-acl.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-system-apps-no-acl.md", GH_API_RAW),
    ("harmonyos", "permissions-for-system-apps-user.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-system-apps-user.md", GH_API_RAW),
    ("harmonyos", "permissions-for-enterprise-apps.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-enterprise-apps.md", GH_API_RAW),
    ("harmonyos", "permissions-for-mdm-apps.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-mdm-apps.md", GH_API_RAW),
    ("harmonyos", "restricted-permissions.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/restricted-permissions.md", GH_API_RAW),
    ("ios", "protected-resources.json",
     "https://developer.apple.com/tutorials/data/documentation/bundleresources/protected-resources.json", {}),
]


def main():
    manifest = []
    for platform, filename, url, headers in SOURCES:
        target = ROOT / platform / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
        except Exception as exc:                      # 抓不到就记下来，不静默跳过
            print(f"  FAILED {platform}/{filename}: {exc}")
            manifest.append({"platform": platform, "file": filename, "url": url,
                             "fetched_at": None, "sha256": None, "error": str(exc)})
            continue
        target.write_bytes(body)
        manifest.append({"platform": platform, "file": filename, "url": url,
                         "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         "sha256": hashlib.sha256(body).hexdigest(),
                         "bytes": len(body)})
        print(f"  ok {platform}/{filename} {len(body)} bytes")

    (ROOT / "SOURCES.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [m for m in manifest if m.get("error")]
    print(f"\n抓取完成 {len(manifest) - len(failed)}/{len(manifest)}；失败 {len(failed)} 条")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑抓取**

Run: `cd /home/user/privacy-platform && /tmp/venv/bin/python scripts/fetch_permission_sources.py`
Expected: 逐行 `ok ...`；`data/kb/` 下出现三平台目录与 `SOURCES.json`。
**把失败的条目原样记下**，报告里要列。

- [ ] **Step 3: 写导入 CLI**

```python
# scripts/import_permissions.py
"""读 data/kb/ 的原始文件，解析后导入知识库。不联网。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                     # noqa: E402
from app.services.permission_import import import_platform      # noqa: E402
from app.services.permission_sources import (                   # noqa: E402
    parse_android_manifest, parse_harmonyos_doc, parse_ios_protected_resources,
)

KB = pathlib.Path(__file__).resolve().parent.parent / "data" / "kb"


def _load(platform):
    if platform == "ANDROID":
        return parse_android_manifest((KB / "android" / "AndroidManifest.xml").read_text(encoding="utf-8"))
    if platform == "HARMONYOS":
        rows, seen = [], set()
        for f in sorted((KB / "harmonyos").glob("permissions-for-*.md")) + \
                 sorted((KB / "harmonyos").glob("restricted-permissions.md")):
            for r in parse_harmonyos_doc(f.read_text(encoding="utf-8")):
                if r["permission_name"] not in seen:        # 跨文件去重（同一权限可能出现在多个文件）
                    seen.add(r["permission_name"])
                    rows.append(r)
        return rows
    if platform == "IOS":
        return parse_ios_protected_resources((KB / "ios" / "protected-resources.json").read_text(encoding="utf-8"))
    raise ValueError(platform)


def main():
    db = SessionLocal()
    try:
        for platform in ("ANDROID", "HARMONYOS", "IOS"):
            rows = _load(platform)
            result = import_platform(db, platform, rows)
            print(f"{platform:10s} 解析 {len(rows):5d} 条  ->  {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑导入**

Run: `cd /home/user/privacy-platform && /tmp/venv/bin/python scripts/import_permissions.py`
Expected: 三行输出；`ANDROID` 解析约 1018 条（去重后略少）；`HARMONYOS`、`IOS` 各若干。

- [ ] **Step 5: 核对落库结果**

Run:
```bash
PGPASSWORD=privacy123 psql -h localhost -U privacy -d privacy_platform -c "
select platform, count(*), count(capability) as 有说明 from privacy_kb.permission group by 1 order by 1;"
```
Expected: `ANDROID` 行数约为 1018 + 原有 103；(有说明) 很小——**这是预期的**，不是 bug。

- [ ] **Step 6: 再跑一次验证幂等**

Run: `cd /home/user/privacy-platform && /tmp/venv/bin/python scripts/import_permissions.py`
Expected: 三行里 `inserted` 均为 0。

- [ ] **Step 7: 回归**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/ -q`
Expected: 全绿（Task 1 之后应为 271 + 新增用例数）

- [ ] **Step 8: Commit**

```bash
git add scripts/fetch_permission_sources.py scripts/import_permissions.py data/kb/
git commit -m "feat(kb): 三平台权限来源抓取与导入脚本，原始文件入仓"
```

---

### Task 8: API 加平台与可达性维度

**Files:**
- Modify: `backend/app/api/v1/permissions.py`
- Modify: `backend/app/schemas/__init__.py`（`PermissionCreate`、`PermissionUpdate`）
- Test: `backend/tests/test_permission_platform_api.py`

**Interfaces:**
- Consumes: `PLATFORMS`、`PERMISSION_TYPES_BY_PLATFORM`、`is_applicable`、`validate_permission_type`（Task 2）
- Produces: `GET /permissions?platform=&applicable=`；`GET /permissions/meta?platform=`

- [ ] **Step 1: 写失败的测试**

```python
# backend/tests/test_permission_platform_api.py
"""权限接口的平台维度。"""
import pytest
from sqlalchemy import text

from app.services.permission_import import import_platform

P = "test.platform.api."


def _cleanup(db):
    db.execute(text("delete from privacy_kb.permission where permission_name like :p"), {"p": P + "%"})
    db.commit()


@pytest.fixture
def seeded(db):
    _cleanup(db)
    import_platform(db, "ANDROID", [
        {"permission_name": P + "danger", "permission_type": "危险权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
        {"permission_name": P + "sig", "permission_type": "签名权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
    ])
    import_platform(db, "IOS", [
        {"permission_name": P + "camera", "permission_type": "用法描述键", "capability": "拍照片",
         "grant_mode": None, "official_reference": None, "raw_data": {}},
    ])
    yield
    _cleanup(db)


def test_meta_returns_platform_specific_vocabulary(client, admin_headers):
    android = client.get("/api/v1/permissions/meta", headers=admin_headers,
                         params={"platform": "ANDROID"}).json()["data"]
    ios = client.get("/api/v1/permissions/meta", headers=admin_headers,
                     params={"platform": "IOS"}).json()["data"]
    assert "危险权限" in android["permission_types"]
    assert ios["permission_types"] == ["用法描述键"]
    assert "危险权限" not in ios["permission_types"]


def test_list_filters_by_platform(client, admin_headers, db, seeded):
    got = client.get("/api/v1/permissions", headers=admin_headers,
                     params={"platform": "IOS", "keyword": P}).json()["data"]
    assert [i["permission_name"] for i in got["items"]] == [P + "camera"]
    assert got["items"][0]["platform"] == "IOS"


def test_applicable_filter_excludes_signature_level(client, admin_headers, db, seeded):
    """Android 那 875 条签名/系统级默认不进版面。"""
    got = client.get("/api/v1/permissions", headers=admin_headers,
                     params={"platform": "ANDROID", "applicable": "true", "keyword": P}).json()["data"]
    names = [i["permission_name"] for i in got["items"]]
    assert P + "danger" in names
    assert P + "sig" not in names


def test_create_rejects_type_from_another_platform(client, admin_headers, db):
    _cleanup(db)
    try:
        resp = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "bad", "platform": "IOS", "permission_type": "危险权限"})
        assert resp.status_code == 400
    finally:
        _cleanup(db)


def test_create_defaults_to_android(client, admin_headers, db):
    _cleanup(db)
    try:
        resp = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "default", "permission_type": "普通权限"})
        assert resp.status_code == 200
        assert resp.json()["data"]["platform"] == "ANDROID"
    finally:
        _cleanup(db)


def test_ios_row_with_empty_capability_round_trips(client, admin_headers, db):
    _cleanup(db)
    try:
        created = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "nocap", "platform": "IOS", "permission_type": "用法描述键"})
        assert created.status_code == 200
        pid = created.json()["data"]["id"]
        got = client.get(f"/api/v1/permissions/{pid}", headers=admin_headers).json()["data"]
        assert got["capability"] is None
    finally:
        _cleanup(db)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v`
Expected: FAIL — meta 不认 `platform` 参数、列表无 `platform` 字段

- [ ] **Step 3: 改 schema**

在 `backend/app/schemas/__init__.py` 的 `PermissionCreate` 里加字段（`PermissionUpdate` 不动）：

```python
class PermissionCreate(BaseModel):
    """权限知识库新建。permission_name 是对外主键（扫描记录按名字匹配），建后不可改。"""
    permission_name: str
    platform: str = "ANDROID"
    category: Optional[str] = None
    permission_type: Optional[str] = None
    risk_level: Optional[str] = None
    capability: Optional[str] = None
    grant_mode: Optional[str] = None
    compliance_focus: Optional[str] = None
    official_reference: Optional[str] = None
```

- [ ] **Step 4: 改路由**

`backend/app/api/v1/permissions.py`：删掉本文件里的 `PERMISSION_TYPES` 常量，
改从 taxonomy 取；`_brief`/`_detail` 加 `platform`；`_check_type` 换成带 platform 的校验。

```python
from app.services.permission_taxonomy import (
    PERMISSION_TYPES_BY_PLATFORM, PLATFORMS, is_applicable, validate_permission_type,
)
```

```python
def _brief(p: KBPermission) -> dict:
    return {
        "id": p.id, "permission_name": p.permission_name, "platform": p.platform,
        "category": p.category, "permission_type": p.permission_type,
        "risk_level": p.risk_level, "is_active": p.is_active,
    }
```

```python
def _check_type(platform: str, value: str | None):
    try:
        validate_permission_type(platform, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

`/meta` 改为：

```python
@router.get("/meta")
def permission_meta(platform: str = None,
                    user: User = Depends(require_permission("permission:read")),
                    db: Session = Depends(get_db)):
    """受控词表与现有分类取值。platform 给定则只返回该平台的词表。"""
    q = db.query(KBPermission.category).filter(
        KBPermission.category.isnot(None), KBPermission.category != "")
    if platform:
        q = q.filter(KBPermission.platform == platform)
    categories = sorted({r[0] for r in q.all()})
    types = (PERMISSION_TYPES_BY_PLATFORM.get(platform) if platform
             else tuple(t for ts in PERMISSION_TYPES_BY_PLATFORM.values() for t in ts))
    return {"code": 0, "data": {
        "platforms": list(PLATFORMS),
        "permission_types": list(dict.fromkeys(types)),
        "risk_levels": list(RISK_LEVELS),
        "categories": categories,
    }}
```

列表签名与筛选：

```python
@router.get("")
def list_permissions(category: str = None, permission_type: str = None,
                     risk_level: str = None, keyword: str = None,
                     platform: str = None, applicable: bool | None = None,
                     is_active: bool = None, page: int = 1, page_size: int = 50,
                     user: User = Depends(require_permission("permission:read")),
                     db: Session = Depends(get_db)):
    ...
    if platform:
        q = q.filter(KBPermission.platform == platform)

    if applicable is None:
        total = q.count()
        items = q.order_by(KBPermission.permission_name) \
                 .offset((page - 1) * page_size).limit(page_size).all()
    else:
        # 可达性不能只在 SQL 里判：鸿蒙还要看 grant_mode，SQL 里拼不干净。
        # 取全量在 Python 侧过滤，分页放在过滤之后（数据量在千级，可以接受）。
        #
        # **三态**：true = 只看可达，false = 只看**不可达**，不传 = 不筛。
        # 不能写成 `if applicable:`——那样 false 会静默退化成「不筛选」，
        # 调用方明确要「不可达」那一档却拿到全量，是个不报错的错答案。
        rows = [r for r in q.order_by(KBPermission.permission_name).all()
                if is_applicable(r.platform, r.permission_type, r.grant_mode) is applicable]
        total = len(rows)
        items = rows[(page - 1) * page_size: page * page_size]
```

并补一条测试钉住三态：

```python
def test_applicable_filter_is_tri_state(client, admin_headers, db, seeded):
    """`applicable` 必须三态：true 只看可达、false 只看不可达、不传不筛。

    写成 `if applicable:` 的话 false 会退化成「不筛选」——调用方要「不可达」却拿到全量，
    是个不报错的错答案。
    """
    only_reachable = client.get("/api/v1/permissions", headers=admin_headers,
                                params={"platform": "ANDROID", "applicable": "true",
                                        "keyword": P}).json()["data"]["items"]
    only_unreachable = client.get("/api/v1/permissions", headers=admin_headers,
                                  params={"platform": "ANDROID", "applicable": "false",
                                          "keyword": P}).json()["data"]["items"]
    unfiltered = client.get("/api/v1/permissions", headers=admin_headers,
                            params={"platform": "ANDROID", "keyword": P}).json()["data"]["items"]

    assert [i["permission_name"] for i in only_reachable] == [P + "danger"]
    assert [i["permission_name"] for i in only_unreachable] == [P + "sig"]
    assert len(unfiltered) == 2, "不传 applicable 时两行都要在"
```

（`total` 与 `items` 在分支外不再各算一次——把原来那两行推进 else 分支里。）

创建/更新里把 `_check_type(req.permission_type)` 换成带平台的形式。**编辑时平台取自那一行自身**
（`PermissionUpdate` 不含 `platform`——平台是行的身份，和 `permission_name` 一样建后不可改）：

```python
# create_permission 里
    _check_type(req.platform, req.permission_type)
    ...
    p = KBPermission(permission_name=name, platform=req.platform, ...)

# update_permission 里
    _check_type(p.platform, req.permission_type)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v`
Expected: 6 passed

- [ ] **Step 6: 回归**

Run: `cd backend && /tmp/venv/bin/python -m pytest tests/ -q`
Expected: 全绿（`test_permission_kb_api.py` 里的 meta 断言可能需要同步更新——
它现在断言 `len(permission_types) == 8`，不传 platform 时返回的是三平台并集，
**应改为传 `platform=ANDROID` 再断言 8 个**）

- [ ] **Step 7: 重启并手测**

```bash
kill $(ss -ltnp | grep ':8000' | grep -oE 'pid=[0-9]+' | cut -d= -f2) 2>/dev/null; sleep 3
cd /home/user/privacy-platform/backend && setsid nohup /tmp/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn_perm.log 2>&1 < /dev/null &
sleep 8 && curl -s http://localhost:8000/health
```
（服务无 `--reload`，必须重启才加载新代码。）

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/v1/permissions.py backend/app/schemas/__init__.py backend/tests/test_permission_platform_api.py
git commit -m "feat(kb): 权限接口增加平台与可达性筛选"
```

---

### Task 9: 前端平台维度

**Files:**
- Modify: `frontend/src/utils/dict.ts`（加 `PLATFORM`）
- Modify: `frontend/src/views/Permissions.vue`
- Modify: `frontend/src/api/permissions.ts`（`meta` 传 platform）

**Interfaces:**
- Consumes: `GET /permissions?platform=&applicable=`、`GET /permissions/meta?platform=`

- [ ] **Step 1: 加平台字典**

`frontend/src/utils/dict.ts` 末尾追加：

```ts
/** 权限所属平台 */
export const PLATFORM: Dict = {
  ANDROID: { label: 'Android', type: 'success' },
  IOS: { label: 'iOS', type: 'primary' },
  HARMONYOS: { label: '鸿蒙', type: 'warning' },
}
```

- [ ] **Step 2: api 传参**

`frontend/src/api/permissions.ts` 的 `meta` 改为接受参数：

```ts
  meta: (params?: any) => api.get('/permissions/meta', { params }),
```

- [ ] **Step 3: 页面加平台维度**

`frontend/src/views/Permissions.vue`：

筛选栏在关键字后加两个控件：

```html
<el-select v-model="filters.platform" placeholder="全部平台" clearable style="width:130px"
           @change="onPlatformChange">
  <el-option v-for="p in meta.platforms" :key="p" :label="dictLabel(PLATFORM, p)" :value="p" />
</el-select>
<el-checkbox v-model="filters.applicable">只看应用可申请</el-checkbox>
```

表格在「权限名」后加平台列：

```html
<el-table-column label="平台" width="100">
  <template #default="{ row }">
    <StatusTag :value="row.platform" :map="PLATFORM" />
  </template>
</el-table-column>
```

script 里 `meta` 加 `platforms: [] as string[]`；`filters` 加 `platform: ''` 与
`applicable: true`（**默认只看可申请的**，见 spec §6）。

```ts
async function loadMeta() {
  const res: any = await permissionApi.meta(
    filters.platform ? { platform: filters.platform } : undefined)
  meta.platforms = res.data.platforms
  meta.permission_types = res.data.permission_types
  meta.risk_levels = res.data.risk_levels
  meta.categories = res.data.categories
}

function onPlatformChange() {
  // 平台变了，受控词表跟着变；已选的类型可能不再合法，清掉
  filters.permission_type = ''
  loadMeta()
  loadData(1)
}
```

`loadData` 的 query 里加：

```ts
      platform: filters.platform || undefined,
      applicable: filters.applicable || undefined,
```

`resetFilters` 里重置这两项（`platform: ''`、`applicable: true`）。弹窗表单加平台选择
（编辑态禁用，与 `permission_name` 同理）：

```html
<el-form-item label="平台" prop="platform">
  <el-select v-model="form.platform" :disabled="!!editingId" style="width:100%"
             @change="loadMeta">
    <el-option v-for="p in meta.platforms" :key="p" :label="dictLabel(PLATFORM, p)" :value="p" />
  </el-select>
</el-form-item>
```

`form` 加 `platform: 'ANDROID'`，`openCreate`/`resetForm` 恢复成 `'ANDROID'`，
提交 payload 带 `platform: form.platform`；编辑态 payload **不含** platform（后端 PUT 不接受）。

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npx vue-tsc -b`
Expected: 退出码 0，无输出

- [ ] **Step 5: 构建**

Run: `cd frontend && npm run build`
Expected: `✓ built in ...`，`dist/assets/` 下出现 `Permissions-*.js`

- [ ] **Step 6: 手工验证**

打开 `/permissions`：默认「只看应用可申请」已勾选；切到「鸿蒙」，类型下拉变成
`normal/system_basic/system_core`；切回 Android，类型下拉恢复 8 个；取消勾选后
能看到「签名权限」行。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/utils/dict.ts frontend/src/api/permissions.ts frontend/src/views/Permissions.vue
git commit -m "feat(ui): 权限知识库增加平台维度与可达性过滤"
```

---

## 收尾

- [ ] 全部测试通过：`cd backend && /tmp/venv/bin/python -m pytest tests/ -q`
- [ ] 写报告时**必须**包含：三平台各收了多少条、抓取失败的源文件清单、
      「模块级权限未穷尽」的说明、以及 Android 有说明文本的行数占比（预期极低）
- [ ] 备份：`pg_dump` 到 `backup/privacy_platform_<日期>_pre_permission_expand.sql.gz`，
      并还原到临时库核对行数
