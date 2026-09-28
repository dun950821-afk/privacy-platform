"""分析有效性判定。

输入的统计数字取自真实样本的实测值（app_version 8/12，见
`docs/analysis-coverage-design.md` §2），不是编的。
"""
import pytest

from app.services.analysis_coverage import (
    DEGRADED, FULL, UNKNOWN, artifact_verdict, engine_verdict, task_verdict)

# app_version 8（360 加固）：DEX 只声明 4 个类，manifest 声明 225 个组件，全部找不到
PACKED = {"class_count": 4, "method_count": 381, "component_class_total": 225,
          "component_class_missing": 225,
          "component_class_missing_sample": ["androidx.core.content.FileProvider"]}
# app_version 12（营口银行）：8009 个类，23 个组件，1 个缺失（动态特性/别名之类）
NORMAL = {"class_count": 8009, "method_count": 63291, "component_class_total": 23,
          "component_class_missing": 1}


def test_packed_apk_is_degraded():
    verdict, detail = artifact_verdict(PACKED)
    assert verdict == DEGRADED
    assert detail["criterion"] == "component_classes_all_missing"
    assert detail["component_class_total"] == detail["component_class_missing"] == 225


def test_partial_missing_is_not_degraded():
    """个别组件类找不到（别名、插件包）不等于分析没覆盖到应用——不能据此判退化。"""
    verdict, detail = artifact_verdict(NORMAL)
    assert verdict == FULL
    assert detail["component_class_missing"] == 1


def test_missing_input_data_is_unknown_not_full():
    """缺数据必须判 UNKNOWN。把未知当成正常，正是这次故障的成因。"""
    assert artifact_verdict(None)[0] == UNKNOWN
    assert artifact_verdict({})[0] == UNKNOWN
    assert artifact_verdict({"component_class_total": 23})[0] == UNKNOWN
    assert artifact_verdict({"component_class_total": 0, "component_class_missing": 0})[0] == UNKNOWN


def test_engine_verdict_follows_artifact_verdict():
    """APK 侧已判定没覆盖到，任何引擎的结果都不可用。"""
    assert engine_verdict("appshark", {}, DEGRADED)[0] == DEGRADED
    assert engine_verdict("androguard", {"anything": 1}, DEGRADED)[0] == DEGRADED
    assert engine_verdict("appshark", {"scan_stats": {"availableMethods": 999}}, DEGRADED)[0] == DEGRADED


def test_engine_without_self_reported_coverage_is_not_condemned():
    """不报覆盖量的引擎不因此被判退化（它没有声称自己覆盖了多少）。"""
    assert engine_verdict("mobsf", {"tracker_count": 0}, FULL)[0] == FULL
    assert engine_verdict("androguard", {"class_count": 8009}, FULL)[0] == FULL


def test_appshark_without_scan_stats_is_degraded():
    """AppShark 连调用图阶段的统计都没有，说明它没跑到那一步。

    历史数据里有 event_count=0 且 scan_stats 缺失的执行，当时状态是 completed。
    """
    assert engine_verdict("appshark", {}, FULL)[0] == DEGRADED
    assert engine_verdict("appshark", {"scan_stats": {}}, FULL)[0] == DEGRADED
    assert engine_verdict("appshark", {"scan_stats": {"availableMethods": 0, "availableClasses": 0}},
                          FULL)[0] == DEGRADED
    assert engine_verdict("appshark", {"scan_stats": {"availableMethods": 30, "availableClasses": 337}},
                          FULL)[0] == FULL


def test_task_verdict_precedence():
    assert task_verdict([]) == UNKNOWN, "没有引擎结果时不得判 FULL"
    assert task_verdict([FULL, FULL]) == FULL
    assert task_verdict([FULL, UNKNOWN]) == UNKNOWN
    assert task_verdict([FULL, DEGRADED]) == DEGRADED
    assert task_verdict([UNKNOWN, DEGRADED]) == DEGRADED
