"""阶段3 测试：OCI 容器镜像层解析（whiteout/最终视图）与 APK 静态扫描。"""
import asyncio
import base64
import gzip
import io
import json
import random
import string
import tarfile
import zipfile

import httpx

from app.collectors.oci_registry import OCIRegistryCollector, parse_image_ref
from app.collectors.apk import ApkCollector
from app.collectors.base import CollectorError


def collect(collector):
    async def _run():
        return [item async for item in collector.items()]
    return asyncio.run(_run())


def rand_alnum(n):
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def _make_layer(files: dict[str, bytes], whiteouts: list[str] | None = None,
                opaque: str | None = None) -> bytes:
    """构造一个 gzip 压缩的 docker 层 tar。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for wo in whiteouts or []:
            parent = wo.rsplit("/", 1)[0] + "/" if "/" in wo else ""
            info = tarfile.TarInfo(f"{parent}.wh.{wo.rsplit('/', 1)[-1]}")
            info.size = 0
            tf.addfile(info, io.BytesIO(b""))
        if opaque:
            info = tarfile.TarInfo(f"{opaque}/.wh..wh..opq")
            info.size = 0
            tf.addfile(info, io.BytesIO(b""))
    return gzip.compress(buf.getvalue())


DIGEST = lambda data: "sha256:" + __import__("hashlib").sha256(data).hexdigest()  # noqa: E731


def _mock_registry(layers: list[bytes], created="2026-01-01T00:00:00Z"):
    config = {"created": created, "architecture": "amd64"}
    config_blob = json.dumps(config).encode()
    layer_blobs = [gzip.compress(l) if not l.startswith(b"\x1f\x8b") else l for l in layers]

    def digest_of(b):
        return DIGEST(b)

    manifest = {
        "schemaVersion": 2,
        "config": {"digest": digest_of(config_blob), "size": len(config_blob)},
        "layers": [{"digest": digest_of(b), "size": len(b)} for b in layer_blobs],
    }
    blobs = {digest_of(config_blob): config_blob}
    blobs.update({digest_of(b): b for b in layer_blobs})

    def responder(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v2/library/alpine/manifests/latest" or path.endswith("/manifests/latest"):
            return httpx.Response(200, json=manifest, headers={"Content-Type": _ACCEPT_HDR()})
        if path.startswith("/v2/") and "/blobs/" in path:
            d = path.rsplit("/", 1)[-1]
            if d in blobs:
                return httpx.Response(200, content=blobs[d])
            return httpx.Response(404)
        return httpx.Response(401)

    return responder, manifest, digest_of(config_blob)


def _ACCEPT_HDR():
    return "application/vnd.docker.distribution.manifest.v2+json"


def _oci(responder):
    def factory(base_url, headers):
        return httpx.AsyncClient(base_url=base_url, headers=headers,
                                 transport=httpx.MockTransport(_auth_then(responder)),
                                 timeout=10, follow_redirects=False)
    return OCIRegistryCollector({"image": "alpine:latest", "max_layer_bytes": 64 * 1024 * 1024},
                                client_factory=factory)


def _auth_then(responder):
    """Docker Hub 匿名流程：auth.docker.io 发 token，registry 走 Bearer。"""
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith("https://auth.docker.io"):
            return httpx.Response(200, json={"token": "test-token"})
        return responder(request)
    return handler


def test_oci_layer_scan_whiteout_and_final_view():
    secret1 = f"aws_secret_access_key = k7Rq2Xm9ZvBs4YwLd8Hn3Jp6TfG1QeAu5Ci0OxVy"
    l1 = _make_layer({"app/config.env": secret1.encode(),
                      "app/old.txt": b"old content here"})
    l2 = _make_layer({"app/old.txt": b"replaced content"}, whiteouts=["app/old.txt"])

    responder, _, config_digest = _mock_registry([l1, l2])
    cursors: dict = {}
    c = _oci(responder)
    items = collect(c)

    paths = {i.path for i in items}
    assert "app/config.env" in paths and "app/old.txt" in paths
    for item in items:
        assert item.version_kind == "digest"
        assert item.extra["image_config_digest"] == config_digest
        assert item.published_confidence == "low", "构建时间只能作低可信"
        if item.path == "app/old.txt":
            assert item.extra["in_final_view"] is True, "第二层替换后仍在最终视图"
    assert not any(i.path.startswith("whiteout:") for i in items), "whiteout 标记本身不产出内容项"
    assert c.cursors.get("last_config_digest") == config_digest

    # 最终视图语义单测：whiteout 删除 + opaque 清空
    l3 = _make_layer({"app/new.txt": b"x"}, whiteouts=["app/config.env"])
    entries = c._iter_layer_tar(l3, "sha256:fake", 2, 10, 1024 * 1024, 512 * 1024 * 1024)
    assert any(e["path"] == "whiteout:app/config.env" for e in entries)
    opaque_entries = c._iter_layer_tar(_make_layer({"d/b.txt": b"b"}, opaque="d"), "sha256:f2", 3, 10, 1024 * 1024, 512 * 1024 * 1024)
    assert any(e["path"] == "opaque:d/" for e in opaque_entries)


def test_oci_parse_ref():
    assert parse_image_ref("alpine")["repo"] == "library/alpine"
    assert parse_image_ref("alpine")["tag"] == "latest"
    assert parse_image_ref("myorg/app:1.2")["repo"] == "myorg/app"
    assert parse_image_ref("ghcr.io/owner/img@sha256:" + "a" * 64)["registry"] == "ghcr.io"
    try:
        parse_image_ref("")
        raise AssertionError
    except CollectorError:
        pass


# ---------------- APK ----------------

def _make_apk(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_apk_scan_assets_and_dex_strings():
    token = "ghp_" + rand_alnum(36)
    manifest = b"\x03\x00binary-xml-not-parsed"  # 无 Androguard 时如实跳过
    dex = b"\x64\x65\x78\x0a" + b"\x00" * 20 + f"GITHUB_TOKEN={token}".encode() + b"\x00\x00"
    apk = _make_apk({
        "AndroidManifest.xml": manifest,
        "assets/config.env": f"API_KEY=J8kQ2wL5vB8nM4cR6tZ0aS3dF7yG1x".encode(),
        "res/layout.bin": b"\x00\x01\x02",          # 二进制资源应跳过
        "classes.dex": dex,
    })
    c = ApkCollector({"path": "demo.apk"})  # path 仅用于名称；数据由 monkeypatch 注入
    items = _scan_bytes(c, apk)
    kinds = {i.kind for i in items}
    assert kinds == {"apk_entry", "apk_dex_strings"}
    paths = {i.path for i in items}
    assert "assets/config.env" in paths
    assert "classes.dex#strings" in paths
    assert "res/layout.bin" not in paths
    assert "AndroidManifest.xml" not in paths, "二进制 manifest 未解析时不得假装扫描"
    dex_item = next(i for i in items if i.kind == "apk_dex_strings")
    assert token in dex_item.text
    assert dex_item.extra.get("apk_sha256")
    # 引擎能在 dex 字符串中检出凭据
    from app.detection.engine import DetectionEngine
    from app.detection.registry import get_registry
    engine = DetectionEngine(get_registry())
    hits = [x for x in engine.scan(dex_item.text, path="classes.dex#strings")
            if not x.evidence.get("rejected_candidate") and x.rule_id == "github-pat"]
    assert hits, "dex 字符串中应检出 GitHub PAT"


def _scan_bytes(collector, apk_bytes, tmp="demo.apk"):
    """通过临时文件注入 APK 数据（collector 从 path 读取）。"""
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as f:
        f.write(apk_bytes)
        p = f.name
    try:
        collector.config["path"] = p
        return collect(collector)
    finally:
        Path(p).unlink(missing_ok=True)


def test_apk_rejects_non_zip():
    c = ApkCollector({})
    try:
        _scan_bytes(c, b"not a zip at all")
        raise AssertionError
    except CollectorError:
        pass
