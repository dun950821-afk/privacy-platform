"""平台结论的详情 / 状态 / 复检记录三个接口（实施计划 0d）。

最值得锁的是**重生成不覆盖人工状态**这条：`GET /{tid}/platform-findings` 每次读取都会
调 `generate_findings()` 重新生成结论（那是有意的——结论要随规则演进刷新），
所以「人工改了状态之后再读一次列表」是这条链上最容易回归的路径。
"""
import pytest
from sqlalchemy import text

from app.models import PlatformFinding


@pytest.fixture
def finding(db):
    """借一条真实结论来测，测完把人工改过的字段还原。"""
    row = db.query(PlatformFinding).filter(
        PlatformFinding.observation_count > 0).order_by(PlatformFinding.id).first()
    if row is None:
        pytest.skip("库里没有带证据的结论，跳过")
    origin = (row.triage_status, row.assigned_to, row.due_date)
    yield row
    db.rollback()
    db.execute(text("update platform_findings set triage_status=:s, assigned_to=:a, due_date=:d "
                    "where id=:i"),
               {"s": origin[0], "a": origin[1], "d": origin[2], "i": row.id})
    db.commit()


def test_status_survives_regeneration(client, admin_headers, finding):
    """人工改的状态，不能被「读列表时重新生成结论」冲掉。"""
    url = f"/api/v1/tasks/{finding.task_id}/platform-findings/{finding.id}/status"
    resp = client.put(url, json={"triage_status": "fixed", "assigned_to": 1,
                                 "due_date": "2026-12-31"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["triage_status"] == "fixed"

    # 这一步会触发 generate_findings()
    listed = client.get(f"/api/v1/tasks/{finding.task_id}/platform-findings",
                        headers=admin_headers)
    assert listed.status_code == 200
    item = next(i for i in listed.json()["data"]["items"] if i["id"] == finding.id)
    assert item["triage_status"] == "fixed", "重新生成把人工状态覆盖了"
    assert item["assigned_to"] == 1
    assert item["due_date"] == "2026-12-31"


def test_status_rejects_unknown_value(client, admin_headers, finding):
    url = f"/api/v1/tasks/{finding.task_id}/platform-findings/{finding.id}/status"
    assert client.put(url, json={"triage_status": "done"}, headers=admin_headers).status_code == 400


def test_status_rejects_bad_date_and_assignee(client, admin_headers, finding):
    url = f"/api/v1/tasks/{finding.task_id}/platform-findings/{finding.id}/status"
    assert client.put(url, json={"due_date": "2026/12/31"}, headers=admin_headers).status_code == 400
    assert client.put(url, json={"assigned_to": 999999}, headers=admin_headers).status_code == 400


def test_detail_returns_observations_for_evidence_block(client, admin_headers, finding):
    """详情要给出关联 observation——调用点列表用它的 location，
    代码证据块要把它的 id 交给 EngineReportViewer（那要 observationId 不是 findingId）。"""
    resp = client.get(f"/api/v1/tasks/{finding.task_id}/platform-findings/{finding.id}",
                      headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["observations"], "详情没带出关联 observation"
    assert {"id", "location", "provider_level", "engine_type"} <= set(data["observations"][0])


def test_detail_404_for_other_tasks_finding(client, admin_headers, finding):
    """结论必须属于该任务——拿别的任务的 tid 去查要 404，不能跨任务读。"""
    resp = client.get(f"/api/v1/tasks/{finding.task_id + 1000000}/platform-findings/{finding.id}",
                      headers=admin_headers)
    assert resp.status_code == 404


def test_retest_records_shape(client, admin_headers, finding):
    resp = client.get(f"/api/v1/tasks/{finding.task_id}/retest-records", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"items", "as_retest"}
