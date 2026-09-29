"""语义注册表的完整性与正确性。"""
import json
import glob
import os
import pytest

from app.services.appshark_semantic_registry import (
    REGISTRY, RESULT_DIRECT, RESULT_SUPPORTING, MissingSemanticsError, RETIRED_REGISTRY,
    enrich_observation, semantics_for,
)

RULE_DIR = "appshark/rules"


def _all_provider_rule_ids():
    ids = set()
    for p in glob.glob(os.path.join(RULE_DIR, "*.json")):
        for rid in json.load(open(p)):
            ids.add(rid)
    return ids


def test_registry_covers_every_rule_file():
    """规则目录里每一条规则都必须有语义标注。

    缺一条就静默降级成「无语义」，关联层会看不见它——宁可在测试里失败。
    """
    missing = _all_provider_rule_ids() - set(REGISTRY)
    assert not missing, "以下规则未登记语义: %s" % sorted(missing)


def test_registry_has_no_stale_entries():
    """注册表不得包含规则目录中已不存在的规则，避免清理后残留死映射。"""
    stale = set(REGISTRY) - _all_provider_rule_ids()
    assert not stale, "以下注册项已无对应规则: %s" % sorted(stale)


def test_unknown_rule_raises_instead_of_degrading():
    with pytest.raises(MissingSemanticsError):
        semantics_for("NoSuchRule_v99")


def test_camera_and_media_split_claims_only_what_is_proven():
    """相机/音视频采集的拆分必须停在引擎真正证明的那一层（设计 §4.2）。

    Camera.open 就是打开摄像头，无歧义 → camera。
    MediaRecorder 的音源/视频源、AudioRecord 的音源都是通配参数（可传 Surface、
    REMOTE_SUBMIX），只证明「配置了音视频采集」→ media，不得声称用了摄像头或麦克风。
    """
    assert REGISTRY["Camera_APICall"]["data_category"] == "camera"
    assert REGISTRY["Media_APICall"]["data_category"] == "media"

    sinks = json.load(open(os.path.join(RULE_DIR, "api_media.json")))["Media_APICall"]["sink"]
    assert not any("Camera" in sig for sig in sinks), \
        "Media_APICall 不得包含 Camera API，否则 camera 会被重复声明"
    camera_sinks = json.load(open(os.path.join(RULE_DIR, "api_camera.json")))["Camera_APICall"]["sink"]
    # 2026-09-29 从 camile.json 补入 camera2 的 openCamera 与 androidx 的
    # ImageCapture.takePicture：前者就是打开摄像头，后者就是拍照，与 Camera.open
    # 同属「无歧义」那一类，所以进 camera 这一格。通配参数的那批仍留在 media。
    assert list(camera_sinks) == [
        "<android.hardware.Camera: * open(*)>",
        "<android.hardware.camera2.CameraManager: * openCamera(*)",
        "<androidx.camera.core.ImageCapture: * takePicture(*)",
    ]
    # 这条断言才是本测试真正要守的东西：只要 Camera 里混进通配参数的采集 API，
    # 上面那个集合快照会通过更新来「修好」，这一条不会。
    assert not any("MediaRecorder" in s or "AudioRecord" in s for s in camera_sinks), \
        "通配参数的音视频采集 API 不得混进 camera"


def test_retired_and_current_are_disjoint():
    """同一条规则不可能既在役又退役：重叠说明拆分时漏删了旧登记项。"""
    assert not (set(RETIRED_REGISTRY) & set(REGISTRY))
    assert not (set(RETIRED_REGISTRY) & _all_provider_rule_ids())


def test_retired_rule_still_resolves_for_historical_artifacts():
    """退役规则名仍须可解析，否则历史产物重新归一化会得到与当时不同的语义。

    task 553 基线里记着 CameraMic_APICall（G2 拆分前）。
    """
    assert "CameraMic_APICall" not in _all_provider_rule_ids(), "该规则已退役，不应仍在规则目录中"
    semantics = semantics_for("CameraMic_APICall")
    assert semantics["data_category"] == "media"
    assert semantics["result_type"] == RESULT_SUPPORTING


def test_dataflow_rules_are_direct_findings_with_category_and_sink():
    """数据流规则必须同时有类目与流向，否则无法参与共享键关联。"""
    for rid, sem in REGISTRY.items():
        if sem["observation_type"] == "dataflow.privacy" and rid != "IMEI_SendBroadcast":
            assert sem["result_type"] == RESULT_DIRECT, "%s 应直接成结论" % rid
            assert sem["data_category"], "%s 缺 data_category" % rid
            assert sem["sink_type"], "%s 缺 sink_type" % rid


def test_api_call_rules_are_supporting_evidence():
    """APICall 只证明「调用了 API」，是支撑证据，不得单独成结论。"""
    for rid, sem in REGISTRY.items():
        if rid.endswith("_APICall"):
            assert sem["result_type"] != RESULT_DIRECT, "%s 是事实不是结论" % rid
            assert sem["sink_type"] is None, "%s 无流向" % rid


def test_vulnerability_claim_rules_are_supporting_evidence_only():
    """论断是「存在某个漏洞」的规则只做证据，不直接成结论。

    AppShark 看不穿接口/多态调用，校验可能就在被调用方的实现里（实测
    ContentProviderPathTraversal 的命中是误报，见 docs/appshark-rule-capability.md
    能力边界 2）。因此命中只说明「外部输入流到了 sink」，不说明弱点存在。
    """
    for rid in ("ContentProviderPathTraversal", "IntentRedirectionBabyVersion",
                "PendingIntentMutable", "unZipSlip"):
        sem = semantics_for(rid)
        assert sem["result_type"] == RESULT_SUPPORTING, "%s 不得直接成结论" % rid
        assert sem["data_category"] is None, "%s 不应被强加数据类目" % rid
        assert sem["sink_type"], "%s 仍应记录流向，否则无从判断它是什么类型的弱点" % rid


def test_enrich_sets_shared_join_key():
    """同类目的不同引擎观察必须产出相同的 entity_keys.data_category，才能连接。"""
    flow = enrich_observation({"app_version_id": 12}, "DeviceId_NetworkTransfer")
    api = enrich_observation({"app_version_id": 12}, "DeviceId_APICall")
    assert flow["entity_keys"]["data_category"] == api["entity_keys"]["data_category"]
    assert flow["entity_keys"]["app_version"] == 12


def test_enrich_does_not_cross_categories():
    """不同类目必须产出不同的 join key，否则会跨类目误关联。"""
    device = enrich_observation({"app_version_id": 12}, "DeviceId_NetworkTransfer")
    location = enrich_observation({"app_version_id": 12}, "Location_NetworkTransfer")
    assert device["entity_keys"]["data_category"] != location["entity_keys"]["data_category"]


def test_enrich_omits_null_category_from_keys():
    """无类目的规则不得产出 data_category 键，否则会与别的 None 类目互相连接。"""
    out = enrich_observation({"app_version_id": 12}, "unZipSlip")
    assert "data_category" not in out["entity_keys"]


def test_enrich_is_pure():
    src = {"app_version_id": 12}
    enrich_observation(src, "DeviceId_APICall")
    assert src == {"app_version_id": 12}, "enrich 不得修改传入对象"
