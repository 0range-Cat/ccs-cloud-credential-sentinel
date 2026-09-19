"""本地目录采集器：分析/测试入口，不计入公开渠道类别。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .base import BaseCollector, ContentItem, register

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "data"}


@register
class LocalDirCollector(BaseCollector):
    key = "local_dir"
    category = "local_import"
    platform = "local"
    title = "本地目录扫描"

    async def items(self):
        root = Path(self.config.get("path") or "")
        if not root.is_dir():
            raise RuntimeError(f"目录不存在: {root}")
        max_bytes = self._max_file_bytes()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                full = Path(dirpath) / name
                rel = str(full.relative_to(root)).replace("\\", "/")
                if not self._path_allowed(rel):
                    continue
                try:
                    stat = full.stat()
                except OSError:
                    continue
                if stat.st_size > max_bytes:
                    continue
                try:
                    data = full.read_bytes()
                except OSError:
                    continue
                text = self.decode_text(data)
                if text is None:
                    continue
                stat_ = full.stat()
                version_id = hashlib.sha256(f"{rel}:{stat_.st_size}:{stat_.st_mtime_ns}".encode()).hexdigest()[:32]
                yield ContentItem(
                    kind="file", platform=self.platform,
                    origin_url=None, repo=None, path=rel,
                    version_id=version_id, version_kind="none",
                    text=text, size=stat_.st_size,
                    published_at=None, published_source="", published_confidence="none",
                    extra={"local_root": str(root)},
                )

    def test_connection(self) -> dict:
        path = Path(self.config.get("path") or "")
        if path.is_dir():
            return {"ok": True, "message": f"目录可访问: {path}"}
        return {"ok": False, "message": f"目录不存在: {path}"}
