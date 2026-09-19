"""业务服务：入库去重、复核审计、统计、导出、规则/能力同步。"""
from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import settings_service
from .db import utcnow
from .detection.engine import Candidate
from .collectors.base import ContentItem
from .models import (
    Capability, Credential, IgnoreRule, Occurrence, ReviewLog, RuleRecord,
    ScanRun, Source, SourceContent, VerificationJob, VerificationResult,
)
from .security import credential_fingerprint, decrypt_text, encrypt_text, mask_preview, location_hash

# ---------- 规则与能力同步 ----------

def sync_rule_records(session: Session, registry) -> None:
    existing = {r.id: r for r in session.query(RuleRecord).all()}
    for rule in registry.rules:
        row = existing.pop(rule.id, None)
        file_sha = ""
        if row is None:
            row = RuleRecord(
                id=rule.id, title=rule.title, type=rule.type, vendor=rule.vendor,
                version=rule.version, license=rule.license, verifier_id=rule.verifier,
                enabled=True, builtin=True, file_sha=file_sha,
            )
            session.add(row)
        else:
            row.title, row.type, row.vendor = rule.title, rule.type, rule.vendor
            row.version, row.license, row.verifier_id = rule.version, rule.license, rule.verifier
    for stale in existing.values():
        session.delete(stale)
    session.commit()


CHANNEL_CAPABILITIES = [
    # (kind, key, title, status, meta)
    ("channel", "code_hosting.github", "GitHub 仓库", "live_verified",
     {"entry": "REST trees+blobs+commits", "limits": "匿名60次/时, 认证5000次/时; 树可能 truncated",
      "history": "提交历史扫描已实现，游标增量（提交时间为低可信公开时间）",
      "live": "2026-09-19 认证态实采用户公开仓库（12文件+53条历史内容）并验证版本缓存",
      "verify_live": "最小验证器实测 valid(200)/invalid(401)"}),
    ("channel", "code_hosting.gitee", "Gitee 仓库", "live_verified",
     {"entry": "API v5 trees+blobs", "live": "2026-09-19 实采 openharmony/docs 内容入库并验证版本缓存增量",
      "limits": "匿名限流不稳定（共享IP），生产建议配置 Token；限流优雅停止已验证"}),
    ("channel", "wiki.mediawiki", "MediaWiki 兼容", "live_verified",
     {"entry": "recentchanges+revisions", "cursor": "rccontinue",
      "live": "2026-09-19 中文维基百科实采6条修订并增量续扫",
      "note": "修订时间戳=可信公开时间(medium)；需符合站点UA策略"}),
    ("channel", "microblog.weibo", "微博", "blocked",
     {"reason": "无合规公开检索接口（需登录态/开放平台权限），不绕过访问控制",
      "remaining": "保留任务；如用户提供账号配置并在合规边界内评估后再接入"}),
    ("channel", "knowledge.csdn", "CSDN", "planned", {"phase": 2, "note": "无官方接口，合规抓取单独评估"}),
    ("channel", "knowledge.cnblogs", "博客园（经通用 RSS）", "live_verified",
     {"live": "2026-09-19 首页RSS实采6条；二轮 ETag 304 未变更跳过"}),
    ("channel", "knowledge.juejin", "掘金", "planned", {"phase": 2, "note": "无官方接口"}),
    ("channel", "knowledge.stackoverflow", "Stack Overflow", "live_verified",
     {"entry": "API 2.3 search+questions", "limits": "匿名配额300/天",
      "live": "2026-09-19 实采6条并验证版本缓存增量"}),
    ("channel", "knowledge.rss_sitemap_url", "通用 RSS/Atom/Sitemap/URL", "live_verified",
     {"cursor": "ETag/Last-Modified", "live": "2026-09-19 经博客园RSS实测",
      "note": "覆盖任何提供订阅源或站点地图的站点"}),
    ("channel", "container.oci", "OCI/Docker Registry", "planned", {"phase": 3}),
    ("channel", "app.apk", "Android APK", "planned", {"phase": 3}),
    ("channel", "miniprogram.package", "小程序产物", "planned", {"phase": 3}),
    ("channel", "local_import.local_dir", "本地目录", "offline_tested", {}),
    ("channel", "local_import.archive", "压缩包导入", "offline_tested", {}),
]


def seed_capabilities(session: Session) -> None:
    """seed 只新增/更新计划行，不覆盖已提升的状态（offline_tested/live_verified 在 DB 中演进）。"""
    for kind, key, title, status, meta in CHANNEL_CAPABILITIES:
        row = session.get(Capability, f"{kind}:{key}")
        if row is None:
            session.add(Capability(id=f"{kind}:{key}", kind=kind, key=key,
                                   title=title, status=status, meta_json=meta))
    session.commit()


# ---------- 忽略规则 ----------

def match_ignore_rules(session: Session, cand: Candidate, category: str, path: str) -> str | None:
    for rule in session.query(IgnoreRule).filter(IgnoreRule.enabled == True).all():  # noqa: E712
        if rule.scope_type == "rule" and rule.scope_value == cand.rule_id:
            return f"忽略规则#{rule.id}: 规则 {rule.scope_value}"
        if rule.scope_type == "path_glob" and fnmatch.fnmatch(path, rule.scope_value):
            return f"忽略规则#{rule.id}: 路径 {rule.scope_value}"
        if rule.scope_type == "category" and rule.scope_value == category:
            return f"忽略规则#{rule.id}: 类别 {rule.scope_value}"
        if rule.scope_type == "fingerprint_prefix":
            fp = credential_fingerprint(cand.type, cand.secret)
            if fp.startswith(rule.scope_value):
                return f"忽略规则#{rule.id}: 指纹前缀"
    return None


# ---------- 入库与去重 ----------

def mask_context(text: str, secret: str, limit: int = 2000) -> str:
    masked = text.replace(secret, mask_preview(secret)) if secret else text
    return masked[:limit]


def ingest_candidate(session: Session, item: ContentItem, content_row_id: int | None,
                     run_id: int | None, cand: Candidate, ignore_reason: str | None) -> dict:
    now = utcnow()
    paired = cand.evidence.get("paired") or {}
    fingerprint = credential_fingerprint(cand.type, cand.secret, paired or None)
    cred = session.query(Credential).filter(Credential.fingerprint == fingerprint).first()
    created_cred = False
    if cred is None:
        cred = Credential(
            fingerprint=fingerprint, type=cand.type, vendor=cand.vendor,
            rule_id=cand.rule_id, rule_version=cand.rule_version,
            confidence=cand.confidence,
            secret_encrypted=encrypt_text(cand.secret),
            paired_encrypted=encrypt_text(json.dumps(paired, ensure_ascii=False)) if paired else None,
            preview=mask_preview(cand.secret),
            review_status="ignored" if ignore_reason else "pending",
            verification_status="not_requested",
        )
        session.add(cred)
        session.flush()
        created_cred = True
        if ignore_reason:
            session.add(ReviewLog(credential_id=cred.id, action="ignore",
                                  note=ignore_reason, actor="system"))
    else:
        cred.last_seen_at = now
        cred.confidence = max(cred.confidence, cand.confidence)
        if ignore_reason and cred.review_status == "pending":
            cred.review_status = "ignored"
            session.add(ReviewLog(credential_id=cred.id, action="ignore",
                                  note=ignore_reason, actor="system"))

    secret_hash = hashlib.sha256(cand.secret.encode("utf-8")).hexdigest()  # 稳定哈希，跨进程一致
    loc = location_hash(item.platform, item.origin_url, item.repo, item.path,
                        item.version_id, cand.line_start, secret_hash)
    occ = session.query(Occurrence).filter(
        Occurrence.credential_id == cred.id, Occurrence.location_hash == loc).first()
    created_occ = False
    if occ is None:
        context = ""
        if item.text:
            lines = item.text.split("\n")
            lo = max(0, cand.line_start - 3)
            hi = min(len(lines), cand.line_end + 2)
            context = mask_context("\n".join(lines[lo:hi]), cand.secret)
        occ = Occurrence(
            credential_id=cred.id, content_id=content_row_id, run_id=run_id,
            category=_category_of(item), platform=item.platform,
            origin_url=item.origin_url, repo=item.repo, path=item.path,
            line_start=cand.line_start, version_id=item.version_id,
            version_kind=item.version_kind, context_masked=context,
            content_hash=None, location_hash=loc,
            evidence_json={
                "rule_id": cand.rule_id, "rule_version": cand.rule_version,
                "evidence": cand.evidence, "paired_fields": sorted(paired.keys()),
            },
        )
        session.add(occ)
        created_occ = True
    else:
        occ.last_seen_at = now
    return {"credential_created": created_cred, "occurrence_created": created_occ}


def _category_of(item: ContentItem) -> str:
    from .collectors.base import all_collectors
    for cls in all_collectors().values():
        if cls.platform == item.platform:
            return cls.category
    return "unknown"


# ---------- 复核与审计 ----------

_REVIEW_TRANSITIONS = {
    "confirm": ("pending", "confirmed"),
    "false_positive": ("pending", "false_positive"),
    "ignore": ("pending", "ignored"),
    "restore": ("confirmed", "pending"),
}


def review_credential(session: Session, credential_id: int, action: str, note: str | None, actor: str = "local") -> Credential:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise ValueError("凭据不存在")
    if action not in _REVIEW_TRANSITIONS:
        raise ValueError(f"不支持的复核动作: {action}")
    src, dst = _REVIEW_TRANSITIONS[action]
    if cred.review_status not in src and action != "restore":
        raise ValueError(f"当前复核状态 {cred.review_status} 不允许 {action}")
    cred.review_status = dst
    session.add(ReviewLog(credential_id=cred.id, action=action, note=note, actor=actor))
    session.commit()
    return cred


def reveal_credential(session: Session, credential_id: int, actor: str = "local") -> str:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise ValueError("凭据不存在")
    secret = decrypt_text(cred.secret_encrypted)
    session.add(ReviewLog(credential_id=cred.id, action="reveal_access",
                          note="界面查看原文", actor=actor))
    session.commit()
    return secret or ""


# ---------- 统计 ----------

def overview_stats(session: Session) -> dict:
    cred_total = session.query(func.count(Credential.id)).scalar() or 0
    occ_total = session.query(func.count(Occurrence.id)).scalar() or 0
    by_review = dict(session.query(Credential.review_status, func.count(Credential.id))
                     .group_by(Credential.review_status).all())
    by_verify = dict(session.query(Credential.verification_status, func.count(Credential.id))
                     .group_by(Credential.verification_status).all())
    by_platform = [list(row) for row in session.query(Occurrence.platform, func.count(Occurrence.id))
                   .group_by(Occurrence.platform).all()]
    by_type = [list(row) for row in session.query(Credential.type, func.count(Credential.id))
               .group_by(Credential.type).order_by(func.count(Credential.id).desc()).limit(20).all()]
    queued_jobs = session.query(func.count(VerificationJob.id)).filter(
        VerificationJob.status == "queued").scalar() or 0
    running_tasks = session.query(func.count(ScanRun.id)).filter(
        ScanRun.status == "running").scalar() or 0
    last_runs = session.query(ScanRun).order_by(ScanRun.started_at.desc()).limit(10).all()
    # 发现延迟：仅统计有可靠公开时间的内容（阶段1渠道多为 none，样本数会如实为 0）
    latencies = [
        (occ.detected_at - c.published_at).total_seconds()
        for occ, c in session.query(Occurrence, SourceContent)
        .join(SourceContent, Occurrence.content_id == SourceContent.id)
        .filter(SourceContent.published_confidence.in_(("high", "medium"))).limit(5000)
    ]
    latencies.sort()
    def _pct(p):
        if not latencies:
            return None
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]
    return {
        "credentials_total": cred_total,
        "occurrences_total": occ_total,
        "by_review_status": by_review,
        "by_verification_status": by_verify,
        "by_platform": by_platform,
        "by_type_top": by_type,
        "verification_queue": queued_jobs,
        "running_scans": running_tasks,
        "recent_runs": [{
            "id": r.id, "task_id": r.task_id, "status": r.status,
            "trigger": r.trigger, "started_at": _iso(r.started_at),
            "stats": r.stats_json,
        } for r in last_runs],
        "detection_latency": {
            "sample_count": len(latencies),
            "p50_seconds": _pct(0.5),
            "p95_seconds": _pct(0.95),
            "note": "仅统计具备可靠公开时间（medium/high 置信）的样本；无公开时间不参与计算",
        },
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


# ---------- 导出 ----------

EXPORT_FIELDS = [
    "credential_id", "type", "vendor", "confidence", "review_status",
    "verification_status", "preview", "secret", "first_seen_at", "last_seen_at",
    "platform", "origin_url", "repo", "path", "line_start", "version_id",
]


def iter_export_rows(session: Session, masked: bool, filters: dict):
    query = session.query(Credential, Occurrence).join(
        Occurrence, Occurrence.credential_id == Credential.id).yield_per(200)
    if filters.get("type"):
        query = query.filter(Credential.type == filters["type"])
    if filters.get("review"):
        query = query.filter(Credential.review_status == filters["review"])
    if filters.get("verify"):
        query = query.filter(Credential.verification_status == filters["verify"])
    if filters.get("platform"):
        query = query.filter(Occurrence.platform == filters["platform"])
    for cred, occ in query:
        secret = "" if masked else (decrypt_text(cred.secret_encrypted) or "")
        yield {
            "credential_id": cred.id, "type": cred.type, "vendor": cred.vendor,
            "confidence": cred.confidence, "review_status": cred.review_status,
            "verification_status": cred.verification_status,
            "preview": cred.preview, "secret": secret if not masked else cred.preview,
            "first_seen_at": _iso(cred.first_seen_at), "last_seen_at": _iso(cred.last_seen_at),
            "platform": occ.platform, "origin_url": occ.origin_url, "repo": occ.repo,
            "path": occ.path, "line_start": occ.line_start, "version_id": occ.version_id,
        }


def csv_escape_cell(value) -> str:
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@"):
        s = "'" + s
    return s


def export_csv(rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_FIELDS)
    for row in rows:
        writer.writerow([csv_escape_cell(row.get(f)) for f in EXPORT_FIELDS])
    return buf.getvalue()
