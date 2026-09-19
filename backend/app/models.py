"""全部 ORM 实体。字段语义见 docs/INTERFACES.md。

约定：所有时间字段存 naive UTC（db.utcnow）；敏感字段存 Fernet 密文。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))          # code_hosting/wiki/...
    platform: Mapped[str] = mapped_column(String(50))          # github/gitee/local/...
    collector_key: Mapped[str] = mapped_column(String(50))     # 插件键
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="source", cascade="all,delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    mode: Mapped[str] = mapped_column(String(20), default="continuous")  # manual/continuous
    status: Mapped[str] = mapped_column(String(20), default="pending")   # pending/running/paused/done/failed/cancelled
    interval_sec: Mapped[int] = mapped_column(Integer, default=300)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    source: Mapped[Source] = relationship(back_populates="tasks")
    runs: Mapped[list["ScanRun"]] = relationship(back_populates="task", cascade="all,delete-orphan")


class ScanRun(Base):
    __tablename__ = "scan_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running/completed/failed/cancelled/interrupted
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual/schedule
    stats_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[Task] = relationship(back_populates="runs")


class Cursor(Base):
    __tablename__ = "cursors"
    __table_args__ = (UniqueConstraint("task_id", "cursor_key", name="uq_cursor_task_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    cursor_key: Mapped[str] = mapped_column(String(200))
    cursor_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SourceContent(Base):
    __tablename__ = "source_contents"
    __table_args__ = (
        UniqueConstraint("source_id", "version_id", "path", "content_hash", name="uq_content_version"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="file")
    platform: Mapped[str] = mapped_column(String(50))
    origin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    path: Mapped[str] = mapped_column(String(500))
    version_id: Mapped[str] = mapped_column(String(200))
    version_kind: Mapped[str] = mapped_column(String(30), default="none")
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_confidence: Mapped[str] = mapped_column(String(20), default="none")
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    detection_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/done/skipped/failed


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    vendor: Mapped[str] = mapped_column(String(80), default="")
    rule_id: Mapped[str] = mapped_column(String(100))
    rule_version: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[int] = mapped_column(Integer, default=50)
    secret_encrypted: Mapped[str] = mapped_column(Text)
    paired_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview: Mapped[str] = mapped_column(String(100), default="")
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/confirmed/false_positive/ignored
    verification_status: Mapped[str] = mapped_column(String(30), default="not_requested", index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Occurrence(Base):
    __tablename__ = "occurrences"
    __table_args__ = (UniqueConstraint("credential_id", "location_hash", name="uq_occurrence_cred_loc"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id"), index=True)
    content_id: Mapped[int | None] = mapped_column(ForeignKey("source_contents.id"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("scan_runs.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(50))
    platform: Mapped[str] = mapped_column(String(50))
    origin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    path: Mapped[str] = mapped_column(String(500))
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version_kind: Mapped[str] = mapped_column(String(30), default="none")
    context_masked: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_hash: Mapped[str] = mapped_column(String(64))
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewLog(Base):
    __tablename__ = "review_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id"), index=True)
    action: Mapped[str] = mapped_column(String(30))  # confirm/false_positive/ignore/restore/reveal_access/auto_verified
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(50), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VerificationJob(Base):
    __tablename__ = "verification_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id"), index=True)
    verifier_id: Mapped[str] = mapped_column(String(80))
    requested_by: Mapped[str] = mapped_column(String(20), default="single")  # single/batch/auto
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued/running/finished/cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VerificationResult(Base):
    __tablename__ = "verification_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("verification_jobs.id"), nullable=True)
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id"), index=True)
    verifier_id: Mapped[str] = mapped_column(String(80))
    verifier_version: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(30))  # 语义见 INTERFACES.md
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RuleRecord(Base):
    __tablename__ = "rule_records"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(80), index=True)
    vendor: Mapped[str] = mapped_column(String(80), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    license: Mapped[str] = mapped_column(String(50), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    verifier_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    file_sha: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class IgnoreRule(Base):
    __tablename__ = "ignore_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(30))   # rule/path_glob/fingerprint_prefix/category
    scope_value: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Capability(Base):
    __tablename__ = "capabilities"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)  # kind:key
    kind: Mapped[str] = mapped_column(String(30), index=True)       # collector/verifier/channel/rule
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="planned")  # planned/implemented/offline_tested/live_verified/unsupported
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
