"""跨引擎 Observation 关联和去重规则。"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import logging

from sqlalchemy.orm import Session

from app.models import Rule, RuleVersion
from app.services.rule_evaluator import (
    RuleValidationError, evaluate_join_rule, evaluate_rule)

logger = logging.getLogger(__name__)

# 置信度阶梯：由证据来源数量与独立性决定，不是固定增量（设计文档 §8）
CONFIDENCE_LADDER = ("medium", "medium_high", "high")
# 1.0 的旧词表只用于比较历史 Finding，不再由新规则产出
LEGACY_CONFIDENCE_RANK = {"possible": "medium", "probable": "medium_high", "confirmed": "high"}


@dataclass
class CorrelationResult:
    """一次关联的全部产出。

    分成两类是刻意的：findings 会新建结论，enrichments 只增强已有结论。
    混在一个列表里，调用方迟早会把增强当成结论写进去（设计 §3.2）。
    """
    findings: list[dict] = field(default_factory=list)
    enrichments: list[dict] = field(default_factory=list)


def observation_dedup_key(observation: dict) -> str:
    payload = {"type": observation.get("observation_type"), "subject": observation.get("subject"),
               "payload": observation.get("payload")}
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_active_rules(db: Session) -> list[dict]:
    """读取已发布的关联规则。"""
    rows = db.query(Rule, RuleVersion).join(
        RuleVersion, Rule.current_version_id == RuleVersion.id
    ).filter(Rule.category == "correlation", Rule.status == "active").all()
    return [{"rule": rule, "version": version, "content": version.rule_content or {}}
            for rule, version in rows]


def _rule_label(entry: dict) -> str:
    rule = entry.get("rule")
    return str(getattr(rule, "rule_key", None) or getattr(rule, "id", "unknown"))


def enrichment_confidence(anchor: list[dict], evidence: list[dict]) -> str:
    """按证据来源的独立性给出置信度（设计 §8）。

    仅单一数据流 → medium；+ 同类目事实证据（同引擎）→ medium_high；
    + 另一引擎独立印证 → high。
    """
    anchor_engines = {o.get("engine_type") for o in anchor if o.get("engine_type")}
    evidence_engines = {o.get("engine_type") for o in evidence if o.get("engine_type")}
    if evidence_engines - anchor_engines:
        return "high"
    return "medium_high" if evidence else "medium"


def stronger_confidence(current: str | None, candidate: str) -> str:
    """取更强的取值。历史词表按等价档位换算，避免旧结论被无谓降级。"""
    def rank(value):
        if value in CONFIDENCE_LADDER:
            return CONFIDENCE_LADDER.index(value)
        return CONFIDENCE_LADDER.index(LEGACY_CONFIDENCE_RANK.get(value, "medium"))

    if candidate is None:
        return current
    if current is None:
        return candidate
    return candidate if rank(candidate) > rank(current) else current


def _enrichment(entry: dict, content: dict, match: dict) -> dict:
    anchor = match["anchor"]
    evidence = match["evidence"]
    return {
        "key_values": match["key_values"],
        "anchor_observation_id": anchor["id"],
        "evidence_observation_ids": sorted(o["id"] for o in evidence if o.get("id")),
        "confidence": enrichment_confidence([anchor], evidence),
        "correlation_rule_id": str(entry["rule"].id),
        "correlation_rule_version": entry["version"].version,
        "rule_snapshot": content,
    }


def correlate(observations: list[dict], rules: list[dict]) -> CorrelationResult:
    """按 schema_version 分派：1.0 产出结论，2.0 产出证据增强。"""
    result = CorrelationResult()
    for entry in rules:
        content = entry["content"]
        is_v2 = content.get("schema_version") == "2.0"
        try:
            matched = evaluate_join_rule(content, observations) if is_v2 else evaluate_rule(content, observations)
        except RuleValidationError as exc:
            # 单条规则内容非法只跳过该规则，不能让整个任务的关联结果为空
            logger.warning(f"跳过无效关联规则 {_rule_label(entry)}: {exc}")
            continue
        if not matched:
            continue
        if is_v2:
            result.enrichments.extend(_enrichment(entry, content, group) for group in matched)
            continue
        produce = content.get("produce") or {}
        standards = content.get("standards") or {}
        key = sha256((produce.get("finding_code", "") + "|" + "|".join(
            str(o.get("id", observation_dedup_key(o))) for o in matched)).encode()).hexdigest()
        result.findings.append({
            "finding_code": produce.get("finding_code"),
            "title": produce.get("title"),
            "category": produce.get("category"),
            "severity": produce.get("severity", "medium"),
            "confidence": produce.get("confidence", "medium"),
            "recommendation": produce.get("recommendation"),
            "masvs_controls": standards.get("masvs", []),
            "maswe_ids": standards.get("maswe", []),
            "mastg_test_ids": standards.get("mastg", []),
            "cwe_ids": standards.get("cwe", []),
            "correlation_rule_id": str(entry["rule"].id),
            "correlation_rule_version": entry["version"].version,
            "rule_snapshot": content,
            "dedup_key": key,
            "observation_ids": [o.get("id") for o in matched if o.get("id")],
        })
    return result
