"""未识别包簇的准入规则：只有「代码符号」才有资格成为包前缀。

## 缺陷（实测 task 2216，2026-09-29）

任务详情页「暂时无法识别」面板列出的 9 个包簇，**全部不是包名**：

    android.permission                 14 个「类」   ← 权限命名空间
    ACCESS_FINE_LOCATION / CALL_PHONE / READ_EXTERNAL_STORAGE   ← 权限名
    file://localhost/ , http://www.openssl.org/support/faq       ← URL

全库口径：272 条包簇里 **190 条（70%）不是包名**。根因是聚类直接把事件的
`api`/`caller` 当类名切分，而这两列在不同事件类型下装的是权限、URL、.so 文件名：

    static_permission     api = android.permission.ACCESS_FINE_LOCATION
    static_sensitive_perm api = ACCESS_COARSE_LOCATION
    static_url            api = http://www.openssl.org/support/faq.html
    static_native_lib     api = libjpeg.so
    static_sensitive_api  api = <android.content.pm.PackageManager: ... >   ← AppShark 外壳

后果不是「不好看」：审计人员会把 `android.permission` 当成一个未识别的第三方包。

## 两道门

1. **类型门** —— 只有候选串承载代码符号的事件类型才参与聚簇。
2. **形态门** —— 剥掉 AppShark 的 `<类: 方法签名>` 外壳后，须是合法 FQCN，
   且不属于 android/java 这类平台命名空间（它们是操作系统，不是第三方组件）。

两道门都不做兜底猜测：判不出来就不产出包簇，而不是产出「看着像包名」的东西。
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.core.security import generate_uid
from app.models import DetectionEvent, DetectionTask, EngineExecution, SubTask
from app.services.sdk_analysis import analyze_task


@pytest.fixture
def make_task(db):
    """建一个任务并注入 (event_type, api) 事件；用完清理。"""
    from app.services.sdk_analysis import ensure_scan_job

    created: list[int] = []

    def _make(events: list[tuple[str, str]]) -> DetectionTask:
        row = db.execute(text(
            "select v.id as version_id, a.project_id as project_id from app_versions v "
            "join app_assets a on a.id = v.app_id order by v.id limit 1")).first()
        task = DetectionTask(task_code=generate_uid("test"), app_version_id=row.version_id,
                             project_id=row.project_id, detection_type="static_only",
                             status="completed")
        db.add(task)
        db.flush()
        sub = SubTask(sub_task_code=generate_uid("st"), task_id=task.id,
                      engine_type="static", status="completed")
        db.add(sub)
        db.flush()
        db.add(EngineExecution(task_id=task.id, sub_task_id=sub.id, engine_type="androguard",
                               engine_name="Androguard", status="completed", attempt_no=1))
        db.flush()
        for event_type, api in events:
            db.add(DetectionEvent(event_uid=generate_uid("evt"), task_id=task.id,
                                  event_type=event_type, timestamp=datetime.now(timezone.utc),
                                  data_type="UNKNOWN", api=api, event_data={},
                                  engine_name="Androguard", engine_version="4.1.4"))
        db.commit()
        created.append(task.id)
        return task

    yield _make

    for tid in created:
        build_key = "task:%d" % tid
        db.execute(text("delete from privacy_scan.component_hit where scan_job_id in "
                        "(select j.id from privacy_scan.scan_job j "
                        " join privacy_scan.app_build b on b.id=j.app_build_id where b.build_key=:k)"),
                   {"k": build_key})
        db.execute(text("delete from privacy_scan.package_cluster where scan_job_id in "
                        "(select j.id from privacy_scan.scan_job j "
                        " join privacy_scan.app_build b on b.id=j.app_build_id where b.build_key=:k)"),
                   {"k": build_key})
        db.execute(text("delete from privacy_scan.scan_job where app_build_id in "
                        "(select id from privacy_scan.app_build where build_key=:k)"), {"k": build_key})
        db.execute(text("delete from privacy_scan.app_build where build_key=:k"), {"k": build_key})
        db.execute(text("delete from detection_events where task_id=:t"), {"t": tid})
        db.execute(text("delete from engine_executions where task_id=:t"), {"t": tid})
        db.execute(text("delete from sub_tasks where task_id=:t"), {"t": tid})
        db.execute(text("delete from detection_tasks where id=:t"), {"t": tid})
    db.commit()


def clusters_of(db, task) -> dict[str, int]:
    """{包前缀: 该簇下的类数}"""
    rows = db.execute(text(
        "select c.package_prefix, c.component_count from privacy_scan.package_cluster c "
        "join privacy_scan.scan_job j on j.id = c.scan_job_id "
        "join privacy_scan.app_build b on b.id = j.app_build_id "
        "where b.build_key = :k"), {"k": f"task:{task.id}"}).fetchall()
    return {r[0]: r[1] for r in rows}


# ── 类型门：非代码符号的事件不得产出包簇 ────────────────────────────────

def test_permission_events_do_not_become_clusters(db, make_task):
    """权限名不是包名。`android.permission` 曾被列成 14 个「类」的包簇。"""
    task = make_task([
        ("static_permission", "android.permission.ACCESS_FINE_LOCATION"),
        ("static_permission", "android.permission.CALL_PHONE"),
        ("static_sensitive_permission", "ACCESS_COARSE_LOCATION"),
    ])
    analyze_task(db, task, refresh=True)
    assert clusters_of(db, task) == {}


def test_url_events_do_not_become_clusters(db, make_task):
    """URL 不是包名。`http://www.openssl.org/support/faq` 曾被当成包前缀。"""
    task = make_task([
        ("static_url", "http://www.openssl.org/support/faq.html"),
        ("static_url", "file://localhost/"),
    ])
    analyze_task(db, task, refresh=True)
    assert clusters_of(db, task) == {}


def test_native_lib_events_do_not_become_package_clusters(db, make_task):
    """.so 文件名不是包名——`libjpeg.so` 切出了包前缀 `libjpeg`。

    原生库该由 NATIVE_SO 指纹那条路处理，不该混进「包前缀」列表。
    """
    task = make_task([
        ("static_native_lib", "libjpeg.so"),
        ("static_native_lib", "libBaiduMapSDK_base_v7_6_5.so"),
    ])
    analyze_task(db, task, refresh=True)
    assert clusters_of(db, task) == {}


# ── 形态门：剥壳 + 平台命名空间 ──────────────────────────────────────────

def test_appshark_shell_is_stripped_before_clustering(db, make_task):
    """`<com.foo.Bar: void baz()>` 曾切出包前缀 `<com.foo.Bar: void ba`。

    匹配路径早已剥壳（component_matcher.normalize_candidate），聚类路径没有，
    两处口径不一致。剥壳后应得到干净的 `com.example.admission`。
    """
    task = make_task([
        ("static_sensitive_api", "<com.example.admission.Foo: void bar()>"),
        ("static_data_flow", "['<com.example.admission.Baz: void qux()>->$r0']"),
    ])
    analyze_task(db, task, refresh=True)
    assert set(clusters_of(db, task)) == {"com.example.admission"}


def test_platform_namespaces_do_not_become_clusters(db, make_task):
    """android/java 是操作系统与语言运行时，不是「未识别的第三方组件」。

    剥壳修复后，`static_sensitive_api` 的候选变成了合法 FQCN，如果不挡平台命名空间，
    `android.content.pm` 会以 4647 条事件的体量成为最大的那个「未识别包」。
    """
    task = make_task([
        ("static_sensitive_api", "<android.content.pm.PackageManager: int check()>"),
        ("static_data_flow", "['<java.net.URL: void open()>->$r1']"),
        ("static_component", "androidx.core.content.FileProvider"),
    ])
    analyze_task(db, task, refresh=True)
    assert clusters_of(db, task) == {}


# ── 回归护栏：真实第三方包必须照常聚簇 ──────────────────────────────────

def test_real_third_party_classes_still_cluster(db, make_task):
    """收紧准入不能把正常包簇一起收掉。"""
    task = make_task([
        ("static_component", "com.example.admission.ui.HomeActivity"),
        ("static_component", "com.example.admission.ui.LoginActivity"),
        ("static_sensitive_api", "<com.thirdparty.tracker.Reporter: void send()>"),
    ])
    analyze_task(db, task, refresh=True)
    got = clusters_of(db, task)
    assert got.get("com.example.admission") == 2, "同一前缀下的类应聚为一簇"
    assert "com.thirdparty.tracker" in got, "第三方包应照常成簇"
