"""任务详情的证据来源接口（实施计划 §4.1）。

两个接口都不新写解析逻辑，直接读 `engine_raw_sections`——那段表存在的意义就是
「提取是一次性的，没被提取的段落等于不存在」。这里锁的是**取数与标记口径**，
以及「没有数据」与「数据是空的」这两件事要能分开。
"""
import pytest

from app.models import EngineRawSection


def _task_with_sections(db) -> int | None:
    row = db.query(EngineRawSection.task_id).filter(
        EngineRawSection.section_path == "endpoints.urls").first()
    return row[0] if row else None


@pytest.fixture
def scanned_task(db):
    tid = _task_with_sections(db)
    if tid is None:
        pytest.skip("库里没有跑出 endpoints.urls 的任务，跳过")
    return tid


def test_endpoints_are_aggregated_by_host(client, admin_headers, scanned_task):
    resp = client.get(f"/api/v1/tasks/{scanned_task}/endpoints", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["available"] is True
    hosts = data["hosts"]
    assert hosts, "有 endpoints.urls 却聚合不出 host"

    # 每个 host 只出现一次，且 url_count 与 urls 长度一致
    seen = [h["host"] for h in hosts]
    assert len(seen) == len(set(seen)), "host 没去重"
    assert all(h["url_count"] == len(h["urls"]) for h in hosts)

    # 去重只是「按 host 归拢」，**不能丢 URL**
    assert sum(h["url_count"] for h in hosts) == data["total_urls"]

    # 排序：条数多的在前（前端按此顺序铺）
    counts = [h["url_count"] for h in hosts]
    assert counts == sorted(counts, reverse=True)


def test_endpoints_flags_test_residue_and_marks_nothing_else(client, admin_headers, scanned_task):
    """只标可判定的两类，不做「业务服务器 / 第三方 SDK」分类（§5.4 明确否掉）。"""
    data = client.get(f"/api/v1/tasks/{scanned_task}/endpoints",
                      headers=admin_headers).json()["data"]
    for h in data["hosts"]:
        assert set(h) == {"host", "urls", "is_test_residue", "is_privacy_policy", "url_count"}, \
            "多出了未声明的分类字段——§5.4 要求不做 业务/第三方 分类"
        if h["is_test_residue"]:
            assert "test" in h["host"]


def test_endpoints_reports_unavailable_when_no_sections(client, admin_headers, db):
    """没跑过（或引擎没产出）时要说「没有数据」，不能与「没有端点」混为一谈。"""
    from app.models import DetectionTask
    row = db.query(DetectionTask.id).filter(
        ~DetectionTask.id.in_(db.query(EngineRawSection.task_id))).first()
    if row is None:
        pytest.skip("所有任务都有 raw_sections，跳过")
    data = client.get(f"/api/v1/tasks/{row[0]}/endpoints", headers=admin_headers).json()["data"]
    assert data["available"] is False
    assert data["hosts"] == []


def test_security_findings_items_and_missing_are_complementary(client, admin_headers, scanned_task):
    data = client.get(f"/api/v1/tasks/{scanned_task}/security-findings",
                      headers=admin_headers).json()["data"]
    sections = [i["section"] for i in data["items"]]
    assert not (set(sections) & set(data["missing"])), "同一段既在 items 又在 missing"
    assert len(sections) + len(data["missing"]) == 5

    # 顺序即展示顺序（前端按此铺「安全加固」块）
    from app.api.v1.tasks import SECURITY_SECTIONS
    order = [s for s, _ in SECURITY_SECTIONS]
    assert sections == [s for s in order if s in sections]
    assert all(i["label"] for i in data["items"])
