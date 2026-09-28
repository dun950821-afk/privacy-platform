"""task 553 回归基线。

`tests/fixtures/appshark/task_553/observations.json` 是改造前固化的真实引擎产物，
基线固定于 commit bfeea4a 之后的规则集（20 条），实测命中 12 条。

**本文件的保护范围（重要，勿误解）**

这些测试断言的是 **fixture 自身的内容**，不是当前代码的行为。它们能发现：

- 基线数据被误改或截断
- 元信息缺失导致基线无法追溯
- 基线中数据流观察缺少 source/sink

它们**不能**发现：

- 代码改动导致规则不再命中

后者需要**重跑真实任务并与基线对比**，属于集成验证，不在本文件范围。
改造 Task 2..4 之后，必须对 app_version 12 重跑一次真实任务，把命中规则集合
与 `EXPECTED_RULES` 逐条比对；不一致即为覆盖回归。

之所以分开说明：把 fixture 断言当作代码回归保护，会在代码真正回归时给出
虚假的安心感——这正是本项目此前吃过一次的亏。
"""
import json
from collections import Counter
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "appshark" / "task_553" / "observations.json"

# 改造前在该样本上真实命中的 12 条规则。任何一条消失都说明覆盖回归。
EXPECTED_RULES = {
    "InstalledApps_APICall", "Network_APICall", "DeviceId_APICall", "DeviceId_Log",
    "Wifi_APICall", "MAC", "Sensor_APICall", "CameraMic_APICall",
    "Clipboard_APICall", "DeviceId_FileWrite", "unZipSlip", "PendingIntentMutable",
}

EXPECTED_OBSERVATIONS = 139


@pytest.fixture(scope="module")
def fixture():
    assert FIXTURE.exists(), "回归基线缺失：%s" % FIXTURE
    return json.loads(FIXTURE.read_text())


def test_baseline_metadata_is_complete(fixture):
    """基线必须自带可追溯元信息，否则无法判断它对应哪个 APK 与引擎版本。"""
    meta = fixture["_meta"]
    for key in ("apk_sha256", "engine_type", "engine_version", "rule_pack_version",
                "raw_result_hash", "observation_count"):
        assert meta.get(key), "基线缺少 %s" % key
    assert meta["observation_count"] == EXPECTED_OBSERVATIONS
    assert len(fixture["observations"]) == EXPECTED_OBSERVATIONS


def test_baseline_rule_coverage_does_not_regress(fixture):
    """改造不得减少命中的规则数。

    这是本基线的核心断言：任何一条曾经命中的规则消失，都说明规则加载或
    语义归一化改造引入了覆盖回归。
    """
    fired = Counter(o["payload"].get("rule") for o in fixture["observations"]
                    if o["payload"].get("rule"))
    missing = EXPECTED_RULES - set(fired)
    assert not missing, "以下规则在基线中命中但清单未收录，或清单已过期: %s" % missing
    assert len(fired) == len(EXPECTED_RULES), (
        "命中规则数从 %d 变为 %d: %s" % (len(EXPECTED_RULES), len(fired), sorted(fired)))


def test_baseline_covers_both_compliance_and_security(fixture):
    """基线必须同时含 ComplianceInfo 与 SecurityInfo，否则安全类规则无回归保护。"""
    sections = Counter(o["payload"].get("section") for o in fixture["observations"])
    assert sections.get("ComplianceInfo", 0) > 0
    assert sections.get("SecurityInfo", 0) > 0


def test_baseline_observations_are_wellformed(fixture):
    """每条观察都必须有类型与证据等级，否则归一化层无法处理。"""
    for o in fixture["observations"]:
        assert o["observation_type"], "观察缺少 observation_type: %s" % o.get("id")
        assert o["evidence_level"], "观察缺少 evidence_level: %s" % o.get("id")


def test_baseline_dataflow_carries_source_and_sink(fixture):
    """数据流观察必须带 source 与 sink，否则无法做语义归一化与证据关联。"""
    flows = [o for o in fixture["observations"] if o["observation_type"] == "dataflow.privacy"]
    assert flows, "基线中应存在 dataflow.privacy 观察"
    for o in flows:
        payload = o["payload"]
        assert payload.get("source"), "数据流缺少 source: rule=%s" % payload.get("rule")
        assert payload.get("sink"), "数据流缺少 sink: rule=%s" % payload.get("rule")
