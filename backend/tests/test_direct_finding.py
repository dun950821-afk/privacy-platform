"""Direct Finding：具备完整风险语义的观察直接成结论，不经过关联器。

这是「12 条规则命中、关联层产出 0 条结论」那个问题的直接解药：
AppShark 的 source→sink 数据流本身已是完整结论，不应再要求
「权限 + 数据流 + 关联器」三步才让它出现。
"""
import json
from pathlib import Path

import pytest

from app.services.finding_service import direct_finding_code, is_direct_finding_observation

FIXTURE = Path(__file__).parent / "fixtures" / "appshark" / "task_553" / "observations.json"


@pytest.fixture(scope="module")
def baseline():
    return json.loads(FIXTURE.read_text())


def _obs(**kw):
    base = {"observation_type": "dataflow.privacy", "data_category": None, "sink_type": None,
            "provider_rule_id": None, "result_semantics": None}
    base.update(kw)
    return base


def test_only_direct_semantics_qualify():
    assert is_direct_finding_observation(_obs(result_semantics="direct_finding"))
    assert not is_direct_finding_observation(_obs(result_semantics="supporting_evidence"))
    assert not is_direct_finding_observation(_obs(result_semantics=None))


def test_finding_code_from_category_and_sink():
    """有类目与流向时，结论码由二者构成，与 Provider 规则名无关。"""
    code = direct_finding_code(_obs(data_category="device_information", sink_type="network"))
    assert code == "PRIVACY_DEVICE_INFORMATION_NETWORK"


def test_finding_code_does_not_leak_provider_rule_name():
    """结论码不得包含 Provider 规则名——否则换引擎就得改结论码。"""
    code = direct_finding_code(_obs(data_category="device_information", sink_type="network",
                                    provider_rule_id="DeviceId_NetworkTransfer"))
    assert "DeviceId" not in code
    assert "NetworkTransfer" not in code


def test_security_rule_without_category_still_gets_a_code():
    """安全规则没有数据类目，但仍是完整结论——这正是类目不能决定是否成结论的证据。"""
    code = direct_finding_code(_obs(observation_type="security.other", sink_type="file",
                                    provider_rule_id="unZipSlip"))
    assert code
    assert "UNZIPSLIP" in code


def test_language_is_not_leaked_into_finding_code():
    """结论码必须稳定可读，不能把中文描述拼进去。"""
    code = direct_finding_code(_obs(data_category="clipboard", sink_type="log"))
    assert code == "PRIVACY_CLIPBOARD_LOG"


def test_baseline_flows_all_qualify_as_direct(baseline):
    """基线里每一条数据流规则都应被判定为 direct——它们是完整结论。"""
    from app.services.appshark_semantic_registry import semantics_for
    rules = {o["payload"].get("rule") for o in baseline["observations"]
             if o["observation_type"] == "dataflow.privacy"}
    checked = 0
    for r in rules:
        if not r:
            continue
        sem = semantics_for(r)
        obs = _obs(result_semantics=sem["result_type"], data_category=sem["data_category"],
                   sink_type=sem["sink_type"], provider_rule_id=r)
        if sem["result_type"] == "direct_finding" and sem["data_category"]:
            assert is_direct_finding_observation(obs), "%s 应为 direct" % r
            checked += 1
    assert checked >= 2, "基线应至少含两条可成结论的数据流规则，实际 %d" % checked
