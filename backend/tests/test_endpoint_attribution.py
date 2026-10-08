"""域名归属推导（`app/services/endpoint_attribution.py`）的两条不变量。

F1：`attribute_hosts` 必须覆盖**该任务实际出现的全部 host**，而不只是 AppShark
    观测到的那些。纯 Androguard 任务（三个银行样本）的 host 一个都不在
    `host_paths` 的 key 里——此前语料为它们写的行被整批静默丢掉。
F3：语料里组件/厂商两列留白、但断语落在 `label` 上的行（平台命名空间 / 应用自研）
    **同样**算「有断语」，要压过推导（否则 www.w3.org 会被 libflutter.so 推成 Flutter）。
T7-M7：三样全空的归属不落地（前端会渲染成一个空的归属盒）。
"""
from app.services import endpoint_attribution as ea
from app.services.component_matcher import cached_component_index


def test_curated_label_column_parsed():
    """语料第 7 列 label 被解析出来；三样全空的行被判为「无断语」。"""
    cur = ea.load_curated()
    assert cur["www.w3.org"]["label"] == "平台命名空间"
    # 自研业务服务器：知识库没有对应组件/厂商，断语只在 label
    assert cur["test.bankofyk.com"]["component_name"] is None
    assert cur["test.bankofyk.com"]["label"] == "应用自研"
    # 真正「查不到依据」的行三样全空
    assert not ea.has_verdict(cur["124.207.86.58"])


def test_attribute_hosts_covers_hosts_absent_from_appshark(db):
    """F1：传进来的 host 即便不在 host_paths 里，也要能拿到归属。

    `paths_by_host={}` 模拟「这个 host 只有 Androguard 观测、AppShark 一行都没有」。
    旧实现只遍历 `host_paths(db, tid)`，这类 host 从不进循环，语料被静默丢弃。
    """
    idx = cached_component_index(db)
    res = ea.attribute_hosts(db, idx, -1, hosts=["test.bankofyk.com"], paths_by_host={})
    assert res.get("test.bankofyk.com", {}).get("label") == "应用自研"
    assert res["test.bankofyk.com"]["via"] == "curated"


def test_curated_label_overrides_derived(db):
    """F3：只有 label 的语料行也压过推导（www.w3.org ≠ Flutter）。"""
    idx = cached_component_index(db)
    res = ea.attribute_hosts(
        db, idx, -1, hosts=["www.w3.org"],
        paths_by_host={"www.w3.org": {"lib/arm64-v8a/libflutter.so"}})
    a = res["www.w3.org"]
    assert a["via"] == "curated"
    assert a["label"] == "平台命名空间"
    assert a["component_name"] is None


def test_no_verdict_host_is_not_emitted(db):
    """T7-M7：既无语料、又推不出的 host 不落地——不返回一个空盒子。"""
    idx = cached_component_index(db)
    res = ea.attribute_hosts(db, idx, -1, hosts=["definitely-not-a-known-host.example"],
                             paths_by_host={})
    assert res == {}
