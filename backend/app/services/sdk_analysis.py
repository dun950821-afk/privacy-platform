"""SDK识别分析服务

将检测任务的事件（detection_events）与知识库指纹匹配，聚合为：
- privacy_scan.component_hit  SDK识别结果（一个SDK一条）
- privacy_scan.hit_evidence   命中证据（一条事件可作为一条证据，event_id 反向关联事件流）
- privacy_scan.package_cluster 未识别包簇（未命中任何组件的包前缀）

用户的人工标记（误报/白名单/自研/关联等）在重新分析时保留。
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import DetectionTask, DetectionEvent, AppVersion
from app.models.kb import (
    KBComponent, KBVendor, KBComponentFingerprint, KBComponentDataClaim,
    KBComponentPermission, KBPermission,
    ScanApp, ScanAppBuild, ScanJob, ScanComponentHit, ScanHitEvidence, ScanPackageCluster,
)

logger = logging.getLogger(__name__)

# 已知加固/插件框架包前缀
PACKER_PREFIXES = {
    "com.byazt", "com.secneo", "com.bangcle", "com.nqshield",
    "com.stub", "com.wrapper", "com.qihoo.util", "com.protect",
    "com.tencent.StubShell", "com.edog",
}

MATCH_TYPES = ["PACKAGE_PREFIX", "CLASS"]


def _load_fingerprints(db: Session):
    """加载匹配指纹（含权重），按值长度降序保证最长前缀优先"""
    rows = db.query(KBComponentFingerprint, KBComponent) \
        .join(KBComponent, KBComponentFingerprint.component_id == KBComponent.id) \
        .filter(KBComponentFingerprint.fingerprint_type.in_(MATCH_TYPES),
                KBComponentFingerprint.is_negative == False,
                KBComponentFingerprint.match_mode.in_(["EXACT", "PREFIX"]),
                KBComponent.is_active == True) \
        .all()
    fps = []
    for fp, comp in rows:
        val = (fp.normalized_value or "").strip().lower()
        if val:
            fps.append((val, fp, comp))
    fps.sort(key=lambda x: len(x[0]), reverse=True)
    return fps


def _match(fps, *candidates):
    """返回 (fp, component) 或 None"""
    for cand in candidates:
        if not cand:
            continue
        c = cand.strip().lower()
        for val, fp, comp in fps:
            if c.startswith(val):
                return fp, comp
    return None


def _cluster_prefix(class_name: str) -> str:
    """包簇前缀：类名去掉简单类名后取前 3 段（不足则全取）"""
    parts = class_name.strip().split(".")
    if len(parts) <= 3:
        return ".".join(parts[:-1]) if len(parts) > 1 else class_name
    return ".".join(parts[:3])


def _guess_attr(prefix: str, app_package: str) -> str:
    """推测包簇属性"""
    p = prefix.lower()
    if app_package and (p.startswith(app_package.lower()) or app_package.lower().startswith(p)):
        return "自研/厂商组件"
    for pk in PACKER_PREFIXES:
        if p.startswith(pk.lower()):
            return "加固或插件组件"
    return "未知组件/待分析"


def _confidence(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def ensure_scan_job(db: Session, task: DetectionTask) -> ScanJob:
    """获取或创建任务对应的 privacy_scan 扫描记录（app/app_build/scan_job）

    前端会并发调用 sdk-hits / package-clusters，两个请求可能同时走到创建逻辑，
    撞 app_build.build_key 唯一键。用 pg 咨询锁把同一任务的创建过程串行化。
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": task.id})

    job = db.query(ScanJob) \
        .join(ScanAppBuild, ScanJob.app_build_id == ScanAppBuild.id) \
        .filter(ScanAppBuild.build_key == f"task:{task.id}",
                ScanJob.scan_type == "STATIC") \
        .first()
    if job:
        return job

    version = db.query(AppVersion).get(task.app_version_id)
    package_name = version.app.package_name if version and version.app else f"unknown.task{task.id}"

    app = db.query(ScanApp).filter(ScanApp.package_name == package_name).first()
    if not app:
        app = ScanApp(package_name=package_name,
                      app_name=version.app.app_name if version and version.app else None)
        db.add(app)
        db.flush()

    build = db.query(ScanAppBuild).filter(ScanAppBuild.build_key == f"task:{task.id}").first()
    if not build:
        build = ScanAppBuild(
            build_key=f"task:{task.id}", app_id=app.id,
            version_name=version.version_name if version else None,
            version_code=str(version.version_code) if version else None,
            min_sdk=version.min_sdk if version else None,
            target_sdk=version.target_sdk if version else None,
            file_size=version.file_size if version else None,
            sha256=version.sha256 if version else None,
        )
        db.add(build)
        db.flush()

    job = ScanJob(app_build_id=build.id, scan_type="STATIC",
                  engine_version="sdk-analysis/1.0",
                  rule_version=task.rule_pack_version,
                  status="SUCCESS", finished_at=datetime.now(timezone.utc))
    db.add(job)
    db.flush()
    return job


def analyze_task(db: Session, task: DetectionTask, refresh: bool = False) -> ScanJob:
    """对任务执行 SDK 识别聚合分析（幂等，保留人工标记）"""
    job = ensure_scan_job(db, task)

    # 「分析过了」的判据必须同时看两张结果表。只看命中数时，一个**一个指纹都没命中**
    # 的 App（结果是 0 命中 + N 个未识别包簇）会被判成「没分析过」，于是既不提前返回、
    # 也不清理旧结果，接着把同样的包簇再插一遍 → 唯一约束冲突 → 接口 500，且每次读取
    # 都失败（线上 2026-09-28 的故障即此）。
    existing_hits = db.query(ScanComponentHit).filter(ScanComponentHit.scan_job_id == job.id).count()
    existing_clusters = db.query(ScanPackageCluster).filter(ScanPackageCluster.scan_job_id == job.id).count()
    analyzed = bool(existing_hits or existing_clusters)
    if analyzed and not refresh:
        return job

    # 保留人工标记
    hit_overrides = {
        h.component_id: h.hit_status
        for h in db.query(ScanComponentHit).filter(ScanComponentHit.scan_job_id == job.id).all()
        if h.hit_status in ("REJECTED", "WHITELISTED", "CONFIRMED")
    }
    cluster_overrides = {
        c.package_prefix: (c.matched_component_id, (c.raw_data or {}).get("review_status"))
        for c in db.query(ScanPackageCluster).filter(ScanPackageCluster.scan_job_id == job.id).all()
    }

    # 清空重算
    if refresh or analyzed:
        for h in db.query(ScanComponentHit).filter(ScanComponentHit.scan_job_id == job.id).all():
            db.query(ScanHitEvidence).filter(ScanHitEvidence.component_hit_id == h.id) \
                .delete(synchronize_session=False)
        db.query(ScanComponentHit).filter(ScanComponentHit.scan_job_id == job.id) \
            .delete(synchronize_session=False)
        db.query(ScanPackageCluster).filter(ScanPackageCluster.scan_job_id == job.id) \
            .delete(synchronize_session=False)
        db.flush()

    events = db.query(DetectionEvent).filter(
        DetectionEvent.task_id == task.id,
        DetectionEvent.event_type == "static_component",
    ).all()

    fps = _load_fingerprints(db)
    app_package = ""
    version = db.query(AppVersion).get(task.app_version_id)
    if version and version.app:
        app_package = version.app.package_name or ""

    # 聚合：component_id -> {component, evidence:[(event, fp)]}
    hit_map: dict[int, dict] = {}
    unmatched: list[DetectionEvent] = []

    for e in events:
        m = _match(fps, e.caller, e.api)
        if m:
            fp, comp = m
            entry = hit_map.setdefault(comp.id, {"component": comp, "evidence": []})
            entry["evidence"].append((e, fp))
        else:
            unmatched.append(e)

    # 写入命中结果与证据
    for comp_id, entry in hit_map.items():
        comp = entry["component"]
        evidences = entry["evidence"]
        total_score = min(100, sum(max((fp.weight or 0), 0) for _, fp in evidences))
        hit_status = hit_overrides.get(comp_id) or (
            "CONFIRMED" if total_score >= 70 else
            "PROBABLE" if total_score >= 40 else "CANDIDATE"
        )
        hit = ScanComponentHit(
            scan_job_id=job.id, component_id=comp_id,
            total_score=total_score,
            confidence_level=_confidence(total_score),
            hit_status=hit_status,
            primary_package=(evidences[0][1].normalized_value if evidences else None),
            evidence_count=len(evidences),
        )
        db.add(hit)
        db.flush()
        for e, fp in evidences:
            db.add(ScanHitEvidence(
                component_hit_id=hit.id, fingerprint_id=fp.id, event_id=e.id,
                evidence_type=e.data_type or fp.fingerprint_type,
                evidence_value=e.api or e.caller or "",
                score=max((fp.weight or 0), 0),
                is_primary=fp.fingerprint_type == "PACKAGE_PREFIX",
                raw_data={"matched_fingerprint": fp.normalized_value,
                          "match_type": fp.fingerprint_type, "source": "Manifest"},
            ))

    # 写入未识别包簇
    cluster_map: dict[str, dict] = {}
    for e in unmatched:
        name = e.api or e.caller or ""
        prefix = _cluster_prefix(name)
        if not prefix:
            continue
        c = cluster_map.setdefault(prefix, {"classes": set(), "types": {}, "first_ts": e.timestamp})
        c["classes"].add(name)
        t = e.data_type or "UNKNOWN"
        c["types"][t] = c["types"].get(t, 0) + 1
        if e.timestamp and (c["first_ts"] is None or e.timestamp < c["first_ts"]):
            c["first_ts"] = e.timestamp

    for prefix, c in cluster_map.items():
        linked_id, review_status = cluster_overrides.get(prefix, (None, None))
        raw = {"review_status": review_status or "pending",
               "first_seen_at": str(c["first_ts"]) if c["first_ts"] else None}
        db.add(ScanPackageCluster(
            scan_job_id=job.id, package_prefix=prefix,
            identified_name=_guess_attr(prefix, app_package),
            component_kind="APP_MODULE" if "自研" in _guess_attr(prefix, app_package) else None,
            component_count=len(c["classes"]),
            component_type_stat=c["types"],
            matched_component_id=linked_id,
            raw_data=raw,
        ))

    db.commit()
    logger.info(f"task {task.id}: {len(hit_map)} sdk hits, {len(cluster_map)} clusters, "
                f"{len(events)} events analyzed")
    return job


def get_hits(db: Session, task: DetectionTask) -> list[dict]:
    """SDK识别结果列表（一个SDK一行）"""
    job = ensure_scan_job(db, task)
    rows = db.query(ScanComponentHit, KBComponent, KBVendor) \
        .join(KBComponent, ScanComponentHit.component_id == KBComponent.id) \
        .outerjoin(KBVendor, KBComponent.vendor_id == KBVendor.id) \
        .filter(ScanComponentHit.scan_job_id == job.id) \
        .order_by(ScanComponentHit.total_score.desc()).all()

    result = []
    for hit, comp, vendor in rows:
        # 涉及信息：组件的个人信息声明类别
        claims = db.query(KBComponentDataClaim).filter(
            KBComponentDataClaim.component_id == comp.id).all()
        info_cats = []
        for cl in claims:
            if cl.personal_info_category:
                for part in str(cl.personal_info_category).replace("；", ";").split(";"):
                    part = part.strip()
                    if part and part not in info_cats:
                        info_cats.append(part)

        # 是否涉及敏感权限
        sensitive = db.query(KBComponentPermission, KBPermission) \
            .join(KBPermission, KBComponentPermission.permission_id == KBPermission.id) \
            .filter(KBComponentPermission.component_id == comp.id,
                    KBPermission.risk_level.in_(["HIGH", "CRITICAL"])) \
            .count() > 0

        # 包名前缀列表
        prefixes = [r[0] for r in db.query(KBComponentFingerprint.normalized_value).filter(
            KBComponentFingerprint.component_id == comp.id,
            KBComponentFingerprint.fingerprint_type == "PACKAGE_PREFIX",
            KBComponentFingerprint.is_negative == False).all() if r[0]]

        result.append({
            "hit_id": hit.id,
            "component_id": comp.id,
            "sdk_name": comp.name,
            "category": comp.category_l1,
            "vendor": vendor.name if vendor else None,
            "confidence_level": hit.confidence_level,
            "total_score": hit.total_score,
            "evidence_count": hit.evidence_count,
            "involved_info": info_cats[:4],
            "hit_status": hit.hit_status,
            "primary_package": hit.primary_package,
            "package_prefixes": prefixes[:5],
            "sensitive_permission": sensitive,
            "detected_version": hit.detected_version,
            "rule_version": job.rule_version,
            "sensitivity_level": comp.sensitivity_level,
            "compliance_note": comp.compliance_note,
        })
    return result


def get_hit_detail(db: Session, task: DetectionTask, hit_id: int) -> dict | None:
    """SDK命中详情 + 证据明细（证据反关联事件流）"""
    job = ensure_scan_job(db, task)
    row = db.query(ScanComponentHit, KBComponent, KBVendor) \
        .join(KBComponent, ScanComponentHit.component_id == KBComponent.id) \
        .outerjoin(KBVendor, KBComponent.vendor_id == KBVendor.id) \
        .filter(ScanComponentHit.id == hit_id,
                ScanComponentHit.scan_job_id == job.id).first()
    if not row:
        return None
    hit, comp, vendor = row

    evidences = db.query(ScanHitEvidence, DetectionEvent) \
        .outerjoin(DetectionEvent, ScanHitEvidence.event_id == DetectionEvent.id) \
        .filter(ScanHitEvidence.component_hit_id == hit.id) \
        .order_by(ScanHitEvidence.score.desc()).all()

    ev_list = []
    type_stat: dict[str, int] = {}
    for ev, event in evidences:
        type_stat[ev.evidence_type] = type_stat.get(ev.evidence_type, 0) + 1
        ev_list.append({
            "id": ev.id,
            "event_id": ev.event_id,
            "evidence_type": ev.evidence_type,
            "evidence_value": ev.evidence_value,
            "score": ev.score,
            "is_primary": ev.is_primary,
            "source": (ev.raw_data or {}).get("source", "Manifest"),
            "matched_fingerprint": (ev.raw_data or {}).get("matched_fingerprint"),
            "event_type": event.event_type if event else None,
            "event_time": str(event.timestamp) if event else None,
        })

    return {
        "hit_id": hit.id,
        "component_id": comp.id,
        "sdk_name": comp.name,
        "vendor": vendor.name if vendor else None,
        "vendor_website": vendor.official_website if vendor else None,
        "category": comp.category_l1,
        "hit_status": hit.hit_status,
        "confidence_level": hit.confidence_level,
        "total_score": hit.total_score,
        "rule_version": job.rule_version,
        "sensitivity_level": comp.sensitivity_level,
        "compliance_note": comp.compliance_note,
        "evidence_total": len(ev_list),
        "evidence_type_stat": type_stat,
        "evidences": ev_list,
    }


def get_clusters(db: Session, task: DetectionTask) -> list[dict]:
    """未识别包簇列表"""
    job = ensure_scan_job(db, task)
    rows = db.query(ScanPackageCluster) \
        .filter(ScanPackageCluster.scan_job_id == job.id) \
        .order_by(ScanPackageCluster.component_count.desc()).all()

    result = []
    for c in rows:
        review_status = (c.raw_data or {}).get("review_status", "pending")
        linked_name = None
        if c.matched_component_id:
            comp = db.query(KBComponent).get(c.matched_component_id)
            linked_name = comp.name if comp else None
        result.append({
            "id": c.id,
            "package_prefix": c.package_prefix,
            "class_count": c.component_count,
            "component_type_stat": c.component_type_stat,
            "guess_attr": c.identified_name,
            "review_status": review_status,
            "linked_component_id": c.matched_component_id,
            "linked_component_name": linked_name,
            "first_seen_at": (c.raw_data or {}).get("first_seen_at"),
        })
    return result
