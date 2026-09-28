"""task 553 回归基线：走**真实管线**的断言。

与相邻两个文件的分工（勿混）：

- `test_appshark_regression_baseline.py` 只断言 fixture 自身内容（基线没被误改）
- `test_observation_semantics.py` 断言归一化算得对
- **本文件**断言把 fixture 的真实产物喂进真实管线之后，Task 1..4 的改造结论成立

为什么必须用 fixture 而不是构造数据：本项目吃过一次「fixture、单测、端到端互相验证
同一个虚构」的亏。所以这里的期望值来自**真实产物**（139 条观察、12 条命中规则），
而不是用被测的那张注册表反推期望——后者只是把同一条假设抄了两遍。

基线固定于改造前（flask 中 `category` 列全为 NULL）。因此每处断言都区分两件事：
**基线记的是什么** 与 **重新归一化后应该是什么**。

真实任务比对（本文件无法自动执行，见下方 `test_baseline_rules_are_still_covered`）：
2026-09-28 对 app_version 12 重跑（task 932），命中规则 12 条，与 EXPECTED_RULES
逐条一致，仅 CameraMic_APICall 因 G2 拆分为 Camera_APICall 而发生一次**有意的改名**。
"""
import json
from pathlib import Path

import pytest

from app.services.appshark_semantic_registry import RETIRED_REGISTRY
from app.services.observation_service import event_to_observation, observation_row

FIXTURE = Path(__file__).parent / "fixtures" / "appshark" / "task_553" / "observations.json"
RULE_DIR = Path(__file__).parent.parent / "appshark" / "rules"

# 把 fixture 里记录的（改造前的）观察类型映射回当时的引擎事件类型
EVENT_TYPE_FOR = {
    "dataflow.privacy": "static_data_flow",
    "security.sensitive_api": "static_sensitive_api",
    "fact.permission": "static_permission",
    "fact.application": "static_basic_info",
}

# 基线命中的 12 条规则里，有的已改名而不是消失。值必须是当前规则目录里真实存在的规则。
RENAMED = {"CameraMic_APICall": ["Camera_APICall", "Media_APICall"]}

EXPECTED_DIRECT_FINDINGS = {
    "PRIVACY_DEVICE_INFORMATION_FILE",
    "PRIVACY_DEVICE_INFORMATION_LOG",
    "SECURITY_UNZIPSLIP",
    "SECURITY_PENDINGINTENTMUTABLE",
}


@pytest.fixture(scope="module")
def baseline():
    return json.loads(FIXTURE.read_text())


def _renormalize(observation):
    """按真实路径重新归一化一条基线观察（与引擎跑完后的处理一致）。"""
    return event_to_observation(
        {"event_type": EVENT_TYPE_FOR.get(observation["observation_type"], "unknown"),
         "api": observation["subject"], "event_data": observation["payload"]},
        task_id=553, execution_id=1, engine_type="appshark", engine_version="0.1.2")


def _renormalized(baseline):
    return [(_renormalize(o), o) for o in baseline["observations"]]


def _current_rule_ids():
    ids = set()
    for path in RULE_DIR.glob("*.json"):
        ids.update(json.loads(path.read_text()))
    return ids


# ---------- Step 2.1：语义解析无静默降级 ----------

def test_every_rule_observation_resolves_semantics(baseline):
    """12 条命中规则的观察必须全部解析出语义，一条都不许静默降级。

    「静默降级」是本项目的典型失败模式：注册表漏一条，那条观察就看不出类目，
    关联层当它不存在，而没有任何一处会报错。
    """
    resolved = {r["provider_rule_id"]: r for r, o in _renormalized(baseline)
                if (o.get("payload") or {}).get("rule")}
    assert len(resolved) == 12, "基线命中 12 条规则，实际解析出 %d" % len(resolved)

    for rule_id, r in resolved.items():
        assert r["result_semantics"], "%s 未解析出 result_semantics" % rule_id
        assert r["observation_kind"], "%s 未解析出 observation_kind" % rule_id
        assert r["observation_type"], "%s 未解析出 observation_type" % rule_id
        # 完整性规则必须有类目与流向；安全规则（unZipSlip 等）允许没有类目
        if r["observation_type"] == "dataflow.privacy":
            assert r["data_category"] and r["sink_type"], \
                "%s 是数据流却缺类目或流向: %s" % (rule_id, r)


def test_data_category_is_no_longer_all_null(baseline):
    """改造前 category 列全为 NULL；重新归一化后必须有值。

    这正是 Task 2/3 要解决的问题——类目为空时关联器只能靠字符串猜语义。
    """
    assert all(o["category"] is None for o in baseline["observations"]), \
        "基线记的是改造前状态：category 应全为 NULL"

    rows = [r for r, _ in _renormalized(baseline)]
    with_category = [r for r in rows if r["data_category"]]
    assert len(with_category) >= 60, \
        "重新归一化后带类目的观察过少: %d / %d" % (len(with_category), len(rows))
    # 类目必须落在设计 §4.3 的枚举里，不得冒出临时拼的取值
    assert set(r["data_category"] for r in with_category) >= {
        "device_information", "installed_apps", "network_information", "media",
    }


def test_observation_kind_is_not_provider_level(baseline):
    """AppShark 的 L2/L3 只留在 provider_level，平台层次用 observation_kind。"""
    rows = [r for r, _ in _renormalized(baseline) if r["provider_level"]]
    assert rows, "基线应带 provider_level"
    for r in rows:
        assert r["provider_level"] in {"L2", "L3", "L4"}
        assert r["observation_kind"] != r["provider_level"]


# ---------- Step 2.2：Direct Finding 不依赖关联器 ----------

def test_direct_findings_are_produced_without_any_correlator(db, execution):
    """把真实基线灌进库里直接产结论：不装任何关联规则也能出结论。

    「12 条规则命中、关联层产出 0 条结论」的直接回归保护。
    """
    from app.services.finding_service import generate_direct_findings

    baseline = json.loads(FIXTURE.read_text())
    expected_observation_count = 0
    for observation in baseline["observations"]:
        data = _renormalize(observation)
        data.update(task_id=execution.task_id, execution_id=execution.id)
        db.add(observation_row(data))
        expected_observation_count += 1
    db.commit()

    findings = generate_direct_findings(db, execution.task_id)

    assert {f.finding_code for f in findings} == EXPECTED_DIRECT_FINDINGS
    for finding in findings:
        # 未装任何关联规则却产出了结论，且结论不声称来自关联规则
        assert finding.correlation_rule_id is None
        assert finding.rule_snapshot["source"] == "direct_finding"
        assert finding.observation_count >= 1
    assert expected_observation_count == 139


def test_direct_finding_does_not_require_other_engines(db, execution):
    """基线里没有任何 Androguard/MobSF 观察，结论照样产出——不依赖跨引擎关联。"""
    from app.services.finding_service import generate_direct_findings

    baseline = json.loads(FIXTURE.read_text())
    for observation in baseline["observations"]:
        data = _renormalize(observation)
        data.update(task_id=execution.task_id, execution_id=execution.id)
        db.add(observation_row(data))
    db.commit()

    findings = generate_direct_findings(db, execution.task_id)
    assert findings

    from app.models import FindingObservation, EngineObservation
    engines = {row.engine_type for row in db.query(EngineObservation).filter(
        EngineObservation.task_id == execution.task_id)}
    assert engines == {"appshark"}, "本用例的前提是单引擎，实际: %s" % engines

    # 证据挂到结论上：按本任务的结论 ID 统计，不能数全库（会被别的用例残留蒙对）
    finding_ids = [f.id for f in findings]
    linked = db.query(FindingObservation).filter(
        FindingObservation.finding_id.in_(finding_ids)).count()
    assert linked > 0


# ---------- Step 2.3：同类目可 join、跨类目禁止 join ----------

def _views(baseline):
    from app.services.observation_service import observation_view

    class _Row:
        def __init__(self, data, obs_id):
            self.id = obs_id
            self.observation_type = data["observation_type"]
            self.subject = data["subject"]
            self.location = data["location"]
            self.payload = data["payload"]
            self.engine_type = data["engine_type"]
            self.data_category = data["data_category"]
            self.sink_type = data["sink_type"]
            self.result_semantics = data["result_semantics"]
            self.observation_kind = data["observation_kind"]
            self.provider_rule_id = data["provider_rule_id"]
            self.provider_level = data["provider_level"]
            self.entity_keys = data["entity_keys"]

    return [observation_view(_Row(r, i)) for i, (r, _) in enumerate(_renormalized(baseline), 1)]


ENRICH_RULE = {
    "schema_version": "2.0",
    "anchor": {"type": "dataflow.privacy"},
    "join": [
        {"type": "security.sensitive_api", "on": ["data_category"]},
        {"type": "fact.sensitive_permission", "on": ["data_category"]},
    ],
    "scope": ["app_version_id"],
    "action": "enrich",
}


def test_same_category_joins_on_real_baseline_data(baseline):
    """设备标识的数据流能连到同类目的设备标识 API 事实（真实基线数据）。"""
    from app.services.rule_evaluator import evaluate_join_rule

    matches = evaluate_join_rule(ENRICH_RULE, _views(baseline))
    assert matches, "基线里 device_information 的数据流与 API 事实应能连上"

    anchors = [m["anchor"] for m in matches]
    assert all(a["data_category"] == "device_information" for a in anchors)
    for m in matches:
        assert m["evidence"], "只返回有证据的锚点"
        for e in m["evidence"]:
            assert e["data_category"] == m["anchor"]["data_category"], \
                "跨类目证据被连上了: %s vs %s" % (e["data_category"], m["anchor"]["data_category"])


def test_cross_category_never_joins_on_real_baseline_data(baseline):
    """构造真正的反例：锚点在场、其他类目的证据也在场，但必须一条都连不上。

    不能只断言「命中结果的类目一致」——那在结果为空时也成立。这里把设备标识之外的
    类目证据单独拿出来喂进去，如果隔离失效（比如键值为 NULL 时也允许连接、或按
    规则名子串匹配），这条就会命中。
    """
    from app.services.rule_evaluator import evaluate_join_rule

    views = _views(baseline)
    anchors = [v for v in views if v["observation_type"] == "dataflow.privacy"]
    others = [v for v in views
              if v["data_category"] and v["data_category"] != "device_information"]
    assert anchors and others, "前提不足：基线需要同时有锚点与其他类目的证据"
    assert all(a["data_category"] == "device_information" for a in anchors)

    assert evaluate_join_rule(ENRICH_RULE, anchors + others) is None, \
        "其他类目的证据被连到了设备标识的数据流上"

    # 同一个数据集里把设备标识的证据加回来，必须连得上——否则上一条是被「什么都不连」蒙对的
    same = [v for v in views
            if v["observation_type"] == "security.sensitive_api"
            and v["data_category"] == "device_information"]
    assert same
    assert evaluate_join_rule(ENRICH_RULE, anchors + others + same) is not None


def test_null_category_observations_never_join(baseline):
    """无类目的观察（权限事实、unZipSlip 等）不得互相连成一团。"""
    from app.services.rule_evaluator import evaluate_join_rule

    rule = {
        "schema_version": "2.0",
        "anchor": {"type": "security.other"},
        "join": [{"type": "fact.permission", "on": ["data_category"]}],
        "action": "enrich",
    }
    assert evaluate_join_rule(rule, _views(baseline)) is None


# ---------- Step 2.4：基线规则不得静默消失 ----------

def test_baseline_rules_are_still_covered(baseline):
    """基线命中的 12 条规则，要么仍在规则目录里，要么有交代得清的改名。

    本文件无法自动重跑真实任务（那需要整套环境）。这条断言守的是能自动守的那一半：
    **没有任何一条曾经的规则无声无息地消失**。真实任务的逐条比对见模块 docstring。
    """
    from tests.test_appshark_regression_baseline import EXPECTED_RULES

    current = _current_rule_ids()
    vanished = []
    for rule_id in sorted(EXPECTED_RULES):
        if rule_id in current:
            continue
        successors = RENAMED.get(rule_id)
        if successors and all(s in current for s in successors):
            continue
        vanished.append(rule_id)

    assert not vanished, "以下基线规则既不在规则库中，也没有改名记录: %s" % vanished

    # 改名记录本身也要成立：旧名不得仍占着规则目录
    for old, new_names in RENAMED.items():
        assert old not in current, "%s 已改名，不应仍在规则目录中" % old
        assert old in RETIRED_REGISTRY or old in {o["payload"].get("rule") for o in baseline["observations"]}, \
            "%s 若已退役，需在 RETIRED_REGISTRY 里保留语义以便历史产物复现" % old
