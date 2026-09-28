"""权限知识库的维护接口。

权限表是**受控词表**：`permission_type` 按平台各一套取值（Android 那套是归一后的 8 个）。
之前这张表里攒了 39 个自由文本取值（「危险/已弱化」「普通/受限 API权限」…），
正是没有入口校验造成的。这里的用例把这条约束钉住，免得又从界面上污染回去。
"""
from sqlalchemy import text

PREFIX = "test.kb.perm."
NAME_A = PREFIX + "alpha"
NAME_B = PREFIX + "beta"
NAME_DUP = PREFIX + "dup"
NAME_REF = PREFIX + "referenced"


def _cleanup(db):
    """删掉本文件造的数据。先断扫描侧外键引用，再删权限本身。"""
    names = [NAME_A, NAME_B, NAME_DUP, NAME_REF]
    db.execute(text("""
        update privacy_scan.declared_permission set permission_id = null
        where permission_id in (select id from privacy_kb.permission where permission_name = any(:names))
    """), {"names": names})
    db.execute(text("delete from privacy_kb.permission where permission_name = any(:names)"),
               {"names": names})
    db.commit()


def _row(db, name):
    return db.execute(text("""
        select id, permission_name, category, permission_type, risk_level,
               capability, grant_mode, compliance_focus, official_reference, is_active
        from privacy_kb.permission where permission_name = :n
    """), {"n": name}).mappings().first()


def test_meta_exposes_controlled_vocabulary(client, admin_headers):
    """枚举值由后端给，前端不硬编码——硬编码正是词表失控的起点。

    词表**按平台各一套**：不传 platform 时返回的是三平台并集，所以这里必须指定平台
    再断言个数，否则 8 这个数字量的是并集、断言失去意义。
    """
    resp = client.get("/api/v1/permissions/meta", headers=admin_headers,
                      params={"platform": "ANDROID"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "危险权限" in data["permission_types"]
    assert "三方声明权限" in data["permission_types"]
    assert len(data["permission_types"]) == 8, "Android 受控词表就是归一后的 8 个"
    assert set(data["risk_levels"]) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert isinstance(data["categories"], list)


def test_create_rejects_invalid_permission_type(client, admin_headers, db):
    """非法 permission_type 必须拒绝，否则 39 个自由文本取值会卷土重来。"""
    _cleanup(db)
    try:
        resp = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": NAME_A, "category": "设备标识",
            "permission_type": "危险/已弱化", "risk_level": "MEDIUM"})
        assert resp.status_code == 400
        assert _row(db, NAME_A) is None
    finally:
        _cleanup(db)


def test_create_rejects_duplicate_name(client, admin_headers, db):
    _cleanup(db)
    try:
        body = {"permission_name": NAME_DUP, "category": "设备标识",
                "permission_type": "危险权限", "risk_level": "HIGH"}
        assert client.post("/api/v1/permissions", headers=admin_headers, json=body).status_code == 200
        assert client.post("/api/v1/permissions", headers=admin_headers, json=body).status_code == 400
    finally:
        _cleanup(db)


def test_lifecycle_create_list_get_update_disable_delete(client, admin_headers, db):
    _cleanup(db)
    try:
        created = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": NAME_A, "category": "位置信息",
            "permission_type": "危险权限（受限）", "risk_level": "HIGH",
            "capability": "后台获取位置", "grant_mode": "运行时授权",
            "compliance_focus": "需单独告知", "official_reference": "https://example.com/x"})
        assert created.status_code == 200
        pid = created.json()["data"]["id"]

        listed = client.get("/api/v1/permissions", headers=admin_headers,
                            params={"keyword": NAME_A})
        assert listed.status_code == 200
        assert any(i["permission_name"] == NAME_A for i in listed.json()["data"]["items"])

        detail = client.get(f"/api/v1/permissions/{pid}", headers=admin_headers).json()["data"]
        assert detail["permission_type"] == "危险权限（受限）"

        # 停用：与删除是两回事，停用后行还在
        assert client.put(f"/api/v1/permissions/{pid}", headers=admin_headers,
                          json={"is_active": False}).status_code == 200
        assert _row(db, NAME_A)["is_active"] is False

        # 启用
        assert client.put(f"/api/v1/permissions/{pid}", headers=admin_headers,
                          json={"is_active": True}).status_code == 200
        assert _row(db, NAME_A)["is_active"] is True

        # 改其它字段
        assert client.put(f"/api/v1/permissions/{pid}", headers=admin_headers,
                          json={"risk_level": "CRITICAL", "category": "高风险系统能力"}).status_code == 200
        row = _row(db, NAME_A)
        assert row["risk_level"] == "CRITICAL"
        assert row["category"] == "高风险系统能力"

        assert client.delete(f"/api/v1/permissions/{pid}", headers=admin_headers).status_code == 200
        assert _row(db, NAME_A) is None
    finally:
        _cleanup(db)


def test_update_rejects_invalid_permission_type(client, admin_headers, db):
    _cleanup(db)
    try:
        pid = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": NAME_B, "permission_type": "普通权限"}).json()["data"]["id"]
        resp = client.put(f"/api/v1/permissions/{pid}", headers=admin_headers,
                          json={"permission_type": "普通/受限 API权限"})
        assert resp.status_code == 400
        assert _row(db, NAME_B)["permission_type"] == "普通权限"
    finally:
        _cleanup(db)


def test_delete_keeps_scan_record_permission_name(client, admin_headers, db):
    """权限被扫描记录引用时：外键置空，但扫描记录里的 permission_name 必须保留。

    权限名是对外主键——历史报告按名字展示，物理删权限不能把历史记录弄成空白。
    """
    _cleanup(db)
    try:
        pid = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": NAME_REF, "permission_type": "三方声明权限"}).json()["data"]["id"]

        job_id = db.execute(text("select id from privacy_scan.scan_job order by id limit 1")).scalar()
        assert job_id is not None, "样本库应至少有一个 scan_job"
        db.execute(text("""
            insert into privacy_scan.declared_permission
              (scan_job_id, permission_name, permission_id, is_dangerous, risk_level)
            values (:j, :n, :p, false, 'MEDIUM')
        """), {"j": job_id, "n": NAME_REF, "p": pid})
        db.commit()

        assert client.delete(f"/api/v1/permissions/{pid}", headers=admin_headers).status_code == 200
        assert _row(db, NAME_REF) is None

        kept = db.execute(text("""
            select permission_name, permission_id from privacy_scan.declared_permission
            where scan_job_id = :j and permission_name = :n
        """), {"j": job_id, "n": NAME_REF}).mappings().first()
        assert kept is not None, "扫描记录不能被删掉"
        assert kept["permission_name"] == NAME_REF, "权限名必须保留"
        assert kept["permission_id"] is None, "悬空外键必须置空"
    finally:
        db.execute(text("delete from privacy_scan.declared_permission where permission_name = :n"),
                   {"n": NAME_REF})
        db.commit()
        _cleanup(db)
