"""权限接口的平台维度。"""
import pytest
from sqlalchemy import text

from app.services.permission_import import import_platform

P = "test.platform.api."


def _cleanup(db):
    db.execute(text("delete from privacy_kb.permission where permission_name like :p"), {"p": P + "%"})
    db.commit()


@pytest.fixture
def seeded(db):
    _cleanup(db)
    import_platform(db, "ANDROID", [
        {"permission_name": P + "danger", "permission_type": "危险权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
        {"permission_name": P + "sig", "permission_type": "签名权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
    ])
    import_platform(db, "IOS", [
        {"permission_name": P + "camera", "permission_type": "用法描述键", "capability": "拍照片",
         "grant_mode": None, "official_reference": None, "raw_data": {}},
    ])
    yield
    _cleanup(db)


def test_meta_returns_platform_specific_vocabulary(client, admin_headers):
    android = client.get("/api/v1/permissions/meta", headers=admin_headers,
                         params={"platform": "ANDROID"}).json()["data"]
    ios = client.get("/api/v1/permissions/meta", headers=admin_headers,
                     params={"platform": "IOS"}).json()["data"]
    assert "危险权限" in android["permission_types"]
    assert ios["permission_types"] == ["用法描述键"]
    assert "危险权限" not in ios["permission_types"]


def test_meta_rejects_unknown_platform(client, admin_headers):
    """未知平台没有词表可给：要 400，不能 500，也不能退回并集。

    退回并集比报错更坏——前端会拿 Android 的取值去校验 iOS 的输入。
    """
    resp = client.get("/api/v1/permissions/meta", headers=admin_headers,
                      params={"platform": "FOO"})
    assert resp.status_code == 400


def test_list_filters_by_platform(client, admin_headers, db, seeded):
    got = client.get("/api/v1/permissions", headers=admin_headers,
                     params={"platform": "IOS", "keyword": P}).json()["data"]
    assert [i["permission_name"] for i in got["items"]] == [P + "camera"]
    assert got["items"][0]["platform"] == "IOS"


def test_applicable_filter_excludes_signature_level(client, admin_headers, db, seeded):
    """Android 那 875 条签名/系统级默认不进版面。"""
    got = client.get("/api/v1/permissions", headers=admin_headers,
                     params={"platform": "ANDROID", "applicable": "true", "keyword": P}).json()["data"]
    names = [i["permission_name"] for i in got["items"]]
    assert P + "danger" in names
    assert P + "sig" not in names


def test_applicable_filter_is_tri_state(client, admin_headers, db, seeded):
    """`applicable` 必须三态：true 只看可达、false 只看不可达、不传不筛。

    写成 `if applicable:` 的话 false 会退化成「不筛选」——调用方要「不可达」却拿到全量，
    是个不报错的错答案。
    """
    only_reachable = client.get("/api/v1/permissions", headers=admin_headers,
                                params={"platform": "ANDROID", "applicable": "true",
                                        "keyword": P}).json()["data"]["items"]
    only_unreachable = client.get("/api/v1/permissions", headers=admin_headers,
                                  params={"platform": "ANDROID", "applicable": "false",
                                          "keyword": P}).json()["data"]["items"]
    unfiltered = client.get("/api/v1/permissions", headers=admin_headers,
                            params={"platform": "ANDROID", "keyword": P}).json()["data"]["items"]

    assert [i["permission_name"] for i in only_reachable] == [P + "danger"]
    assert [i["permission_name"] for i in only_unreachable] == [P + "sig"]
    assert len(unfiltered) == 2, "不传 applicable 时两行都要在"


def test_applicable_filter_happens_before_pagination(client, admin_headers, db, seeded):
    """`page_size=1` + `applicable`：先过滤，后切片。

    切片顺序写反（先按页取一条再过滤）不会报错，只会**静静少给**——所以这里造一个
    排序在最前、但不可达的行（`P+"a0sig"`）：先切片的话第一页取到它、过滤完是空列表，
    断言立刻红。名字前缀刻意排在 app1/app2/danger 之前，就是为了让两种顺序分道扬镳。
    """
    import_platform(db, "ANDROID", [
        {"permission_name": P + "a0sig", "permission_type": "签名权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
        {"permission_name": P + "app1", "permission_type": "普通权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
        {"permission_name": P + "app2", "permission_type": "普通权限", "capability": None,
         "grant_mode": None, "official_reference": None, "raw_data": {}},
    ])

    def page(n):
        return client.get("/api/v1/permissions", headers=admin_headers,
                          params={"platform": "ANDROID", "applicable": "true",
                                  "keyword": P, "page": n, "page_size": 1}).json()["data"]

    first, second = page(1), page(2)
    # 可达的是 app1 / app2 / danger 三条，不可达的 sig / a0sig 已被滤掉
    assert first["total"] == second["total"] == 3, "total 必须是过滤后的条数"
    assert [i["permission_name"] for i in first["items"]] == [P + "app1"]
    assert [i["permission_name"] for i in second["items"]] == [P + "app2"]
    assert [i["permission_name"] for i in page(3)["items"]] == [P + "danger"]
    assert page(4)["items"] == [], "按名排序翻到底就该是空的"


def test_create_rejects_type_from_another_platform(client, admin_headers, db):
    _cleanup(db)
    try:
        resp = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "bad", "platform": "IOS", "permission_type": "危险权限"})
        assert resp.status_code == 400
    finally:
        _cleanup(db)


def test_update_validates_against_the_row_own_platform(client, admin_headers, db):
    """编辑态的词表要按**这一行自身的平台**取。

    `PermissionUpdate` 不含 platform（平台是行的身份，建后不可改），所以拿全局词表
    或拿错平台的词表都会放行——那样 IOS 行就能被改成「危险权限」。
    """
    _cleanup(db)
    try:
        pid = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "iosrow", "platform": "IOS",
            "permission_type": "用法描述键"}).json()["data"]["id"]

        bad = client.put(f"/api/v1/permissions/{pid}", headers=admin_headers,
                         json={"permission_type": "危险权限"})
        assert bad.status_code == 400

        ok = client.put(f"/api/v1/permissions/{pid}", headers=admin_headers,
                        json={"permission_type": "用法描述键"})
        assert ok.status_code == 200
    finally:
        _cleanup(db)


def test_create_defaults_to_android(client, admin_headers, db):
    _cleanup(db)
    try:
        resp = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "default", "permission_type": "普通权限"})
        assert resp.status_code == 200
        assert resp.json()["data"]["platform"] == "ANDROID"
    finally:
        _cleanup(db)


def test_ios_row_with_empty_capability_round_trips(client, admin_headers, db):
    _cleanup(db)
    try:
        created = client.post("/api/v1/permissions", headers=admin_headers, json={
            "permission_name": P + "nocap", "platform": "IOS", "permission_type": "用法描述键"})
        assert created.status_code == 200
        pid = created.json()["data"]["id"]
        got = client.get(f"/api/v1/permissions/{pid}", headers=admin_headers).json()["data"]
        assert got["capability"] is None
    finally:
        _cleanup(db)
