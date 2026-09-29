# Task 5 报告：iOS 解析器

## 实现了什么

在 `backend/app/services/permission_sources.py` 末尾追加 `parse_ios_protected_resources(json_text: str) -> list[dict]`，
解析 Apple「Protected resources」文档 JSON 中的用法描述键。

规则细节：

- **只收 `*UsageDescription`**，用**后缀匹配**（`title.endswith("UsageDescription")`）而非前缀匹配，
  因为 `NFCReaderUsageDescription` 不带 `NS` 前缀。
- entitlements（`com.apple.developer.*`）与 TCC 服务名**不收**——它们是「能力授权」而非「用户隐私授权」。
- `permission_type` 恒为 `"用法描述键"`，与 `permission_taxonomy.PERMISSION_TYPE_VOCAB` 里 `IOS` 的受控词表
  （唯一取值）一致。
- `capability` 取 `abstract` 数组里各段 `text` 的拼接（跳过非 dict 段，如 `codeVoice`），空则 `None`。
- `grant_mode` 恒为 `None`（iOS 用法描述键没有对应概念）。
- `official_reference` 按 Apple 文档 URL 规则拼 `.../information-property-list/{title.lower()}`。
- `raw_data = {"platform_source": "apple_protected_resources"}`，与另两个解析器的溯源字段命名一致。
- 同名 title 去重；输出按 `permission_name` 排序，保证确定性。

统一行形状的六个顶层键**严格保持**：`permission_name` / `permission_type` / `capability` /
`grant_mode` / `official_reference` / `raw_data`（已用断言验证 set 完全相等，无多余键）。

未抽公共抽象——三个平台格式差异大，各自一个函数（与 Task 3/4 一致）。未新增 import（`json` 已在文件顶部）。

## 测了什么与结果

新增 3 条测试（`backend/tests/test_permission_sources.py` 末尾追加），fixture 为
`backend/tests/fixtures/permission_sources/ios_protected_resources_sample.json`（4 条 reference，其中 1 条非用法描述键）。

1. `test_ios_parse_only_picks_usage_description_keys` — 只挑出 3 个 `*UsageDescription`，`SomeOtherKey` 被跳过。
2. `test_ios_parse_uses_usage_key_type_and_carries_abstract` — `permission_type == "用法描述键"`，
   `capability` 以 abstract 文本开头。
3. `test_ios_parse_accepts_nfc_reader_key` — 钉住后缀匹配：不带 `NS` 前缀的 `NFCReaderUsageDescription` 也必须收进来。

这三条测的是真实解析行为（真 fixture 进、真行字典出），无 mock，断言的是输出而非实现细节。

**结果：**

- 聚焦：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v` → **14 passed**
  （Task 3 的 6 + Task 4 的 5 + 本任务 3）。
- 全量：`cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → **295 passed, 34 warnings in 12.26s**
  （基线 292 → 295，与任务说明一致）。

## TDD 证据

**RED** — 先写 fixture 与测试，此时实现尚不存在：

```
$ cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v -k ios
collecting ... collected 0 items / 1 error
==================================== ERRORS ====================================
ImportError while importing test module '.../tests/test_permission_sources.py'.
tests/test_permission_sources.py:112: in <module>
    from app.services.permission_sources import parse_ios_protected_resources
E   ImportError: cannot import name 'parse_ios_protected_resources' from 'app.services.permission_sources'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.10s ===============================
```

为什么预期失败：这一步还没写实现，模块里自然没有这个符号；测试模块顶部就 import 它，
所以是**收集期** ImportError，`-k ios` 连一条都收集不到。失败原因正是「实现缺失」，不是别的偶然错误。

**GREEN** — 追加实现后：

```
$ cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v
tests/test_permission_sources.py::test_ios_parse_only_picks_usage_description_keys PASSED [ 85%]
tests/test_permission_sources.py::test_ios_parse_uses_usage_key_type_and_carries_abstract PASSED [ 92%]
tests/test_permission_sources.py::test_ios_parse_accepts_nfc_reader_key PASSED [100%]
============================== 14 passed in 0.02s ==============================
```

## 改了哪些文件

| 文件 | 变更 |
| --- | --- |
| `backend/app/services/permission_sources.py` | +34 行，末尾追加 `_IOS_REF` 与 `parse_ios_protected_resources` |
| `backend/tests/test_permission_sources.py` | +31 行（顶部加 `import json`，末尾追加 3 条用例） |
| `backend/tests/fixtures/permission_sources/ios_protected_resources_sample.json` | 新建 |

纯追加：`git diff` 显示无任何已有代码/已有用例被改动（Task 3 的 6 条与 Task 4 的 5 条原样保留）。

## 自审发现

1. **brief 里 `return [r for r in sorted(out, key=...)]` 是冗余的**——`sorted()` 已经返回 list，
   再套一层推导式纯属噪音。已简化为 `return sorted(out, key=lambda r: r["permission_name"])`，
   行为完全一致。其余实现与 brief 逐字一致。
2. **brief Step 5 的期望数字写错了**：原文写「Expected: 11 passed（Task 3 的 5 + Task 4 的 3 + 本任务 3）」，
   既算错了加数（实际 6 + 5），也漏掉了新加的 3。实际为 **14 passed**。以任务说明里的
   基线口径（292 → 295）为准，已对齐。这是 brief 的笔误，未按错误数字行事。
3. 边界探针（非正式测试，用脚本验证未崩）：`{}`、`{"references": null}`、缺 `abstract`、
   `abstract` 只有 `codeVoice` 段、同 title 重复、`title` 为 `null` —— 全部安全返回，无 AttributeError/TypeError。
   其中「引用值为 `null`（非 dict）」这一种会抛 `AttributeError`，但 Apple 的实际 JSON 结构里
   reference 恒为对象，brief 也未要求该防御，按 YAGNI 不加守卫。

## 遗留顾虑

- **无阻塞项。**
- `official_reference` 拼出的 URL 是按 Apple 文档的既有命名规则推的。与鸿蒙那边「不拼猜的链接」
  的处理不同——原因是这里的规则是稳定的（`{Title}.lower()` 直连
  `information-property-list/` 路径），且 brief 明确要求这么拼。真实抓取（Task 7）时建议顺手抽验一两条
  拼接结果是否 200，若发现 Apple 的 URL 规则有例外，此处需回炉。
- `platform_source` 用 `"apple_protected_resources"`，与 `aosp_core_manifest` / `openharmony_docs`
  命名风格对齐；Task 6 的导入服务若按 `platform_source` 映射平台，需把该值登记上。
