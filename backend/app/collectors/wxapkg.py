"""小程序包采集器：合法取得的未加密 wxapkg（如开发工具预览/构建产物）与解包目录。

合规边界（如实执行）：
- 仅解析未加密 wxapkg（首字节 0xBE 的公开容器格式）；加密包（V1MMWX 等）不做任何解密，
  直接拒绝并说明原因——不包含绕过平台加密/鉴权的能力。
- 线上小程序无合法公开获取途径（见 RESEARCH.md），本采集器面向"合法取得的产物"：
  上传 / 本地路径 / 公开下载 URL 监控。
- 解包目录可直接用本地目录采集器扫描；wxapkg 容器解析补齐"整包"入口。
"""
from __future__ import annotations

import hashlib
import io
import struct
from pathlib import Path

import httpx

from .base import USER_AGENT, BaseCollector, ContentItem, CollectorError, register

MAGIC_UNENCRYPTED = 0xBE
MARKER_ENCRYPTED = b"V1MMWX"
MAX_ENTRIES = 20_000
MAX_TOTAL = 512 * 1024 * 1024


@register
class WxapkgCollector(BaseCollector):
    key = "wxapkg"
    category = "miniprogram"
    platform = "wxapkg"
    title = "小程序包扫描（未加密 wxapkg）"

    def __init__(self, config: dict, client_factory=None, cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory

    def _client(self) -> httpx.AsyncClient:
        if self._client_factory is not None:
            return self._client_factory({"User-Agent": USER_AGENT})
        return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True)

    async def items(self):
        path = (self.config.get("path") or "").strip()
        url = (self.config.get("url") or "").strip()
        if path:
            data = Path(path).read_bytes()
            source_name = Path(path).name
            origin = None
        elif url:
            async with self._client() as client:
                resp = await client.get(url)
            if resp.status_code in (403, 429):
                self.rate_limited = True
                return
            if resp.status_code != 200:
                raise CollectorError(f"wxapkg 下载失败（{resp.status_code}）: {url}")
            data = resp.content
            source_name = url.rsplit("/", 1)[-1] or "download.wxapkg"
            origin = url
        else:
            raise CollectorError("需要配置 path 或 url 之一")
        if not data:
            raise CollectorError(f"空文件: {source_name}")

        pkg_sha = hashlib.sha256(data).hexdigest()
        if data[:6] == MARKER_ENCRYPTED or data[0] not in (MAGIC_UNENCRYPTED,):
            raise CollectorError(
                "该小程序包为加密格式（V1MMWX 等）：出于合规边界不做解密，"
                "仅支持未加密 wxapkg（0xBE）或解包目录（可用本地目录采集器扫描）")

        entries = self._parse_entries(data)
        max_member = self._max_file_bytes() * 8
        count = 0
        for name, blob in entries:
            count += 1
            if count > MAX_ENTRIES:
                raise CollectorError("条目数量超出安全上限")
            if len(blob) > max_member or not self._path_allowed(name):
                continue
            text = self.decode_text(blob)
            if text is None or not text.strip():
                continue
            yield ContentItem(
                kind="wxapkg_entry", platform=self.platform,
                origin_url=origin, repo=source_name,
                path=name, version_id=pkg_sha, version_kind="app_version",
                text=text, size=len(blob),
                published_at=None, published_source="", published_confidence="none",
                extra={"wxapkg_sha256": pkg_sha[:32], "entry_count": len(entries)},
            )

    @staticmethod
    def _parse_entries(data: bytes) -> list[tuple[str, bytes]]:
        """未加密 wxapkg 容器格式：0xBE + indexInfoLen + bodyInfoLen + 0xED + fileCount，
        逐条目 nameLen/name/offset/size（大端）。解析前做全部边界校验，防越界读。"""
        if data[0] != MAGIC_UNENCRYPTED or len(data) < 14:
            raise CollectorError("wxapkg 头部不符合未加密格式")
        index_len, body_len, marker, file_count = struct.unpack(">IIBI", data[1:14])
        if marker != 0xED:
            raise CollectorError("wxapkg 标记字节异常（0xED 缺失）")
        if len(data) < 14 + index_len or len(data) < 14 + index_len + body_len:
            raise CollectorError("wxapkg 索引/正文长度声明越界（疑似损坏或裁剪）")
        if file_count > MAX_ENTRIES:
            raise CollectorError("条目数量声明超出安全上限")
        pos = 14
        body_start = 14 + index_len  # 条目 offset 相对正文起点
        out: list[tuple[str, bytes]] = []
        for _ in range(file_count):
            if pos + 4 > len(data):
                break
            (name_len,) = struct.unpack(">I", data[pos:pos + 4])
            pos += 4
            if name_len > 4096 or pos + name_len + 8 > len(data):
                raise CollectorError("wxapkg 条目名长度越界")
            name = data[pos:pos + name_len].decode("utf-8", errors="replace")
            pos += name_len
            offset, size = struct.unpack(">II", data[pos:pos + 8])
            pos += 8
            if offset + size > body_len or body_start + offset + size > len(data):
                raise CollectorError(f"wxapkg 条目数据越界: {name}")
            out.append((name.replace("\\", "/").lstrip("/"),
                        data[body_start + offset: body_start + offset + size]))
        if not out:
            raise CollectorError("wxapkg 未解析出条目")
        return out

    def test_connection(self) -> dict:
        path = (self.config.get("path") or "").strip()
        url = (self.config.get("url") or "").strip()
        if path:
            p = Path(path)
            if not p.is_file():
                return {"ok": False, "message": f"文件不存在: {path}"}
            head = p.read_bytes()[:6]
            if head == MARKER_ENCRYPTED or p.read_bytes()[0] != MAGIC_UNENCRYPTED:
                return {"ok": False, "message": "加密包：不做解密（合规边界），请提供未加密 wxapkg 或解包目录"}
            return {"ok": True, "message": f"未加密 wxapkg 可解析: {path}"}
        if url:
            try:
                head_resp = httpx.get(url, timeout=20, follow_redirects=True,
                                      headers={"User-Agent": USER_AGENT, "Range": "bytes=0-5"})
                if head_resp.status_code not in (200, 206):
                    return {"ok": False, "message": f"下载入口返回 {head_resp.status_code}"}
                if head_resp.content == MARKER_ENCRYPTED or (head_resp.content and head_resp.content[0] != MAGIC_UNENCRYPTED):
                    return {"ok": False, "message": "加密包：不做解密（合规边界）"}
                return {"ok": True, "message": f"未加密 wxapkg 可访问: {url}"}
            except httpx.HTTPError as exc:
                return {"ok": False, "message": f"网络错误: {exc}"}
        return {"ok": False, "message": "未配置 path 或 url"}
