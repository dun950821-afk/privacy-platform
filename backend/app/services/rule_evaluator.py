"""关联规则的受控校验与条件求值。

两套 DSL 并存，由 schema_version 区分，**不靠字段探测**（探测会让「历史结论
可复现」依赖猜测）：

- `1.0`：`match` 条件 + `produce` 结论。字面值匹配，既有规则与历史 Finding 的
  rule_snapshot 都跑在这套上，语义不得改动。
- `2.0`：`anchor` / `where` / `join` / `scope` / `action`。规则里不出现任何具体
  数据类目名，新增类目由同一条规则覆盖，维护量 O(1)（设计文档 §7）。
"""
import re

ALLOWED_LOGIC = {"all", "any"}
ALLOWED_OPERATORS = {"equals", "contains", "exists"}
ALLOWED_FIELDS = {"subject", "location"}
# produce.* 会逐字写入 platform_findings 的定长 NOT NULL 列。校验器必须在这里
# 收口长度，否则一次超长写入会在 generate_findings 的最终 commit 抛错并回滚整个
# 事务，导致该任务(甚至所有任务)的 /platform-findings 接口 500。
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
ALLOWED_CONFIDENCES = {"confirmed", "probable", "possible"}
MAX_FINDING_CODE_LEN = 64     # 列宽 120
MAX_TITLE_LEN = 200           # 列宽 300
MAX_CATEGORY_LEN = 60         # 列宽 80
MAX_RECOMMENDATION_LEN = 2000  # 列类型 Text, 仅防滥用
MASVS_RE = re.compile(r"^MASVS-[A-Z]+-\d+$")
MASWE_RE = re.compile(r"^MASWE-\d{4}$")
MASTG_RE = re.compile(r"^MASTG-[A-Z]+-[A-Z0-9-]+$")
FINDING_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")

SCHEMA_V1 = "1.0"
SCHEMA_V2 = "2.0"

# 2.0：enrich 是证据增强，create 是组合推导（尚未实现，见设计文档 §13）。
# create 被列为合法取值但单独拒绝，这样报错能区分「没实现」与「写错了」。
ALLOWED_ACTIONS = {"enrich", "create"}
# V1 只做 data_category 这一个 join key（设计 §4.5）；未知键必须报错而不是被忽略，
# 因为「键写错」的表现是静默不关联 —— 不报错的话规则看起来是生效的。
ALLOWED_JOIN_KEYS = {"data_category"}
ALLOWED_SCOPE_KEYS = {"app_version_id"}
# 2.0 的置信度由证据来源数量与独立性决定（设计 §8），不是固定增量
ALLOWED_CONFIDENCES_V2 = {"medium", "medium_high", "high"}
# where 能过滤的字段 = 平台语义字段 + 既有结构字段；payload.* 另算
V2_WHERE_FIELDS = {"data_category", "sink_type", "result_semantics", "observation_kind",
                   "provider_rule_id", "provider_level", "subject", "location", "engine_type"}
V2_TOP_LEVEL_KEYS = {"schema_version", "anchor", "where", "join", "scope", "action"}


class RuleValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuleValidationError(message)


def _is_payload_field(field: str) -> bool:
    return isinstance(field, str) and field.startswith("payload.") and len(field) > len("payload.")


def _resolve_field(observation: dict, field: str):
    if _is_payload_field(field):
        value = observation.get("payload") or {}
        for part in field[len("payload."):].split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value
    return observation.get(field)


def _require_bounded_text(value, label: str, limit: int, *, required: bool) -> None:
    """可选/必填文本字段：必须是字符串且不超过列宽允许的长度。"""
    if value is None:
        _require(not required, f"{label} 不能为空")
        return
    _require(isinstance(value, str), f"{label} 必须是字符串")
    if required:
        _require(bool(value.strip()), f"{label} 不能为空")
    _require(len(value) <= limit, f"{label} 超过最大长度 {limit}")


def _require_enum(produce: dict, key: str, allowed: set[str], default: str) -> None:
    """可选枚举字段：缺省时由 correlate 填默认值，一旦出现就必须在受控取值内。"""
    if key not in produce:
        return
    value = produce.get(key)
    _require(isinstance(value, str) and value in allowed,
             f"{key} 只能是 {'/'.join(sorted(allowed))} 之一（缺省为 {default}）")


def _validate_standard_ids(standards: dict, key: str, pattern: re.Pattern, label: str) -> None:
    values = standards.get(key)
    if values is None:
        return
    _require(isinstance(values, (list, tuple)), f"{label} 标识必须是数组")
    for value in values:
        _require(isinstance(value, str) and bool(pattern.match(value)), f"{label} 标识格式错误: {value}")


def validate_rule_content(content: dict) -> None:
    _require(isinstance(content, dict), "规则内容必须是对象")
    version = content.get("schema_version")
    if version == SCHEMA_V1:
        _validate_v1(content)
    elif version == SCHEMA_V2:
        _validate_v2(content)
    else:
        raise RuleValidationError(f"不支持的 schema_version: {version}")


def _validate_v1(content: dict) -> None:
    match = content.get("match") or {}
    _require(isinstance(match, dict), "match 必须是对象")
    logic = match.get("logic")
    _require(isinstance(logic, str) and logic in ALLOWED_LOGIC, "logic 只能是 all 或 any")
    conditions = match.get("conditions") or []
    _require(isinstance(conditions, list), "conditions 必须是数组")
    _require(len(conditions) > 0, "至少需要一个匹配条件")
    for condition in conditions:
        _require(isinstance(condition, dict), "匹配条件必须是对象")
        operator = condition.get("operator")
        _require(isinstance(operator, str) and operator in ALLOWED_OPERATORS, f"不支持的操作符: {operator}")
        field = condition.get("field")
        _require(isinstance(field, str) and (field in ALLOWED_FIELDS or _is_payload_field(field)),
                 f"不支持的字段: {field}")
        _require(bool(condition.get("observation_type")), "条件缺少 observation_type")
        if operator != "exists":
            _require(condition.get("value") not in (None, ""), "该操作符需要 value")
    produce = content.get("produce") or {}
    _require(isinstance(produce, dict), "produce 必须是对象")
    finding_code = str(produce.get("finding_code") or "")
    _require(len(finding_code) <= MAX_FINDING_CODE_LEN, f"finding_code 超过最大长度 {MAX_FINDING_CODE_LEN}")
    _require(bool(FINDING_CODE_RE.match(finding_code)), "finding_code 格式错误")
    _require_bounded_text(produce.get("title"), "produce.title", MAX_TITLE_LEN, required=True)
    _require_bounded_text(produce.get("category"), "produce.category", MAX_CATEGORY_LEN, required=True)
    _require_bounded_text(produce.get("recommendation"), "produce.recommendation",
                          MAX_RECOMMENDATION_LEN, required=False)
    _require_enum(produce, "severity", ALLOWED_SEVERITIES, "medium")
    _require_enum(produce, "confidence", ALLOWED_CONFIDENCES, "possible")
    standards = content.get("standards") or {}
    _require(isinstance(standards, dict), "standards 必须是对象")
    _validate_standard_ids(standards, "masvs", MASVS_RE, "MASVS")
    _validate_standard_ids(standards, "maswe", MASWE_RE, "MASWE")
    _validate_standard_ids(standards, "mastg", MASTG_RE, "MASTG")


def _validate_where(where, label: str) -> None:
    """where 只做筛选，不再冒充关联原语（设计 §7.3）。"""
    if where is None:
        return
    _require(isinstance(where, dict), f"{label} 必须是对象")
    for field, expected in where.items():
        _require(field in V2_WHERE_FIELDS or _is_payload_field(field),
                 f"{label} 不支持的字段: {field}")
        _require(isinstance(expected, (str, bool, int)),
                 f"{label}.{field} 只能是字符串、布尔或数字，收到: {expected!r}")


def _validate_v2(content: dict) -> None:
    unknown = set(content) - V2_TOP_LEVEL_KEYS
    _require(not unknown, f"未知的顶层字段: {sorted(unknown)}")

    anchor = content.get("anchor")
    _require(isinstance(anchor, dict), "anchor 必须是对象")
    _require(set(anchor) <= {"type"}, f"anchor 只接受 type，实际: {sorted(anchor)}")
    _require(isinstance(anchor.get("type"), str) and anchor["type"].strip(), "anchor 缺少 type")

    _validate_where(content.get("where"), "where")

    joins = content.get("join")
    if joins is not None:
        _require(isinstance(joins, list), "join 必须是数组")
        for item in joins:
            _require(isinstance(item, dict), "join 项必须是对象")
            _require(set(item) <= {"type", "on", "where"}, f"join 项存在未知字段: {sorted(item)}")
            _require(isinstance(item.get("type"), str) and item["type"].strip(), "join 项缺少 type")
            on = item.get("on")
            _require(isinstance(on, list) and len(on) > 0, "join 项缺少 on")
            for key in on:
                _require(key in ALLOWED_JOIN_KEYS,
                         f"join on 只支持 {sorted(ALLOWED_JOIN_KEYS)}，收到: {key}")
            _validate_where(item.get("where"), "join.where")

    scope = content.get("scope")
    if scope is not None:
        _require(isinstance(scope, list) and len(scope) > 0, "scope 必须是非空数组")
        for key in scope:
            _require(key in ALLOWED_SCOPE_KEYS, f"不支持的 scope: {key}")

    action = content.get("action")
    _require(isinstance(action, str) and action in ALLOWED_ACTIONS,
             f"action 只能是 {'/'.join(sorted(ALLOWED_ACTIONS))}，收到: {action}")
    if action == "create":
        # 组合推导（设计 §7.2）V1 不实现。存下一条永远不触发的规则，比拒绝保存更糟。
        raise RuleValidationError("action=create（组合推导）V1 尚未实现，见设计文档 §13")


def _condition_matches(condition: dict, observation: dict) -> bool:
    if observation.get("observation_type") != condition["observation_type"]:
        return False
    value = _resolve_field(observation, condition["field"])
    if condition["operator"] == "exists":
        return value is not None
    if value is None:
        return False
    text = str(value)
    if condition["operator"] == "equals":
        return text == str(condition["value"])
    return str(condition["value"]) in text


def _dedup_by_id(observations: list[dict]) -> list[dict]:
    return list({o.get("id", id(o)): o for o in observations}.values())


def evaluate_rule(content: dict, observations: list[dict]) -> list[dict] | None:
    validate_rule_content(content)
    match = content["match"]
    conditions = match["conditions"]
    if match["logic"] == "any":
        hit = [o for o in observations if any(_condition_matches(c, o) for c in conditions)]
        return _dedup_by_id(hit) or None
    matched = []
    for condition in conditions:
        hit = [o for o in observations if _condition_matches(condition, o)]
        if not hit:
            return None
        matched.extend(hit)
    return _dedup_by_id(matched)


# ---------- 2.0：共享语义键 join ----------

def _where_matches(where: dict | None, observation: dict) -> bool:
    for field, expected in (where or {}).items():
        value = _resolve_field(observation, field)
        if value is None:
            return False
        if value == expected:
            continue
        if str(value) != str(expected):
            return False
    return True


def _observations_join(anchor: dict, candidate: dict, keys: list[str]) -> bool:
    """按共享键连接。

    键值为 NULL 时**一律不连接**：`None == None` 会让所有「没有类目」的观察
    连成一团，这正是跨类目误配最隐蔽的形态（旧规则用 `_NetworkTransfer` 子串
    匹配，把设备标识的流算成通讯录的证据，属于同一类错误）。
    """
    for key in keys:
        anchor_value = anchor.get(key)
        if anchor_value is None or anchor_value != candidate.get(key):
            return False
    return True


def evaluate_join_rule(content: dict, observations: list[dict]) -> list[dict] | None:
    """求值 2.0 规则，返回 `[{"anchor": 观察, "evidence": [观察...], "key_values": {...}}]`。

    **每个锚点一条**，各自带自己的证据。不要按连接键把锚点合并成组：同一类目下
    可能已有多条结论（实测 app_version 12：设备标识的数据流分成「落盘」与「日志」
    两条），合并后所有证据会挂到其中一条上，另一条纹丝不动 —— 看起来像「证据不够」，
    实际是分组把两条结论当成了一条。

    只返回**有证据**的锚点：没有新证据就不该动结论的置信度。
    """
    validate_rule_content(content)
    anchor_type = content["anchor"]["type"]
    where = content.get("where")
    joins = content.get("join") or []

    anchors = [o for o in observations
               if o.get("observation_type") == anchor_type and _where_matches(where, o)]
    if not anchors:
        return None

    matched = []
    for anchor in anchors:
        for item in joins:
            keys = item["on"]
            key_values = {k: anchor.get(k) for k in keys}
            if any(value is None for value in key_values.values()):
                continue
            evidence = []
            for candidate in observations:
                if candidate is anchor or candidate.get("id") == anchor.get("id"):
                    continue
                if candidate.get("observation_type") != item["type"]:
                    continue
                if not _where_matches(item.get("where"), candidate):
                    continue
                if not _observations_join(anchor, candidate, keys):
                    continue
                if candidate not in evidence:
                    evidence.append(candidate)
            if evidence:
                matched.append({"anchor": anchor, "evidence": evidence, "key_values": key_values})
    return matched or None
