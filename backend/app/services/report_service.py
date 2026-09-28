"""报告生成服务"""
from sqlalchemy.orm import Session
from app.models import (DetectionTask, Finding, DetectionEvent, Evidence,
                        DetectionScenario, AppVersion, Rule)
from app.core.storage import storage
from datetime import datetime, timezone
import json


class ReportService:
    """报告生成服务"""

    def __init__(self, db: Session):
        self.db = db

    def generate(self, task: DetectionTask) -> dict:
        """生成检测报告"""
        version = self.db.query(AppVersion).get(task.app_version_id)
        app = version.app if version else None

        findings = self.db.query(Finding).filter(Finding.task_id == task.id).all()
        events = self.db.query(DetectionEvent).filter(DetectionEvent.task_id == task.id).order_by(
            DetectionEvent.timestamp.asc()
        ).all()
        scenarios = self.db.query(DetectionScenario).filter(DetectionScenario.task_id == task.id).all()
        evidence = self.db.query(Evidence).filter(Evidence.task_id == task.id).all()

        # 统计
        severity_count = {}
        status_count = {}
        for f in findings:
            severity_count[f.severity] = severity_count.get(f.severity, 0) + 1
            status_count[f.status] = status_count.get(f.status, 0) + 1

        event_type_count = {}
        for e in events:
            event_type_count[e.event_type] = event_type_count.get(e.event_type, 0) + 1

        # 构建报告
        report = {
            "report_id": f"RPT-{task.id}-{int(datetime.now(timezone.utc).timestamp())}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task": {
                "id": task.id, "task_code": task.task_code,
                "detection_type": task.detection_type,
                "rule_pack_version": task.rule_pack_version,
                "status": task.status,
                # 报告必须能说清「这次分析算不算数」，否则 0 条结论会被读成「未发现风险」
                "analysis_coverage": task.analysis_coverage,
                "coverage_detail": task.coverage_detail or {},
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None
            },
            "app_info": {
                "app_name": app.app_name if app else None,
                "package_name": app.package_name if app else None,
                "version_name": version.version_name if version else None,
                "version_code": version.version_code if version else None,
                "sha256": version.sha256 if version else None,
                "min_sdk": version.min_sdk if version else None,
                "target_sdk": version.target_sdk if version else None
            },
            "summary": {
                "total_findings": len(findings),
                "total_events": len(events),
                "total_evidence": len(evidence),
                "total_scenarios": len(scenarios),
                "severity_distribution": severity_count,
                "status_distribution": status_count,
                "event_type_distribution": event_type_count
            },
            "scenarios": [{
                "id": s.id, "type": s.scenario_type,
                "consent_status": s.consent_status, "status": s.status
            } for s in scenarios],
            "findings": [{
                "id": f.id, "finding_uid": f.finding_uid,
                "title": f.title, "severity": f.severity,
                "status": f.status, "confidence": f.confidence,
                "data_type": f.data_type, "description": f.description,
                "api_path": f.api_path, "network_domain": f.network_domain,
                "remediation_advice": f.remediation_advice,
                "created_at": f.created_at.isoformat() if f.created_at else None
            } for f in findings]
        }

        # 保存报告文件
        report_text = json.dumps(report, ensure_ascii=False, indent=2)
        report_path = storage.save_text(
            report_text, task.id, "reports",
            f"report_{task.task_code}_{int(datetime.now(timezone.utc).timestamp())}.json"
        )

        return {
            "report_id": report["report_id"],
            "report_path": report_path,
            "summary": report["summary"]
        }
