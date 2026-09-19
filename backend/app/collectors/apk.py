"""Android APK 采集器：合法取得的 APK 文件（上传/本地路径/公开下载 URL 监控）。

- APK 本质是 zip：文本类成员（assets/res-raw/META-INF/配置）直接扫描；
- classes*.dex 提取可打印字符串序列后扫描（凭据常以字符串常量存在）；
- AndroidManifest.xml 为二进制 XML：可选使用 Androguard 解析包名/版本（未安装则如实跳过）；
- 版本监控：URL 模式以 APK 内容 sha256 为版本（重复下载相同包自动跳过）；
- 不执行未知应用（纯静态）；限制：成员数/成员大小/解压总量。
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path

import httpx

from .base import USER_AGENT, BaseCollector, ContentItem, CollectorError, register

MAX_MEMBERS = 20_000
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
TEXT_SUFFIXES = (".json", ".xml", ".properties", ".txt", ".yml", ".yaml", ".ini", ".cfg",
                 ".conf", ".md", ".js", ".ts", ".html", ".csv", ".env", ".pem", ".sql")
TEXT_PREFIX_DIRS = ("assets/", "res/raw/", "META-INF/")
_DEX_STRING = re.compile(rb"[\x20-\x7e]{8,}")


def _dex_strings(data: bytes, cap: int = 200_000) -> str:
    parts: list[str] = []
    total = 0
    for m in _DEX_STRING.finditer(data):
        s = m.group(0).decode("ascii", errors="ignore")
        parts.append(s)
        total += len(s) + 1
        if total > cap:
            break
    return "\n".join(parts)


def _try_manifest_info(data: bytes) -> dict:
    """可选 Androguard 解析二进制 manifest；未安装则返回空（如实跳过）。"""
    try:
        from androguard.core.axml import AXMLPrinter  # type: ignore
    except Exception:
        return {}
    try:
        xml = AXMLPrinter(data).get_xml().decode("utf-8", errors="ignore")
        pkg = __import__("re").search(r'package="([^"]+)"', xml)
        ver = __import__("re").search(r'android:versionName="([^"]+)"', xml)
        return {"package": pkg.group(1) if pkg else None,
                "version_name": ver.group(1) if ver else None}
    except Exception:
        return {}


@register
class ApkCollector(BaseCollector):
    key = "apk"
    category = "app"
    platform = "apk"
    title = "Android APK 静态扫描"

    def __init__(self, config: dict, client_factory=None, cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory

    def _client(self) -> httpx.AsyncClient:
        if self._client_factory is not None:
            return self._client_factory({"User-Agent": USER_AGENT})
        return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=120,
                                 follow_redirects=True)

    async def items(self):
        path = (self.config.get("path") or "").strip()
        url = (self.config.get("url") or "").strip()
        origin = None
        if path:
            data = Path(path).read_bytes()
            source_name = Path(path).name
        elif url:
            async with self._client() as client:
                resp = await client.get(url)
            if resp.status_code in (403, 429):
                self.rate_limited = True
                return
            if resp.status_code != 200:
                raise CollectorError(f"APK 下载失败（{resp.status_code}）: {url}")
            data = resp.content
            source_name = url.rsplit("/", 1)[-1] or "download.apk"
            origin = url
        else:
            raise CollectorError("需要配置 path 或 url 之一")
        if len(data) < 4 or data[:2] != b"PK":
            raise CollectorError(f"不是有效的 APK（zip）文件: {source_name}")

        apk_sha = hashlib.sha256(data).hexdigest()
        max_member = self._max_file_bytes() * 8
        total = 0
        count = 0
        manifest_extra: dict = {}
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                count += 1
                if count > MAX_MEMBERS:
                    raise CollectorError("APK 成员数量超出安全上限")
                if info.is_dir():
                    continue
                total += info.file_size
                if total > MAX_TOTAL_UNCOMPRESSED:
                    raise CollectorError("APK 解压总量超出安全上限")
                name = info.filename.replace("\\", "/")
                if name.endswith("AndroidManifest.xml") and not manifest_extra:
                    manifest_extra = _try_manifest_info(zf.read(info))
                    manifest_extra = {k: v for k, v in manifest_extra.items() if v}
                    continue
                if not (name.endswith(TEXT_SUFFIXES) or name.startswith(TEXT_PREFIX_DIRS)):
                    continue
                if info.file_size > max_member or info.file_size == 0:
                    continue
                if not self._path_allowed(name):
                    continue
                raw = zf.read(info)
                text = self.decode_text(raw)
                if text is None or not text.strip():
                    continue
                yield ContentItem(
                    kind="apk_entry", platform=self.platform,
                    origin_url=origin, repo=source_name,
                    path=name, version_id=apk_sha, version_kind="app_version",
                    text=text, size=info.file_size,
                    published_at=None, published_source="", published_confidence="none",
                    extra={"apk_sha256": apk_sha[:32], **manifest_extra},
                )
            # dex 字符串
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if not re.fullmatch(r"classes\d*\.dex", name.rsplit("/", 1)[-1]):
                    continue
                if info.file_size > max_member:
                    continue
                strings = _dex_strings(zf.read(info))
                if not strings:
                    continue
                yield ContentItem(
                    kind="apk_dex_strings", platform=self.platform,
                    origin_url=origin, repo=source_name,
                    path=f"{name}#strings", version_id=apk_sha, version_kind="app_version",
                    text=strings, size=len(strings),
                    published_at=None, published_source="", published_confidence="none",
                    extra={"apk_sha256": apk_sha[:32], **manifest_extra},
                )

    def test_connection(self) -> dict:
        path = (self.config.get("path") or "").strip()
        url = (self.config.get("url") or "").strip()
        if path:
            p = Path(path)
            return {"ok": p.is_file(), "message": f"APK 文件{'存在' if p.is_file() else '不存在'}: {path}"}
        if url:
            try:
                head = httpx.head(url, timeout=20, follow_redirects=True,
                                  headers={"User-Agent": USER_AGENT})
                return {"ok": head.status_code == 200,
                        "message": f"下载入口返回 {head.status_code}"}
            except httpx.HTTPError as exc:
                return {"ok": False, "message": f"网络错误: {exc}"}
        return {"ok": False, "message": "未配置 path 或 url"}
