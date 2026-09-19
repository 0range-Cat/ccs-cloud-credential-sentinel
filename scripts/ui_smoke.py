"""关键界面流程浏览器自动化冒烟（阶段5，Playwright + Chromium）。

覆盖流程：启动服务 → 总览渲染 → 发现列表（默认脱敏断言）→ 详情抽屉（位置/上下文脱敏）
→ 渠道与规则（能力矩阵）→ 设置页加载。证据截图存 docs/evidence/。

运行：cd backend && .venv/Scripts/python ../scripts/ui_smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="ccs-ui-"))
os.environ["CCS_DATA_DIR"] = str(TMP)
os.environ["CCS_DB_URL"] = f"sqlite:///{(TMP / 'ui.db').as_posix()}"
os.environ["CCS_BACKGROUND"] = "false"
sys.path.insert(0, str(ROOT / "backend"))

PORT = 8222
SAMPLE_TOKEN = "ghp_4a9Ck2XwQqLmN8vBzR5tYuIoP1sDfGhJkL2b"  # 合成假值

# ---- 准备数据（复用与用户真实操作相同的 API/流水线） ----
from app.db import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.models import Source, Task  # noqa: E402
from app import pipeline, services  # noqa: E402
from app.detection.registry import get_registry  # noqa: E402

Base.metadata.create_all(engine)
s = SessionLocal()
services.sync_rule_records(s, get_registry())
services.seed_capabilities(s)
src = Source(name="UI冒烟-样例仓库", category="local_import", platform="local",
             collector_key="local_dir",
             config_json={"path": str((ROOT / "backend" / "tests" / "fixtures" / "sample_repo").resolve())},
             enabled=True)
s.add(src)
s.flush()
s.add(Task(source_id=src.id, mode="manual", interval_sec=300, status="pending"))
s.commit()
pipeline.run_task(src.tasks[0].id, "manual")
s.close()

# ---- 启动服务（子进程，真实 uvicorn） ----
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=str(ROOT / "backend"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    env={**os.environ})
try:
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/system/info", timeout=2)
            break
        except Exception:
            time.sleep(1)

    # ---- Playwright 浏览器流程 ----
    from playwright.sync_api import sync_playwright

    evidence_dir = ROOT / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 1. 总览
        page.goto(f"http://127.0.0.1:{PORT}/#/")
        page.wait_for_selector(".stat-num", timeout=10000)
        results.append(("总览渲染（统计卡片）", "PASS"))
        page.screenshot(path=str(evidence_dir / "ui_overview.png"))

        # 2. 发现列表：默认脱敏
        page.goto(f"http://127.0.0.1:{PORT}/#/findings")
        page.wait_for_selector(".el-table__row", timeout=10000)
        body = page.inner_text("body")
        assert SAMPLE_TOKEN not in page.content(), "界面出现凭据原文——脱敏失败"
        results.append(("发现列表渲染且默认脱敏（原文零出现）", "PASS"))
        rows = page.locator(".el-table__row").count()
        results.append((f"发现列表行数 = {rows}", "PASS" if rows >= 10 else "FAIL"))
        page.screenshot(path=str(evidence_dir / "ui_findings.png"))

        # 3. 详情抽屉
        page.locator(".el-table__row").first.click()
        page.wait_for_selector(".el-drawer", timeout=10000)
        drawer = page.inner_text(".el-drawer")
        assert "出现位置" in drawer and "复核与审计" in drawer
        results.append(("详情抽屉（位置/验证历史/复核记录）", "PASS"))
        page.screenshot(path=str(evidence_dir / "ui_detail.png"))
        page.keyboard.press("Escape")

        # 4. 渠道与规则
        page.goto(f"http://127.0.0.1:{PORT}/#/channels")
        page.wait_for_selector(".el-table__row", timeout=10000)
        chan_body = page.inner_text("body")
        assert "live_verified" in chan_body and "blocked" in chan_body
        results.append(("渠道能力矩阵（live_verified/blocked 状态可见）", "PASS"))

        # 5. 设置页
        page.goto(f"http://127.0.0.1:{PORT}/#/settings")
        page.wait_for_selector("text=平台采集账号", timeout=10000)
        results.append(("设置页加载（采集账号/验证策略表单）", "PASS"))
        page.screenshot(path=str(evidence_dir / "ui_settings.png"))

        # 6. 验证中心
        page.goto(f"http://127.0.0.1:{PORT}/#/verification")
        page.wait_for_selector("text=验证器", timeout=10000)
        assert "GET /user" in page.inner_text("body")
        results.append(("验证中心（验证器清单）", "PASS"))

        browser.close()

    print("\n=== UI SMOKE RESULTS ===")
    ok = True
    for name, st in results:
        print(f"[{st}] {name}")
        ok = ok and st == "PASS"
    print("UI_SMOKE_" + ("OK" if ok else "FAILED"))
finally:
    server.terminate()
