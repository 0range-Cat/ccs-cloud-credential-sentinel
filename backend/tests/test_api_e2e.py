"""端到端 API 测试：设置→建任务→采集→检测→入库→查询→复核→验证→脱敏→导出→导入。"""
import io
import random
import string
import zipfile

from app import scheduler
from app.db import SessionLocal
from app.models import ScanRun, Task, VerificationJob
from app.verification import worker

SAMPLE_TOKEN = "ghp_4a9Ck2XwQqLmN8vBzR5tYuIoP1sDfGhJkL2b"  # 合成假值（与 fixtures 一致）


def rand_alnum(n):
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def test_full_flow(client, sample_repo_path, tmp_path):
    # 1. 设置：平台 Token 加密存储，响应必须脱敏
    resp = client.put("/api/settings", json={"values": {"platform.github.token": "ccs_demo_token_123"}})
    assert resp.status_code == 200
    data = client.get("/api/settings").json()
    assert data["platform.github.token"]["configured"] is True
    assert "ccs_demo_token_123" not in resp.text and "ccs_demo_token_123" not in str(data)

    # 2. 连接测试（本地目录，不使用发现凭据）
    resp = client.post("/api/settings/test-connection",
                       json={"target": "local_dir", "config": {"path": sample_repo_path}})
    assert resp.status_code == 200 and resp.json()["ok"] is True

    # 3. 创建来源并手动运行
    resp = client.post("/api/sources", json={
        "name": "样例仓库扫描", "collector_key": "local_dir",
        "config": {"path": sample_repo_path}, "mode": "manual",
    })
    assert resp.status_code == 200
    source = resp.json()
    assert source["task"]["status"] == "pending"
    resp = client.post(f"/api/sources/{source['id']}/run")
    assert resp.status_code == 200

    # 4. 发现列表：默认脱敏，不得出现原文
    resp = client.get("/api/findings")
    assert resp.status_code == 200
    findings = resp.json()
    assert findings["total"] > 0
    assert SAMPLE_TOKEN not in resp.text, "列表响应必须脱敏"
    assert all(item["preview"].endswith("****") or "****" in item["preview"] for item in findings["items"])

    # 5. 详情：多位置 + 上下文脱敏 + 时间字段
    cred_id = findings["items"][0]["id"]
    resp = client.get(f"/api/findings/{cred_id}")
    detail = resp.json()
    assert detail["occurrence_count"] >= 1
    assert SAMPLE_TOKEN not in resp.text
    for loc in detail["locations"]:
        assert "detected_at" in loc and "first_seen_at" in loc

    # 6. 同一凭据（GitHub PAT 样例）应有两个位置（.env 与 config.yaml）
    ghp = [i for i in findings["items"] if i["type"] == "github_pat" and i["preview"].startswith("ghp_4a9")]
    if ghp:
        d = client.get(f"/api/findings/{ghp[0]['id']}").json()
        assert d["occurrence_count"] == 2, "样例中同一 PAT 出现在两个文件"

    # 7. reveal 需显式请求并写审计
    resp = client.post(f"/api/findings/{cred_id}/reveal")
    assert resp.status_code == 200 and resp.json()["secret"]
    d = client.get(f"/api/findings/{cred_id}").json()
    assert any(l["action"] == "reveal_access" for l in d["review_logs"])

    # 8. 复核流转
    resp = client.post(f"/api/findings/{cred_id}/review", json={"action": "confirm", "note": "确认"})
    assert resp.json()["review_status"] == "confirmed"
    resp = client.post(f"/api/findings/{cred_id}/review", json={"action": "restore"})
    assert resp.json()["review_status"] == "pending"

    # 9. 批量复核
    ids = [i["id"] for i in findings["items"][:2]]
    resp = client.post("/api/findings/batch-review", json={"ids": ids, "action": "false_positive"})
    assert resp.json()["ok"] == 2

    # 10. 导出：默认脱敏；显式不脱敏才有原文；CSV 防公式注入
    csv_masked = client.get("/api/export/findings.csv").text
    assert SAMPLE_TOKEN not in csv_masked
    csv_raw = client.get("/api/export/findings.csv?masked=false").text
    assert SAMPLE_TOKEN in csv_raw
    json_export = client.get("/api/export/findings.json?masked=false")
    assert SAMPLE_TOKEN in json_export.text
    from app.services import csv_escape_cell
    assert csv_escape_cell("=cmd()").startswith("'=")
    assert csv_escape_cell("+1").startswith("'+")

    # 11. 验证：默认关闭（扫描后无队列任务）；手动提交走队列
    assert client.get("/api/verification/jobs?status=queued").json() == []
    ghp_any = next((i for i in findings["items"] if i["type"] == "github_pat"), None)
    resp = client.post(f"/api/findings/{ghp_any['id']}/verify")
    assert resp.json()["queued"] is True
    queued = client.get("/api/verification/jobs?status=queued").json()
    assert len(queued) == 1

    # 用 mock 传输层处理队列任务（不访问真实 GitHub）
    def handler(request):
        return __import__("httpx").Response(200, json={})
    session = SessionLocal()
    try:
        job = session.query(VerificationJob).filter(VerificationJob.status == "queued").first()
        worker._process_job(session, job, http_factory_override=(
            lambda: __import__("httpx").AsyncClient(
                transport=__import__("httpx").MockTransport(handler), follow_redirects=False)))
    finally:
        session.close()
    history = client.get(f"/api/verification/history?credential_id={ghp_any['id']}").json()
    assert history and history[0]["status"] == "valid"

    # 无验证器类型 → unsupported，保留检测能力
    aws = next((i for i in findings["items"] if i["type"] == "aws_access_key_id"), None)
    if aws:
        resp = client.post(f"/api/findings/{aws['id']}/verify")
        assert resp.json()["status"] == "unsupported"

    # 12. 总览统计与口径
    stats = client.get("/api/overview/stats").json()
    assert stats["credentials_total"] >= findings["total"]
    assert "note" in stats["detection_latency"], "时延口径必须说明样本依据"

    # 13. 渠道与规则
    channels = client.get("/api/channels").json()
    caps = {c["key"]: c["status"] for c in channels["capabilities"]}
    assert caps["code_hosting.github"] == "live_verified"
    assert caps["microblog.weibo"] == "blocked"
    rules = client.get("/api/rules").json()
    assert len(rules) >= 30
    rid = rules[0]["id"]
    client.patch(f"/api/rules/{rid}", json={"enabled": False})
    assert client.get("/api/rules").json()[0]["enabled"] is False
    client.patch(f"/api/rules/{rid}", json={"enabled": True})

    # 14. 压缩包导入 → 扫描 → 新发现
    zip_token = "ghp_" + rand_alnum(36)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("leaked.env", f"TOKEN={zip_token}")
    buf.seek(0)
    resp = client.post("/api/import/archive",
                       files={"upload": ("demo.zip", buf, "application/zip")})
    assert resp.status_code == 200 and resp.json()["triggered"] is True
    task_id = resp.json()["task_id"]
    runs = client.get(f"/api/tasks/{task_id}/runs").json()
    assert runs and runs[0]["stats"]["new_credentials"] >= 1

    # 15. 暂停/恢复/重试任务
    resp = client.post("/api/sources", json={
        "name": "持续任务", "collector_key": "local_dir",
        "config": {"path": sample_repo_path}, "mode": "continuous", "interval_sec": 3600,
    })
    task_id2 = resp.json()["task"]["id"]
    assert client.post(f"/api/tasks/{task_id2}/pause").json()["status"] == "paused"
    assert client.post(f"/api/tasks/{task_id2}/resume").json()["status"] == "pending"
    assert client.post(f"/api/tasks/{task_id2}/pause").json()["status"] == "paused"


def test_api_requires_valid_collector(client):
    resp = client.post("/api/sources", json={"name": "x", "collector_key": "nope", "config": {}})
    assert resp.status_code == 400
