"""流水线测试：入库、去重、多位置关联、忽略规则、重启恢复。"""
import random
import string

from app import pipeline, scheduler, services
from app.collectors.local_dir import LocalDirCollector
from app.db import utcnow
from app.models import Credential, IgnoreRule, Occurrence, ReviewLog, ScanRun, Source, Task
from app.security import decrypt_text


def rand_alnum(n: int) -> str:
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def make_source(session, path: str, name: str = "t") -> tuple[Source, Task]:
    source = Source(name=name, category="local_import", platform="local",
                    collector_key="local_dir", config_json={"path": path}, enabled=True)
    session.add(source)
    session.flush()
    task = Task(source_id=source.id, mode="manual", interval_sec=300, status="pending")
    session.add(task)
    session.commit()
    return source, task


def test_scan_dedup_and_multi_location(tmp_path, db):
    token = "ghp_" + rand_alnum(36)
    (tmp_path / "a.env").write_text(f"GITHUB_TOKEN={token}", encoding="utf-8")
    (tmp_path / "b.env").write_text(f"token: {token}", encoding="utf-8")
    source, task = make_source(db, str(tmp_path), "dedup")

    stats = pipeline.run_task(task.id, "manual")
    assert stats["new_credentials"] >= 1
    assert stats["stop_reason"] == "completed"

    cred = db.query(Credential).filter(Credential.type == "github_pat").all()
    target = [c for c in cred if decrypt_text(c.secret_encrypted) == token]
    assert len(target) == 1, "同一凭据必须归并为一个实体"
    occs = db.query(Occurrence).filter(Occurrence.credential_id == target[0].id).all()
    assert len(occs) == 2, "同凭据两个文件应为两个位置"
    assert {o.path for o in occs} == {"a.env", "b.env"}

    # 重复扫描：幂等，不新增凭据/位置
    stats2 = pipeline.run_task(task.id, "manual")
    assert stats2["new_credentials"] == 0
    assert stats2["new_occurrences"] == 0
    assert stats2["items_skipped"] == 2
    occs_after = db.query(Occurrence).filter(Occurrence.credential_id == target[0].id).count()
    assert occs_after == 2


def test_review_transitions_and_audit(tmp_path, db):
    token = "ghp_" + rand_alnum(36)
    (tmp_path / "a.env").write_text(f"GITHUB_TOKEN={token}", encoding="utf-8")
    _, task = make_source(db, str(tmp_path), "review")
    pipeline.run_task(task.id, "manual")
    cred = [c for c in db.query(Credential).all() if decrypt_text(c.secret_encrypted) == token][0]

    services.review_credential(db, cred.id, "confirm", "确认真实")
    assert cred.review_status == "confirmed"
    services.review_credential(db, cred.id, "restore", None)
    assert cred.review_status == "pending"
    services.review_credential(db, cred.id, "false_positive", "格式误报")
    assert cred.review_status == "false_positive"
    actions = [l.action for l in db.query(ReviewLog).filter(ReviewLog.credential_id == cred.id)]
    assert actions == ["confirm", "restore", "false_positive"]


def test_ignore_rule_marks_not_deletes(tmp_path, db):
    token = "ghp_" + rand_alnum(36)
    (tmp_path / "noise.env").write_text(f"GITHUB_TOKEN={token}", encoding="utf-8")
    db.add(IgnoreRule(scope_type="path_glob", scope_value="noise.env", reason="测试忽略", enabled=True))
    db.commit()
    _, task = make_source(db, str(tmp_path), "ignore")
    pipeline.run_task(task.id, "manual")

    cred = [c for c in db.query(Credential).all() if decrypt_text(c.secret_encrypted) == token][0]
    assert cred.review_status == "ignored", "命中忽略规则应标记而非丢弃"
    log = db.query(ReviewLog).filter(ReviewLog.credential_id == cred.id).first()
    assert log and "忽略规则" in log.note


def test_time_fields_published_unknown(tmp_path, db):
    token = "ghp_" + rand_alnum(36)
    (tmp_path / "a.env").write_text(f"GITHUB_TOKEN={token}", encoding="utf-8")
    _, task = make_source(db, str(tmp_path), "time")
    pipeline.run_task(task.id, "manual")
    for c in db.query(Credential).all():
        if decrypt_text(c.secret_encrypted) == token:
            occ = db.query(Occurrence).filter(Occurrence.credential_id == c.id).first()
            content = occ and None
            assert c.first_seen_at <= c.last_seen_at
            assert c.verified_at is None, "默认不验证"


def test_restart_recovery(db):
    _, task = make_source(db, "/nonexistent-path-for-recovery", "recover")
    task.status = "running"
    run = ScanRun(task_id=task.id, status="running", trigger="schedule")
    db.add(run)
    db.commit()

    recovered = scheduler.recover_interrupted(db)
    assert recovered >= 1
    db.refresh(run)
    db.refresh(task)
    assert run.status == "interrupted"
    assert task.status == "pending"


def test_already_running_task_skipped(tmp_path, db):
    (tmp_path / "a.env").write_text("GITHUB_TOKEN=ghp_" + rand_alnum(36), encoding="utf-8")
    _, task = make_source(db, str(tmp_path), "overlap")
    task.status = "running"
    db.commit()
    stats = pipeline.run_task(task.id, "manual")
    assert stats == {"skipped": "already_running"}, "同任务禁止重叠执行"
