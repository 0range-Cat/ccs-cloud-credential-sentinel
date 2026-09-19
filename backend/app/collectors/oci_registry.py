"""容器镜像采集器：OCI Distribution API 兼容（Docker Hub / ghcr / 阿里云等）。

- 以 config digest 作为镜像版本（同一 tag 重扫即跳过；digest 变化才重新拉取）。
- 逐层解析 tar：处理 whiteout（.wh. 文件）与 opaque 标记；区分"当前视图可见"与"历史层残留"。
- 资源限制：层总量、单成员大小、成员数量、解压后总量熔断。
- 公开时间：镜像配置 created 为构建时间（low 可信），不冒充发布时间。
- 匿名拉取走 Docker Hub token 流程；其他 registry 遵循同样的 401 Bearer 流程。
"""
from __future__ import annotations

import base64
import gzip
import io
import json
import re
import tarfile
from datetime import datetime
from urllib.parse import urlparse

import httpx

from .base import USER_AGENT, BaseCollector, ContentItem, CollectorError, register

DOCKER_AUTH = "https://auth.docker.io/token"
DOCKER_REGISTRY = "https://registry-1.docker.io"
MAX_MEMBERS = 20_000
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024

_ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])

_IMAGE_REF = re.compile(
    r"^(?:(?P<registry>[^/]+\.[^/]+)/)?(?P<repo>[A-Za-z0-9._/-]+?)(?::(?P<tag>[\w.-]+))?(?:@(?P<digest>sha256:[0-9a-f]{64}))?$"
)


def parse_image_ref(ref: str) -> dict:
    ref = (ref or "").strip()
    if ref.startswith("docker://"):
        ref = ref[9:]
    m = _IMAGE_REF.match(ref)
    if not m or not m.group("repo"):
        raise CollectorError(f"无法解析镜像引用: {ref}")
    registry = m.group("registry") or "docker.io"
    repo = m.group("repo")
    if registry == "docker.io" and "/" not in repo:
        repo = f"library/{repo}"
    tag = m.group("tag") or ("latest" if not m.group("digest") else None)
    digest = m.group("digest")
    if not tag and not digest:
        tag = "latest"
    return {"registry": registry, "repo": repo, "tag": tag, "digest": digest}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


@register
class OCIRegistryCollector(BaseCollector):
    key = "oci_registry"
    category = "container"
    platform = "oci"  # item.platform 取 registry 主机
    title = "容器镜像层扫描"

    def __init__(self, config: dict, client_factory=None, cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory
        self.rate_limited = False
        self.auth_error: str | None = None

    # ---------- HTTP ----------
    def _client(self, base_url: str, headers: dict | None = None) -> httpx.AsyncClient:
        h = {"User-Agent": USER_AGENT}
        h.update(headers or {})
        if self._client_factory is not None:
            return self._client_factory(base_url, h)
        return httpx.AsyncClient(base_url=base_url, headers=h, timeout=60, follow_redirects=False)

    async def _bearer(self, client, registry: str, repo: str) -> str | None:
        """匿名（或带静态凭据）Bearer token 获取；非 Docker Hub 的匿名流程相同。"""
        if registry.startswith("docker.io"):
            auth_url = DOCKER_AUTH
            service = "registry.docker.io"
        else:
            auth_url = f"https://{registry}/v2/"
            resp = await client.get(auth_url)
            if resp.status_code == 200:
                return None  # 该 registry 免认证
            www_auth = resp.headers.get("www-authenticate", "")
            realm = self._realm(www_auth)
            service = self._service(www_auth) or registry
            if not realm:
                return None
            auth_url = realm
        params = {"service": service, "scope": f"repository:{repo}:pull"}
        resp = await client.get(auth_url, params=params)
        if resp.status_code != 200:
            self.auth_error = f"获取 registry token 失败（{resp.status_code}）"
            return None
        return resp.json().get("token")

    @staticmethod
    def _realm(www_auth: str) -> str | None:
        m = re.search(r'realm="([^"]+)"', www_auth)
        return m.group(1) if m else None

    @staticmethod
    def _service(www_auth: str) -> str | None:
        m = re.search(r'service="([^"]+)"', www_auth)
        return m.group(1) if m else None

    async def _get_json(self, client, url: str, headers: dict | None = None):
        # registry 会把 blob/manifest 307 到 CDN，采集层需要跟随重定向
        resp = await client.get(url, headers=headers, follow_redirects=True)
        if resp.status_code in (403, 429):
            self.rate_limited = True
            return None
        if resp.status_code == 401:
            self.auth_error = "registry 认证失败（401）"
            return None
        if resp.status_code == 404:
            raise CollectorError(f"镜像或标签不存在（404）: {url}")
        if resp.status_code != 200:
            return None
        return resp.json()

    async def _get_blob(self, client, url: str, token_header: dict) -> bytes | None:
        resp = await client.get(url, headers=token_header, follow_redirects=True)
        if resp.status_code in (403, 429):
            self.rate_limited = True
            return None
        if resp.status_code in (401, 404):
            return None
        if resp.status_code != 200:
            return None
        return resp.content

    # ---------- 主流程 ----------
    async def items(self):
        ref = parse_image_ref(self.config.get("image") or "")
        registry = ref["registry"]
        base = registry if registry.startswith("http") else (
            DOCKER_REGISTRY if registry == "docker.io" else f"https://{registry}")
        max_total = int(self.config.get("max_layer_bytes") or MAX_TOTAL_UNCOMPRESSED)
        max_member = self._max_file_bytes() * 4
        async with self._client(base) as client:
            token = await self._bearer(client, registry, ref["repo"])
            if self.auth_error:
                raise CollectorError(self.auth_error)
            auth = {"Authorization": f"Bearer {token}"} if token else {}
            reference = ref["digest"] or ref["tag"]
            manifest = await self._get_json(client, f"/v2/{ref['repo']}/manifests/{reference}",
                                            {**auth, "Accept": _ACCEPT})
            if manifest is None or self.rate_limited:
                return
            # 多架构清单：取第一个 manifest（或 amd64 优先）
            if "manifests" in manifest:
                chosen = next((m for m in manifest["manifests"]
                               if (m.get("platform") or {}).get("architecture") == "amd64"),
                              manifest["manifests"][0])
                manifest = await self._get_json(client, f"/v2/{ref['repo']}/manifests/{chosen['digest']}",
                                                {**auth, "Accept": _ACCEPT})
                if manifest is None:
                    return
            config_digest = (manifest.get("config") or {}).get("digest")
            if not config_digest:
                raise CollectorError("manifest 缺少 config digest（不支持的格式）")
            self.save_cursor("last_config_digest", config_digest)

            # 镜像配置：构建时间（low 可信）
            created = None
            cfg_blob = await self._get_blob(client, f"/v2/{ref['repo']}/blobs/{config_digest}", auth)
            if cfg_blob:
                try:
                    created = _parse_ts(json.loads(cfg_blob).get("created"))
                except (json.JSONDecodeError, ValueError):
                    created = None

            layers = manifest.get("layers") or []
            total = sum(int(l.get("size") or 0) for l in layers)
            if total > max_total:
                raise CollectorError(f"镜像层总量 {total} 超过预算 {max_total}，已中止")

            # 逐层解析，先收集（用于计算最终视图），再产出
            layer_files: list[dict] = []
            for index, layer in enumerate(layers):
                if self.rate_limited:
                    return
                digest = layer.get("digest")
                size = int(layer.get("size") or 0)
                if not digest:
                    continue
                blob = await self._get_blob(client, f"/v2/{ref['repo']}/blobs/{digest}", auth)
                if blob is None:
                    if self.rate_limited or self.auth_error:
                        return
                    continue
                try:
                    layer_files += self._iter_layer_tar(blob, digest, index, size, max_member, max_total)
                except (tarfile.TarError, OSError, EOFError) as exc:
                    self.save_cursor("layer_error", f"{digest}: {type(exc).__name__}")
                    continue

            final_view = self._final_view(layer_files)
            for entry in layer_files:
                path = entry["path"]
                if entry.get("whiteout_target"):
                    continue  # whiteout 标记本身无内容
                text = entry["text"]
                if text is None:
                    continue
                yield ContentItem(
                    kind="layer_entry", platform=f"oci:{registry}",
                    origin_url=f"{base}/v2/{ref['repo']}/blobs/{entry['layer_digest']}",
                    repo=f"{ref['repo']}:{ref['tag'] or ''}@{config_digest[:20]}",
                    path=path,
                    version_id=entry["layer_digest"], version_kind="digest",
                    text=text, size=entry["size"],
                    published_at=created, published_source="image_config_created",
                    published_confidence="low" if created else "none",
                    extra={"layer_index": entry["layer_index"],
                           "in_final_view": path in final_view,
                           "image_config_digest": config_digest},
                )

    # ---------- tar 解析与 whiteout ----------
    def _iter_layer_tar(self, blob: bytes, digest: str, index: int, compressed_size: int,
                        max_member: int, max_total: int) -> list[dict]:
        raw = blob
        try:
            raw = gzip.decompress(blob)
        except (gzip.BadGzipFile, OSError):
            raw = blob  # 未压缩层（极少数）
        if len(raw) > max_total:
            raise CollectorError("层解压后超出总量预算")
        out: list[dict] = []
        count = 0
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tf:
            for member in tf:
                count += 1
                if count > MAX_MEMBERS:
                    raise CollectorError("成员数量超出安全上限")
                if member.issym() or member.islnk() or member.isdev() or member.isdir():
                    continue
                name = member.name.replace("\\", "/").lstrip("./")
                basename = name.rsplit("/", 1)[-1]
                if basename.startswith(".wh."):
                    target = name.rsplit("/", 1)[0] + "/" if "/" in name else ""
                    if basename == ".wh..wh..opq":
                        out.append({"path": f"opaque:{target}", "whiteout_target": None,
                                    "opaque_dir": target, "text": None, "size": 0,
                                    "layer_index": index, "layer_digest": digest})
                    else:
                        target = (target + basename[4:]) if target else basename[4:]
                        out.append({"path": f"whiteout:{target}", "whiteout_target": target,
                                    "text": None, "size": 0,
                                    "layer_index": index, "layer_digest": digest})
                    continue
                if member.size > max_member or member.size == 0:
                    continue
                if not self._path_allowed(name):
                    continue
                fobj = tf.extractfile(member)
                if fobj is None:
                    continue
                data = fobj.read()
                text = self.decode_text(data)
                out.append({"path": name, "text": text, "size": member.size,
                            "layer_index": index, "layer_digest": digest})
        return out

    @staticmethod
    def _final_view(layer_files: list[dict]) -> set[str]:
        """按层序应用 whiteout/opaque，得到"当前视图可见路径"集合（历史层残留扫描的对照）。

        Docker 语义：本层 whiteout 只作用于**下层**文件；本层同层新增/替换文件仍然可见。
        """
        view: set[str] = set()
        by_layer: dict[int, list[dict]] = {}
        for entry in layer_files:
            by_layer.setdefault(entry["layer_index"], []).append(entry)
        for index in sorted(by_layer):
            entries = by_layer[index]
            for e in entries:
                p = e["path"]
                if p.startswith("whiteout:"):
                    view.discard(p[len("whiteout:"):])
                elif p.startswith("opaque:"):
                    prefix = p[len("opaque:"):]
                    view = {x for x in view if not x.startswith(prefix)}
            for e in entries:
                if e.get("text") is not None:
                    view.add(e["path"])
        return view

    def test_connection(self) -> dict:
        import httpx as _h

        try:
            ref = parse_image_ref(self.config.get("image") or "")
        except CollectorError as exc:
            return {"ok": False, "message": str(exc)}
        base = ref["registry"] if ref["registry"].startswith("http") else (
            DOCKER_REGISTRY if ref["registry"] == "docker.io" else f"https://{ref['registry']}")
        try:
            with _h.Client(base_url=base, timeout=20, follow_redirects=False) as client:
                token = None
                if ref["registry"] == "docker.io":
                    tr = _h.get(DOCKER_AUTH, params={"service": "registry.docker.io",
                                                     "scope": f"repository:{ref['repo']}:pull"}, timeout=20)
                    if tr.status_code != 200:
                        return {"ok": False, "message": f"token 获取失败（{tr.status_code}）"}
                    token = tr.json().get("token")
                headers = {"Accept": _ACCEPT, **({"Authorization": f"Bearer {token}"} if token else {})}
                resp = client.head(f"/v2/{ref['repo']}/manifests/{ref['digest'] or ref['tag']}", headers=headers)
            if resp.status_code == 200:
                return {"ok": True, "message": f"镜像可访问: {ref['repo']}:{ref['tag']}"}
            if resp.status_code in (403, 429):
                return {"ok": False, "message": f"触发限流或权限不足（{resp.status_code}）"}
            if resp.status_code == 404:
                return {"ok": False, "message": f"镜像或标签不存在（404）"}
            return {"ok": False, "message": f"意外状态码 {resp.status_code}"}
        except _h.HTTPError as exc:
            return {"ok": False, "message": f"网络错误: {exc}"}
