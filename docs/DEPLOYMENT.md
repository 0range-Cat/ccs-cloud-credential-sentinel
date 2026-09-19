# 部署说明（DEPLOYMENT）

## 1. Windows 11（开发/单机，已实测）

前置：Python 3.11+（实测 3.13.9）、Node 18+（实测 24，仅构建前端需要）。

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      &:: 可选
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端构建一次（产物由后端自动托管）：

```bat
cd frontend
npm install
npm run build
```

访问 http://127.0.0.1:8000（中文界面）；API 文档 /docs。
实测记录（2026-09-19）：uvicorn 启动 → /api/system/info 返回 35 规则/3 采集器/1 验证器；
导入样例目录 → 16 凭据/17 位置；重复扫描幂等；前端页面正常打开。

## 2. Ubuntu（云服务器，未实测——需用户服务器执行，步骤如下）

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nodejs npm
git clone <本仓库> ccs && cd ccs/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
# 前端（构建机可分离）
cd ../frontend && npm ci && npm run build && cd ../backend
# 启动（systemd 示例）
sudo tee /etc/systemd/system/ccs.service <<'EOF'
[Unit]
Description=Cloud Credential Sentinel
After=network.target
[Service]
WorkingDirectory=/opt/ccs/backend
ExecStart=/opt/ccs/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Environment=CCS_ACCESS_TOKEN=改成强口令
Restart=on-failure
User=www-data
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now ccs
```

远程访问安全（二选一）：
1. Nginx 反向代理 + Basic Auth / TLS，仅暴露 443；
2. `CCS_ACCESS_TOKEN` 环境变量启用系统内置单用户令牌（登录接口 POST /api/login）。
不要把 8000 端口直接暴露公网（无 TLS 且界面未做登录限速）。

## 3. Docker Compose（未实测——Docker 29 已装，镜像构建在阶段5 验证）

```yaml
# docker-compose.yml（阶段5 提交正式版本）
services:
  app:
    build:
      context: .
      dockerfile: backend/Dockerfile   # 两阶段：node 构建前端 → python 运行
    ports: ["127.0.0.1:8000:8000"]
    volumes:
      - ./data:/app/data               # 数据库 + 主密钥（必须持久化）
    environment:
      - CCS_ACCESS_TOKEN=${CCS_ACCESS_TOKEN:-}
```

## 4. 数据与密钥（重要）

| 路径 | 内容 | 备份要求 |
| --- | --- | --- |
| `data/app.db`（或 -wal/-shm） | 业务数据库（SQLite WAL） | 常规备份 |
| `data/master.key` | 主密钥（Fernet 派生源） | **必须与数据库同时备份**，丢失=凭据密文不可恢复 |
| `data/tmp/` | 上传压缩包临时区 | 无需备份，可清理 |
| `logs/` | 运行日志（无凭据原文） | 按需 |

- 主密钥优先取环境变量 `CCS_MASTER_KEY`，其次 `data/master.key`（首次启动自动生成）。
- 迁移到 PostgreSQL：设置 `CCS_DB_URL=postgresql+psycopg://...` 后 `alembic upgrade head`；
  数据搬迁用导出/导入（阶段5 提供脚本）。主密钥不变则历史密文仍可解密。
- 升级：`git pull` → `pip install -r requirements.txt` → `alembic upgrade head` → 重启。

## 5. 已知部署限制

- SQLite 轻量模式适合单机单人；高并发建议 PostgreSQL（阶段5 实测）。
- Windows 控制台用 curl 传中文 JSON 会有编码问题，属终端限制，界面/API 客户端无此问题。
- 浏览器自动化测试未安装（TODO T5.4），界面目前以人工走查为准。
