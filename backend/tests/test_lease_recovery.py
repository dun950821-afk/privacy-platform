from app.engine.repository import (
    claim_execution, claim_queued_executions, recover_expired_leases, cas_update_execution,
)


def test_stale_worker_cannot_write_after_reclaim(db, execution, expire_lease):
    first = claim_execution(db, execution.id, "worker-a", lease_seconds=60)
    assert first
    expire_lease(db, execution.id)
    second = claim_execution(db, execution.id, "worker-b", lease_seconds=60)
    assert second
    assert not cas_update_execution(db, execution.id, first.lease_token, first.state_version, status="running")
    assert cas_update_execution(db, execution.id, second.lease_token, second.state_version, status="running")


def test_recover_expired_lease_requeues_execution(db, execution, expire_lease):
    execution.status = "running"
    db.commit()
    claim_execution(db, execution.id, "worker-a", lease_seconds=60)
    expire_lease(db, execution.id)
    recovered = recover_expired_leases(db)
    assert execution.id in recovered
    db.refresh(execution)
    assert execution.status == "queued"
    assert execution.lease_token is None


def test_recover_marks_failed_when_attempts_exhausted(db, execution, expire_lease):
    execution.status = "running"
    execution.attempt_no = 4
    db.commit()
    claim_execution(db, execution.id, "worker-a", lease_seconds=60)
    expire_lease(db, execution.id)
    recover_expired_leases(db, max_attempts=4)
    db.refresh(execution)
    assert execution.status == "failed"
    assert execution.error_code == "ENGINE_PROCESS_CRASHED"


def test_claim_queued_executions_returns_unqueued_rows(db, execution):
    from app.models import EngineExecution
    claimed = claim_queued_executions(db, limit=500)
    assert execution.id in claimed
    rows = db.query(EngineExecution).filter(EngineExecution.id.in_(claimed)).all()
    assert all(row.status == "queued" and row.lease_token is None for row in rows)


def test_second_worker_cannot_claim_while_lease_is_valid(db, execution):
    first = claim_execution(db, execution.id, "worker-a", lease_seconds=60)
    assert first
    assert claim_execution(db, execution.id, "worker-b", lease_seconds=60) is None


def test_claim_skips_terminal_execution(db, execution):
    execution.status = "completed"
    db.commit()
    assert claim_execution(db, execution.id, "worker-a", lease_seconds=60) is None


def test_recovery_requeues_parent_task(db, execution, expire_lease):
    from app.models import DetectionTask
    execution.status = "running"
    db.query(DetectionTask).filter(DetectionTask.id == execution.task_id).update({"status": "running_static"})
    db.commit()
    claim_execution(db, execution.id, "worker-a", lease_seconds=60)
    expire_lease(db, execution.id)
    recover_expired_leases(db)
    task = db.query(DetectionTask).get(execution.task_id)
    assert task.status == "queued"
