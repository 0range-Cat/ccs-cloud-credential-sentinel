"""采集器测试：本地目录、压缩包安全、GitHub mock（平台响应样例注入）。"""
import asyncio
import base64
import io
import random
import string
import tarfile
import zipfile

import httpx

from app.collectors.local_dir import LocalDirCollector
from app.collectors.archive import ArchiveCollector
from app.collectors.github import GitHubCollector
from app.collectors.base import CollectorError


def rand_token() -> str:
    return "ghp_" + "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(36))


def collect(collector):
    async def _run():
        return [item async for item in collector.items()]
    return asyncio.run(_run())


def test_local_dir_filters_and_binary_skip(tmp_path):
    token = rand_token()
    (tmp_path / "secret.txt").write_text(f"token: {token}", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02binary")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.txt").write_text("token: ghp_dep", encoding="utf-8")
    collector = LocalDirCollector({"path": str(tmp_path)})
    items = collect(collector)
    paths = [i.path for i in items]
    assert "secret.txt" in paths
    assert "binary.bin" not in paths
    assert all(not p.startswith("node_modules") for p in paths)
    found = [i for i in items if i.text and token in i.text]
    assert found and found[0].version_kind == "none"
    assert found[0].published_confidence == "none"


def test_local_dir_exclude_globs(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "skip.log").write_text("hello", encoding="utf-8")
    items = collect(LocalDirCollector({"path": str(tmp_path), "exclude_globs": ["*.log"]}))
    assert [i.path for i in items] == ["a.txt"]


def test_zip_traversal_and_oversize_skipped(tmp_path):
    token = rand_token()
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("src/ok.txt", f"token: {token}")
        zf.writestr("../evil.txt", "should be skipped")
        zf.writestr("abs/C:\\evil.txt", "skipped")
        zf.writestr("big.txt", "x" * (2 * 1024 * 1024))  # 超过默认 1MB 上限
    items = collect(ArchiveCollector({"path": str(zip_path)}))
    paths = [i.path for i in items]
    assert "src/ok.txt" in paths
    assert "../evil.txt" not in paths
    assert all(not p.startswith("/") and ".." not in p.split("/") for p in paths), "存在路径穿越成员"
    assert "big.txt" not in paths


def test_tar_symlink_skipped(tmp_path):
    token = rand_token()
    tar_path = tmp_path / "sample.tar"
    with tarfile.open(tar_path, "w") as tf:
        data = f"token: {token}".encode()
        info = tarfile.TarInfo("ok.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("link.txt")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tf.addfile(link)
    items = collect(ArchiveCollector({"path": str(tar_path)}))
    assert [i.path for i in items] == ["ok.txt"]


def _github_collector(responder, token=""):
    def factory(headers):
        return httpx.AsyncClient(
            base_url="https://api.github.com", headers=headers,
            transport=httpx.MockTransport(responder), timeout=5, follow_redirects=False)

    return GitHubCollector({"repo": "demo/demo"}, client_factory=factory, token=token)


def test_github_collector_happy_path():
    token = rand_token()
    blob_content = base64.b64encode(f"token: {token}".encode()).decode()

    def responder(request: httpx.Request) -> httpx.Response:
        url = request.url.path
        if url == "/repos/demo/demo":
            assert request.headers.get("authorization") is not None
            return httpx.Response(200, json={"default_branch": "main", "full_name": "demo/demo"})
        if url == "/repos/demo/demo/git/trees/main":
            return httpx.Response(200, json={"sha": "treesha", "tree": [
                {"type": "blob", "path": "config/app.env", "sha": "blob1", "size": 50},
                {"type": "blob", "path": "huge.bin", "sha": "blob2", "size": 5_000_000},
            ], "truncated": False})
        if url == "/repos/demo/demo/git/blobs/blob1":
            return httpx.Response(200, json={"encoding": "base64", "content": blob_content})
        return httpx.Response(404)

    items = collect(_github_collector(responder, token="t"))
    assert len(items) == 1
    item = items[0]
    assert item.path == "config/app.env"
    assert item.version_id == "blob1" and item.version_kind == "blob"
    assert item.origin_url == "https://github.com/demo/demo/blob/main/config/app.env"
    assert item.text and token in item.text
    assert item.published_confidence == "none", "文件级公开时间不可得，必须如实标记"


def test_github_collector_rate_limit_stops_gracefully():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/demo/demo":
            return httpx.Response(200, json={"default_branch": "main", "full_name": "demo/demo"})
        if request.url.path.endswith("trees/main"):
            return httpx.Response(200, json={"sha": "t", "tree": [
                {"type": "blob", "path": "a.txt", "sha": "b1", "size": 10} for _ in range(3)
            ]})
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={})

    c = _github_collector(responder)
    items = collect(c)
    assert items == []
    assert c.rate_limited is True, "限流应优雅停止并标记，而非报错"


def test_github_collector_auth_error():
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    c = _github_collector(responder, token="bad")
    try:
        collect(c)
        raise AssertionError("401 应触发 CollectorError")
    except CollectorError as exc:
        assert "Token" in str(exc) or "认证" in str(exc)


def test_github_repo_parse():
    from app.collectors.github import parse_repo
    assert parse_repo("https://github.com/o/r") == "o/r"
    assert parse_repo("o/r") == "o/r"
    try:
        parse_repo("justname")
        raise AssertionError
    except CollectorError:
        pass
