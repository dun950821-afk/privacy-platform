"""官方规则的来源与逐条核实记录。

Task 7 的产物是「哪些官方规则真的能检出所声称的问题」。这个结论直接决定
`docs/rule-coverage.md` 里哪些弱点类目算已覆盖，因此不能靠改一个布尔值了事——
本文件守的就是「翻 `verified` 必须留下证据」。
"""
import json
from pathlib import Path

import pytest

PROVENANCE = Path(__file__).parent.parent / "appshark" / "upstream-provenance.json"
RULE_DIR = Path(__file__).parent.parent / "appshark" / "rules"


@pytest.fixture(scope="module")
def provenance():
    return json.loads(PROVENANCE.read_text())


def test_every_rule_records_upstream_source(provenance):
    """来源必须可追溯：改不动上游，至少要能说清是哪一次抓取的。"""
    upstream = provenance.get("upstream") or {}
    for key in ("repo", "commit", "source_path"):
        assert upstream.get(key), "缺少上游来源信息: %s" % key

    for rule in provenance["rules"]:
        assert rule["provider"] == "appshark"
        assert rule["upstream_commit"] == upstream["commit"], \
            "%s 的 commit 与顶层不一致" % rule["provider_rule_id"]
        assert rule["source_file"]
        assert RULE_DIR.joinpath(rule["source_file"]).exists(), \
            "%s 记录的来源文件不存在: %s" % (rule["provider_rule_id"], rule["source_file"])


def test_verified_requires_recorded_evidence(provenance):
    """置 true 必须同时留下样本、取样覆盖与核实说明。

    没有这条，「verified: true」就只是一个说法：它会让覆盖矩阵把一个弱点类目记成
    已覆盖，而依据无从查证。本项目已因「拿触发当成立」吃过一次亏。
    """
    for rule in provenance["rules"]:
        rule_id = rule["provider_rule_id"]
        if not rule["verified"]:
            continue
        assert rule.get("verified_at"), "%s 缺 verified_at" % rule_id
        assert rule.get("verified_sample"), "%s 缺 verified_sample" % rule_id
        assert rule.get("verified_call_sites"), "%s 缺 verified_call_sites" % rule_id
        assert len(rule.get("verification_note") or "") >= 30, \
            "%s 的 verification_note 太短，说明不了核实依据" % rule_id


def test_never_hit_rules_are_not_marked_verified(provenance):
    """从未命中任何真实样本的规则不得标为已验证——没有样本就无从成立。"""
    for rule in provenance["rules"]:
        if rule.get("verified_call_sites") == "0/0":
            assert not rule["verified"], \
                "%s 从未在真实样本上命中，不能标 verified" % rule["provider_rule_id"]


def test_verification_method_is_documented(provenance):
    """判据本身要写下来：否则「已验证」在下次改动时无法复核同一套标准。"""
    method = provenance.get("verification_method") or ""
    assert "字节码" in method or "实现" in method, "未说明核实到哪一层"
    assert "触发" in method, "未说明「触发」不构成 verified"
