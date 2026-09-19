"""压缩包导入采集器（zip / tar.*）：内存内逐成员读取，防路径穿越、符号链接与解压炸弹。"""
from __future__ import annotations

import hashlib
import io
import posixpath
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from .base import BaseCollector, ContentItem, CollectorError, register

MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _entry_safe(name: str) -> bool:
    p = PurePosixPath(name)
    if p.is_absolute() or name.startswith("/") or "\\" in name:
        return False
    return all(part not in ("..", "") for part in p.parts)


@register
class ArchiveCollector(BaseCollector):
    key = "archive"
    category = "local_import"
    platform = "archive"
    title = "压缩包导入扫描"

    async def items(self):
        path = Path(self.config.get("path") or "")
        if not path.is_file():
            raise CollectorError(f"压缩包不存在: {path}")
        max_bytes = self._max_file_bytes()
        total = 0
        name = path.name.lower()
        if name.endswith(".zip"):
            for item in self._iter_zip(path, max_bytes, lambda used: self._check_total(used)):
                yield item
        elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
            for item in self._iter_tar(path, max_bytes, lambda used: self._check_total(used)):
                yield item
        else:
            raise CollectorError(f"不支持的压缩包格式: {path.name}")

    def _check_total(self, used: int) -> None:
        if used > MAX_TOTAL_BYTES:
            raise CollectorError("解包总量超出安全上限，已中止（防解压炸弹）")

    def _emit(self, entry_path: str, data: bytes, version_meta: str):
        text = self.decode_text(data)
        if text is None or not self._path_allowed(entry_path):
            return None
        version_id = hashlib.sha256(f"{entry_path}:{version_meta}".encode()).hexdigest()[:32]
        return ContentItem(
            kind="archive_entry", platform=self.platform,
            origin_url=None, repo=Path(self.config.get("path") or "").name,
            path=entry_path, version_id=version_id, version_kind="none",
            text=text, size=len(data),
            published_at=None, published_source="", published_confidence="none",
            extra={"archive": str(self.config.get("path"))},
        )

    def _iter_zip(self, path: Path, max_bytes: int, check_total):
        total = 0
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if not _entry_safe(info.filename):
                    continue  # 路径穿越成员直接忽略
                if info.file_size > max_bytes:
                    continue
                total += info.file_size
                check_total(total)
                data = zf.read(info)
                item = self._emit(info.filename.replace("\\", "/"), data, f"crc{info.CRC}:{info.file_size}")
                if item:
                    yield item

    def _iter_tar(self, path: Path, max_bytes: int, check_total):
        total = 0
        with tarfile.open(path, mode="r:*") as tf:
            for member in tf:
                if not member.isfile() or member.issym() or member.islnk() or member.isdev():
                    continue
                if not _entry_safe(member.name):
                    continue
                if member.size > max_bytes:
                    continue
                total += member.size
                check_total(total)
                fobj = tf.extractfile(member)
                if fobj is None:
                    continue
                data = fobj.read()
                item = self._emit(member.name.replace("\\", "/"), data, f"{member.size}:{member.mtime}")
                if item:
                    yield item

    def test_connection(self) -> dict:
        path = Path(self.config.get("path") or "")
        if path.is_file():
            return {"ok": True, "message": f"压缩包可读: {path}"}
        return {"ok": False, "message": f"压缩包不存在: {path}"}
