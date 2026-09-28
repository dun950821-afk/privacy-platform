"""关联规则的受控校验与条件求值。"""
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
    _require(content.get("schema_version") == "1.0", "不支持的 schema_version")
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
