"""关联规则的受控校验与条件求值。"""
import re

ALLOWED_LOGIC = {"all", "any"}
ALLOWED_OPERATORS = {"equals", "contains", "exists"}
ALLOWED_FIELDS = {"subject", "location"}
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


def validate_rule_content(content: dict) -> None:
    _require(isinstance(content, dict), "规则内容必须是对象")
    _require(content.get("schema_version") == "1.0", "不支持的 schema_version")
    match = content.get("match") or {}
    _require(match.get("logic") in ALLOWED_LOGIC, "logic 只能是 all 或 any")
    conditions = match.get("conditions") or []
    _require(len(conditions) > 0, "至少需要一个匹配条件")
    for condition in conditions:
        operator = condition.get("operator")
        _require(operator in ALLOWED_OPERATORS, f"不支持的操作符: {operator}")
        field = condition.get("field")
        _require(field in ALLOWED_FIELDS or _is_payload_field(field), f"不支持的字段: {field}")
        _require(bool(condition.get("observation_type")), "条件缺少 observation_type")
        if operator != "exists":
            _require(condition.get("value") not in (None, ""), "该操作符需要 value")
    produce = content.get("produce") or {}
    _require(bool(FINDING_CODE_RE.match(str(produce.get("finding_code") or ""))), "finding_code 格式错误")
    _require(bool(produce.get("title")), "produce.title 不能为空")
    _require(bool(produce.get("category")), "produce.category 不能为空")
    standards = content.get("standards") or {}
    for value in standards.get("masvs") or []:
        _require(bool(MASVS_RE.match(value)), f"MASVS 标识格式错误: {value}")
    for value in standards.get("maswe") or []:
        _require(bool(MASWE_RE.match(value)), f"MASWE 标识格式错误: {value}")
    for value in standards.get("mastg") or []:
        _require(bool(MASTG_RE.match(value)), f"MASTG 标识格式错误: {value}")


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
