"""受控"泄露→发现时延"实验（评价维度 4/5，可复现）。

方法：
1. 把 examples/demo_repo 的合成样例（全部为假值，无法认证）推送到用户公开仓库的
   ccs-demo-lab/ 目录，记录每个文件 PUT 成功时刻为公开时间 T0（我们对发布时刻有第一手证据）。
2. 系统扫描该仓库 → 检出候选（评价 4：发现数量与去重口径）。
3. 三批追加新文件（每批一个唯一合成 Token），T0=推送完成时刻，随后以固定间隔轮询扫描，
   检出时刻 T1 → 时延 = T1 - T0（评价 5）。平台索引延迟=0（直接读仓库树，不依赖搜索索引）。
4. 幂等验证：重复扫描不得新增唯一凭据/位置。

安全：GitHub Token 从 data/github.token（gitignored）读取；本脚本不含任何密钥。
产出：stdout JSON 摘要 + data/latency_log.json（gitignored）。
"""
from __future__ import annotations

import base64
import json
import random
import string
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import os  # noqa: E402

os.environ["CCS_DATA_DIR"] = str(ROOT / "data")
os.environ["CCS_DB_URL"] = f"sqlite:///{(ROOT / 'data' / 'app.db').as_posix()}"
os.environ["CCS_BACKGROUND"] = "false"

import httpx  # noqa: E402

from app.db import Base, SessionLocal, engine, utcnow  # noqa: E402
import app.models  # noqa: E402,F401
from app.models import Credential, Occurrence, Source, Task  # noqa: E402
from app import pipeline, services, settings_service  # noqa: E402
from app.detection.registry import get_registry  # noqa: E402
from app.security import credential_fingerprint  # noqa: E402

REPO = "0range-Cat/0range-Cat.github.io"
PREFIX = "ccs-demo-lab"
POLL_INTERVAL = 8


def gh_headers() -> dict:
    token = (ROOT / "data" / "github.token").read_text().strip()
    return {"Authorization": f"Bearer {token}", "User-Agent": "ccs-collector/0.1",
            "Accept": "application/vnd.github+json"}


def put_file(client: httpx.Client, path: str, content: bytes, message: str) -> tuple[str, bool]:
    """推送文件；返回 (公开时刻T0, 是否本次新推送)。

    GitHub push protection 会拦截"疑似真实凭据格式"的合成样例（如 Twilio SID 无校验位），
    官方流程：响应给出 placeholder_id → 申请 bypass（reason=used_in_tests）→ 重推。
    已存在的文件（422）视为早已公开，跳过。
    """
    base = f"https://api.github.com/repos/{REPO}/contents/{PREFIX}/{path}"
    existing = client.get(base, headers=gh_headers(), timeout=30)
    if existing.status_code == 200:
        return datetime.now(timezone.utc).isoformat(), False
    bypassed: set[str] = set()
    for attempt in range(6):
        r = client.put(base, headers=gh_headers(), timeout=30,
                       json={"message": message,
                             "content": base64.b64encode(content).decode()})
        if r.status_code in (200, 201):
            return datetime.now(timezone.utc).isoformat(), True
        if r.status_code == 409:  # 同分支竞态 或 push protection 拦截
            meta = ((r.json() or {}).get("metadata") or {}).get("secret_scanning") or {}
            for ph in meta.get("bypass_placeholders", []):
                pid = ph.get("placeholder_id")
                if pid and pid not in bypassed:
                    bypassed.add(pid)
                    client.post(f"https://api.github.com/repos/{REPO}/secret-scanning/push-protection-bypasses",
                                headers=gh_headers(), timeout=30,
                                json={"placeholder_id": pid, "reason": "used_in_tests"})
            time.sleep(2 + attempt)
            continue
        if r.status_code == 422:  # 已存在（无 sha 更新）→ 跳过
            return datetime.now(timezone.utc).isoformat(), False
        if r.status_code in (502, 503):
            time.sleep(2 + attempt * 2)
            continue
        r.raise_for_status()
    raise RuntimeError(f"推送失败（重试耗尽）: {path}")


def rand_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "ghp_" + "".join(random.SystemRandom().choice(alphabet) for _ in range(36))


def main() -> None:
    Base.metadata.create_all(engine)
    session = SessionLocal()
    services.sync_rule_records(session, get_registry())
    services.seed_capabilities(session)
    src = session.query(Source).filter(Source.name == "GitHub实采-用户站点仓库").first()
    if src is None:
        src = Source(name="GitHub实采-用户站点仓库", category="code_hosting", platform="github",
                     collector_key="github", config_json={"repo": REPO}, enabled=True)
        session.add(src)
        session.flush()
        session.add(Task(source_id=src.id, mode="manual", interval_sec=300, status="pending"))
        session.commit()

    report: dict = {"repo": REPO, "prefix": PREFIX}

    # ---- 阶段1：基线样例推送与发现 ----
    client = httpx.Client()
    baseline = []
    for f in sorted((ROOT / "examples" / "demo_repo").rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(ROOT / "examples" / "demo_repo").as_posix()
        t0, pushed = put_file(client, rel, f.read_bytes(),
                              f"chore(ccs-demo-lab): 合成样例 {rel}（假值，无法认证）")
        baseline.append({"file": rel, "published_at": t0, "pushed_now": pushed})
        time.sleep(1.2)
    report["baseline_files"] = baseline

    stats1 = pipeline.run_task(src.tasks[0].id, "manual")
    report["baseline_scan"] = {k: stats1.get(k) for k in
                               ("items_seen", "candidates", "new_credentials",
                                "new_occurrences", "stop_reason", "error")}
    stats_repeat = pipeline.run_task(src.tasks[0].id, "manual")
    report["idempotency"] = {"new_credentials": stats_repeat.get("new_credentials"),
                             "new_occurrences": stats_repeat.get("new_occurrences"),
                             "items_skipped": stats_repeat.get("items_skipped")}
    creds = session.query(Credential).count()
    occs = session.query(Occurrence).count()
    report["totals_after_baseline"] = {"credentials": creds, "occurrences": occs}

    # ---- 阶段2：受控时延实验（3 批） ----
    latencies = []
    run_tag = str(int(time.time()))
    for batch in range(1, 4):
        token = rand_token()
        fname = f"latency-b{batch}-{run_tag}.env"
        t0iso, _pushed = put_file(client, fname,
                                  (f"# synthetic latency sample {batch} (FAKE, cannot authenticate)\n"
                                   f"GITHUB_TOKEN={token}\n").encode(),
                                  f"chore(ccs-demo-lab): 时延实验批次 {batch}（合成假值）")
        t0 = datetime.fromisoformat(t0iso).replace(tzinfo=None)  # 与库内 naive UTC 对齐
        fp = credential_fingerprint("github_pat", token)
        polls = 0
        detected_at = None
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL)
            polls += 1
            pipeline.run_task(src.tasks[0].id, "manual")
            session.expire_all()
            cred = session.query(Credential).filter(Credential.fingerprint == fp).first()
            if cred is not None:
                detected_at = utcnow()
                break
        if detected_at is None:
            latencies.append({"batch": batch, "published_at": t0iso,
                              "detected_at": None, "latency_seconds": None, "polls": polls,
                              "note": "超时未检出"})
            continue
        latency = (detected_at - t0).total_seconds()
        latencies.append({"batch": batch, "published_at": t0iso,
                          "detected_at": detected_at.isoformat() + "Z",
                          "latency_seconds": latency, "polls": polls,
                          "fingerprint_prefix": fp[:12]})
        print(f"batch {batch}: T0={t0iso} T1={detected_at.isoformat()}Z "
              f"latency={latency:.1f}s polls={polls}", flush=True)

    report["latency_samples"] = latencies
    values = sorted(l["latency_seconds"] for l in latencies if l["latency_seconds"] is not None)
    if values:
        report["latency_summary"] = {
            "n": len(values),
            "p50_seconds": values[len(values) // 2],
            "p95_seconds": values[-1],  # 样本量小，P95 以最大值近似并如实注明
            "note": f"轮询间隔 {POLL_INTERVAL}s；时延含轮询等待+采集+检测+入库；样本量小，P95 用最大值近似",
        }

    (ROOT / "data" / "latency_log.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    session.close()


if __name__ == "__main__":
    main()
