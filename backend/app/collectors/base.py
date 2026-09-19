"""采集器插件契约与注册表。实现者只产出 ContentItem，不写库、不检测。"""
from __future__ import annotations

import fnmatch
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from ..db import utcnow


@dataclass
class ContentItem:
    kind: str                      # file / page / blob / archive_entry / layer_entry / apk_entry ...
    platform: str
    origin_url: str | None
    repo: str | None
    path: str
    version_id: str
    version_kind: str = "none"     # commit/digest/revision/tag/app_version/blob/none
    text: str | None = None
    size: int = 0
    published_at: datetime | None = None
    published_source: str = ""
    published_confidence: str = "none"
    source_updated_at: datetime | None = None
    fetched_at: datetime = field(default_factory=utcnow)
    extra: dict = field(default_factory=dict)


class CollectorError(RuntimeError):
    """致命错误（如仓库不存在）。限流不是 CollectorError，属于正常停止语义。"""


class BaseCollector:
    key: str = ""
    category: str = ""
    platform: str = ""
    title: str = ""
    version: str = "1.0.0"

    def __init__(self, config: dict):
        self.config = config or {}

    async def items(self) -> AsyncIterator[ContentItem]:
        raise NotImplementedError
        yield  # pragma: no cover

    def test_connection(self) -> dict:
        return {"ok": False, "message": "该采集器不支持连接测试"}

    # ---- 通用工具 ----
    def _filters(self) -> tuple[list[str], list[str]]:
        c = self.config or {}
        return list(c.get("include_globs") or []), list(c.get("exclude_globs") or [])

    def _path_allowed(self, path: str) -> bool:
        include, exclude = self._filters()
        if exclude and any(fnmatch.fnmatch(path, pat) for pat in exclude):
            return False
        if include and not any(fnmatch.fnmatch(path, pat) for pat in include):
            return False
        return True

    def _max_file_bytes(self, default: int = 1024 * 1024) -> int:
        return int((self.config or {}).get("max_file_bytes") or default)

    @staticmethod
    def decode_text(data: bytes) -> str | None:
        """二进制跳过（NUL 探测），文本按 UTF-8 宽松解码。"""
        if b"\x00" in data[:8192]:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return data.decode("gb18030")
            except UnicodeDecodeError:
                return None


_COLLECTORS: dict[str, type[BaseCollector]] = {}


def register(cls: type[BaseCollector]) -> type[BaseCollector]:
    _COLLECTORS[cls.key] = cls
    return cls


def get_collector_class(key: str) -> type[BaseCollector] | None:
    return _COLLECTORS.get(key)


def all_collectors() -> dict[str, type[BaseCollector]]:
    return dict(_COLLECTORS)


# 导入触发注册
from . import local_dir, archive, github  # noqa: E402,F401
