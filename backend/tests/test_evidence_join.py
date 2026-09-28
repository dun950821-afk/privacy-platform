"""Evidence Join：用共享语义键做证据增强。

形状取自真实产物（app_version 12 / task 625 的 AppShark 观察），注释标了每条
观察在库里的真实样子，避免「单测与真实都基于同一个虚构」。
"""
import json

import pytest

from app.services.correlation import enrichment_confidence
from app.services.rule_evaluator import (
    RuleValidationError, evaluate_join_rule, validate_rule_content)
from app.services.rule_seed import BUILTIN_CORRELATION_RULES


def _rule(**overrides):
    content = {
        "schema_version": "2.0",
        "anchor": {"type": "dataflow.privacy"},
        "where": {"sink_type": "network"},
        "join": [{"type": "security.sensitive_api", "on": ["data_category"]}],
        "scope": ["app_version_id"],
        "action": "enrich",
    }
    content.update(overrides)
    return content


def flow(obs_id=1, category="device_information", engine="appshark", sink="network", **extra):
    """dataflow.privacy：AppShark 的 source→sink 命中，带平台语义字段。"""
    return {"id": obs_id, "observation_type": "dataflow.privacy", "engine_type": engine,
            "subject": "['<com.x.A: java.lang.String getDeviceId(android.content.Context)>->$r0']",
            "data_category": category, "sink_type": sink,
            "result_semantics": "direct_finding", "provider_rule_id": "DeviceId_NetworkTransfer",
            **extra}


def api_fact(obs_id=2, category="device_information", engine="appshark", **extra):
    """security.sensitive_api：同引擎同类目的事实证据（DeviceId_APICall 归一化结果）。"""
    return {"id": obs_id, "observation_type": "security.sensitive_api", "engine_type": engine,
            "subject": "getDeviceId", "data_category": category, "sink_type": None,
            "result_semantics": "supporting_evidence", "provider_rule_id": "DeviceId_APICall",
            **extra}


# ---------- 校验 ----------

def test_valid_enrich_rule_passes():
    validate_rule_content(_rule())


def test_rule_has_no_category_names():
    """规则里不得出现具体类目名，否则维护量回到 O(类目数 × 流向 × 引擎)。"""
    text = json.dumps(_rule(), ensure_ascii=False)
    for category in ("contacts", "location", "device_information", "camera"):
        assert category not in text


@pytest.mark.parametrize("mutate,message", [
    (lambda c: c.pop("anchor"), "anchor"),
    (lambda c: c.pop("action"), "action"),
    (lambda c: c.update(action="delete"), "action"),
    (lambda c: c.update(anchor={}), "anchor"),
    (lambda c: c.update(anchor={"type": ""}), "anchor"),
    (lambda c: c.update(where={"sink": "network"}), "where"),
    (lambda c: c.update(join=[{"type": "security.sensitive_api"}]), "on"),
    (lambda c: c.update(join=[{"on": ["data_category"]}]), "type"),
    (lambda c: c.update(join=[{"type": "x", "on": []}]), "on"),
    (lambda c: c.update(join=[{"type": "x", "on": ["rule_name"]}]), "on"),
    (lambda c: c.update(scope=["app_version_id", "github_run"]), "scope"),
    (lambda c: c.update(joins=[]), "未知"),
])
def test_invalid_enrich_rule_is_rejected(mutate, message):
    """非法内容必须在校验期拦下：join key 写错只会静默不关联，不会报错。"""
    content = _rule()
    mutate(content)
    with pytest.raises(RuleValidationError) as exc:
        validate_rule_content(content)
    assert message in str(exc.value)


def test_create_action_is_rejected_until_implemented():
    """V1 不做组合推导（设计 §13）。宁可拒绝保存，也不要存下一条永远不触发的规则。"""
    with pytest.raises(RuleValidationError) as exc:
        validate_rule_content(_rule(action="create"))
    assert "create" in str(exc.value)


# ---------- 求值 ----------

def test_same_category_joins():
    matches = evaluate_join_rule(_rule(), [flow(), api_fact()])
    assert matches is not None
    assert len(matches) == 1
    assert matches[0]["anchor"]["id"] == 1
    assert [o["id"] for o in matches[0]["evidence"]] == [2]
    assert matches[0]["key_values"] == {"data_category": "device_information"}


def test_cross_category_never_joins():
    """通讯录的锚点不得连到设备标识的证据 —— 这正是旧规则犯过的错。"""
    assert evaluate_join_rule(_rule(), [flow(category="contacts"), api_fact(category="device_information")]) is None
    assert evaluate_join_rule(_rule(), [flow(category="device_information"), api_fact(category="contacts")]) is None


def test_null_key_never_joins_null():
    """类目为 NULL 的观察不得互相连接：NULL == NULL 会把所有无类目观察连成一团。

    这条盯着的是 `evaluate_join_rule` 里的锚点级守卫——唯一一处 NULL 判定。
    去掉它，这条就会命中。
    """
    assert evaluate_join_rule(_rule(where={}), [flow(category=None), api_fact(category=None)]) is None


def test_anchor_with_category_does_not_join_candidate_without_one():
    """锚点有类目、候选没有时同样不得连接（候选侧为 NULL）。"""
    assert evaluate_join_rule(_rule(), [flow(category="device_information"), api_fact(category=None)]) is None


def test_each_anchor_carries_only_its_own_key_evidence():
    """每个锚点只带同键证据，且各自成条 —— 按类目合并会把多条结论当成一条。"""
    observations = [flow(1, "device_information"), flow(2, "location"),
                    api_fact(3, "device_information"), api_fact(4, "location")]
    matches = evaluate_join_rule(_rule(), observations)
    assert [(m["anchor"]["id"], [o["id"] for o in m["evidence"]]) for m in matches] == [(1, [3]), (2, [4])]


def test_where_filters_anchor_and_join_candidates():
    # sink 不是 network 的锚点不参与（真实例：DeviceId_Log / DeviceId_FileWrite）
    assert evaluate_join_rule(_rule(), [flow(sink="log"), api_fact()]) is None
    # join 侧 where 同样生效
    rule = _rule(join=[{"type": "security.sensitive_api", "on": ["data_category"],
                        "where": {"provider_rule_id": "MAC"}}])
    assert evaluate_join_rule(rule, [flow(), api_fact()]) is None
    assert evaluate_join_rule(rule, [flow(), api_fact(provider_rule_id="MAC")]) is not None


def test_no_evidence_means_no_enrichment():
    """锚点命中但没有证据时不产出：没有新证据就不该动置信度。"""
    assert evaluate_join_rule(_rule(), [flow()]) is None


def test_anchor_is_not_its_own_evidence():
    rule = _rule(join=[{"type": "dataflow.privacy", "on": ["data_category"]}], where={"sink_type": "network"})
    assert evaluate_join_rule(rule, [flow()]) is None


def test_no_anchor_match_returns_none():
    assert evaluate_join_rule(_rule(), [api_fact()]) is None


# ---------- 置信度阶梯（设计 §8） ----------

def test_confidence_ladder_by_evidence_sources():
    anchor = [flow(engine="appshark")]
    assert enrichment_confidence(anchor, []) == "medium"
    assert enrichment_confidence(anchor, [api_fact(engine="appshark")]) == "medium_high"
    assert enrichment_confidence(anchor, [api_fact(engine="appshark"), api_fact(engine="androguard")]) == "high"


# ---------- 端到端：增强已有结论，不新增结论 ----------
# 走的是真实入库路径（event_to_observation → observation_row → generate_findings），
# 事件形状取自 appshark 适配器与 task 625 的真实产物。

ENRICH_RULE = next(r for r in BUILTIN_CORRELATION_RULES
                   if r["rule_key"] == "PRIVACY_FLOW_FACT_ENRICHMENT")

ANCHOR_EVENT = {
    "event_type": "static_data_flow", "data_type": "ComplianceInfo",
    "api": "['<com.x.A: java.lang.String getDeviceId(android.content.Context)>->$r0']",
    "caller": "<com.x.A: java.lang.String getDeviceId(android.content.Context)>",
    "event_data": {"section": "ComplianceInfo", "rule": "DeviceId_NetworkTransfer", "level": "L3",
                   "detail": "设备标识符通过网络发送",
                   "sink": ["<com.x.A: java.lang.String b()>->$r8"],
                   "source": ["<com.x.A: java.lang.String getDeviceId(android.content.Context)>->$r8_8"]},
}
EVIDENCE_EVENT = {
    "event_type": "static_sensitive_api", "data_type": "device_id",
    "api": "getDeviceId", "caller": "<com.x.A: java.lang.String getDeviceId(android.content.Context)>",
    "event_data": {"section": "ComplianceInfo", "mode": "APIMode", "rule": "DeviceId_APICall",
                   "level": "L2", "detail": "设备标识符 API 调用", "statement": "getDeviceId()"},
}


def _install_rule(monkeypatch, content):
    """只启用这一条规则。

    不用「往库里写一条规则」的方式：开发库里已经种着同一条内置增强规则，两条
    规则命中同一批观察时测试结果取决于库里还有什么，测的就不是这条规则了。
    """
    from app.services import correlation
    entry = {"rule": type("R", (), {"id": 9001, "rule_key": "TEST_ENRICH"})(),
             "version": type("V", (), {"version": "1.0"})(), "content": content}
    monkeypatch.setattr(correlation, "load_active_rules", lambda db: [entry])
    return entry


def _add_observation(db, execution, event, engine_type="appshark"):
    from app.services.observation_service import event_to_observation, observation_row
    version = "4.1.4" if engine_type == "androguard" else "0.1.2"
    data = event_to_observation(event, task_id=execution.task_id, execution_id=execution.id,
                               engine_type=engine_type, engine_version=version)
    row = observation_row(data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _links(db, finding_id):
    from app.models import FindingObservation
    rows = db.query(FindingObservation).filter(FindingObservation.finding_id == finding_id).all()
    return sorted((r.observation_id, r.relation_type) for r in rows)


def test_enrichment_raises_confidence_and_never_creates_a_finding(db, execution, monkeypatch):
    from app.services.finding_service import generate_findings

    _install_rule(monkeypatch, ENRICH_RULE["content"])
    anchor = _add_observation(db, execution, ANCHOR_EVENT)
    evidence = _add_observation(db, execution, EVIDENCE_EVENT)
    assert anchor.result_semantics == "direct_finding"
    assert anchor.data_category == evidence.data_category == "device_information"

    findings = generate_findings(db, execution.task_id)
    assert [f.finding_code for f in findings] == ["PRIVACY_DEVICE_INFORMATION_NETWORK"]
    finding = findings[0]
    # 单一数据流 → medium；+ 同引擎同类目事实证据 → medium_high
    assert finding.confidence == "medium_high"
    assert _links(db, finding.id) == sorted([(anchor.id, "evidence"), (evidence.id, "enriched_evidence")])
    assert finding.observation_count == 2
    assert finding.rule_snapshot["source"] == "direct_finding"          # 结论来源未被改写
    assert finding.rule_snapshot["enrichments"][0]["confidence"] == "medium_high"

    # 再跑一次：结论数不变、证据不重复挂、快照不重复追加（幂等）
    again = generate_findings(db, execution.task_id)
    assert [f.finding_code for f in again] == ["PRIVACY_DEVICE_INFORMATION_NETWORK"]
    assert _links(db, finding.id) == sorted([(anchor.id, "evidence"), (evidence.id, "enriched_evidence")])
    assert len(finding.rule_snapshot["enrichments"]) == 1


def test_two_enrich_rules_on_same_evidence_do_not_duplicate(db, execution, monkeypatch):
    """两条规则命中同一批证据时不得重复挂：重复 INSERT 主键会让整个任务写库失败。"""
    from app.services import correlation
    from app.services.finding_service import generate_findings

    entry = _install_rule(monkeypatch, ENRICH_RULE["content"])
    second = {"rule": type("R", (), {"id": 9002, "rule_key": "TEST_ENRICH_2"})(),
              "version": type("V", (), {"version": "1.0"})(), "content": ENRICH_RULE["content"]}
    monkeypatch.setattr(correlation, "load_active_rules", lambda db: [entry, second])

    anchor = _add_observation(db, execution, ANCHOR_EVENT)
    evidence = _add_observation(db, execution, EVIDENCE_EVENT)
    findings = generate_findings(db, execution.task_id)
    assert _links(db, findings[0].id) == sorted([(anchor.id, "evidence"), (evidence.id, "enriched_evidence")])


def test_enrichment_without_matching_finding_creates_nothing(db, execution, monkeypatch):
    """只有事实证据、没有对应数据流结论时，增强规则不得凭空造出结论。"""
    from app.services.finding_service import generate_findings

    _install_rule(monkeypatch, ENRICH_RULE["content"])
    _add_observation(db, execution, EVIDENCE_EVENT)
    assert generate_findings(db, execution.task_id) == []


def test_cross_engine_corroboration_reaches_high(db, execution, monkeypatch):
    """另一引擎的同类目证据把置信度推到 high —— 设计 §8 的最高一档。

    真实样本 app_version 11（门户测试 3.4.24）：AppShark 报出 Location_NetworkTransfer，
    Androguard 同时报出 ACCESS_FINE_LOCATION 权限。两者类目同为 location、引擎不同。
    """
    from app.services.finding_service import generate_findings

    _install_rule(monkeypatch, ENRICH_RULE["content"])
    location_event = dict(ANCHOR_EVENT, event_data=dict(ANCHOR_EVENT["event_data"],
                                                        rule="Location_NetworkTransfer"))
    anchor = _add_observation(db, execution, location_event)                     # appshark
    permission = _add_observation(db, execution, {                              # androguard
        "event_type": "static_sensitive_permission", "data_type": "LOCATION",
        "api": "ACCESS_FINE_LOCATION",
        "event_data": {"api": "ACCESS_FINE_LOCATION", "category": "LOCATION",
                       "permission": "ACCESS_FINE_LOCATION", "source": "manifest"},
    }, engine_type="androguard")
    assert permission.data_category == "location"

    findings = generate_findings(db, execution.task_id)
    assert [f.finding_code for f in findings] == ["PRIVACY_LOCATION_NETWORK"]
    assert findings[0].confidence == "high"
    assert _links(db, findings[0].id) == sorted([(anchor.id, "evidence"),
                                                 (permission.id, "enriched_evidence")])


def test_cross_category_evidence_is_not_attached(db, execution, monkeypatch):
    """位置信息的结论不得挂上设备标识的证据。"""
    from app.services.finding_service import generate_findings

    _install_rule(monkeypatch, ENRICH_RULE["content"])
    location_event = dict(ANCHOR_EVENT, event_data=dict(ANCHOR_EVENT["event_data"],
                                                        rule="Location_NetworkTransfer"))
    anchor = _add_observation(db, execution, location_event)
    _add_observation(db, execution, EVIDENCE_EVENT)          # device_information 的事实

    findings = generate_findings(db, execution.task_id)
    assert [f.finding_code for f in findings] == ["PRIVACY_LOCATION_NETWORK"]
    assert _links(db, findings[0].id) == [(anchor.id, "evidence")]
    assert findings[0].confidence == "medium"               # 无同键证据，保持单一数据流
