# 云上凭据泄露自动化检测与响应系统（CCS）

面向网络安全创新大赛赛题"云上凭据泄露的自动化检测"的单机可持续运行平台：
对公开渠道（代码托管、Wiki、微博、知识分享、容器镜像、App、小程序产物及本地导入）
进行凭据泄露采集与检测，支持候选复核、可选的最小化在线验证、脱敏展示与导出。

> 合规边界：本系统只做"公开泄露的发现 + 记录 + 最小化有效性验证"，不利用凭据执行任何业务操作。
> 在线验证默认关闭，且仅使用官方文档明确的最小认证接口。

## 核心特性

- 插件化渠道采集器（Collector）与验证器（Verifier），新增渠道只需实现一个 Python 类。
- 自研检测引擎：规则注册表（YAML）+ 上下文/熵/占位符过滤 + AK/SK 配对，检测阶段禁用任何第三方在线验证。
- 凭据实体与出现位置分离建模，支持同凭据多位置关联、重复扫描不产生重复事件。
- 完整时间模型：source_published_at / fetched_at / detected_at / first_seen_at / last_seen_at 分开记录，公开时间未知时显示"未知"。
- 验证模块独立且默认关闭；单条 / 批量 / 可选自动验证；严格最小认证语义（不枚举资源、不读业务数据）。
- 中文 Web 界面：总览 / 监控任务 / 发现 / 验证中心 / 渠道与规则 / 设置；默认脱敏，导出可选脱敏。

## 快速启动（Windows / macOS / Linux 通用）

后端（Python 3.11+）：

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                 # Windows（可选，默认零配置可跑）
# cp .env.example .env                 # Linux/macOS
alembic upgrade head                   # 也可跳过：应用启动时自动执行迁移
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端（Node 18+，首次）：

```bash
cd frontend
npm install
npm run build        # 产物输出到 frontend/dist，由后端自动托管
```

打开 http://127.0.0.1:8000 即为中文管理界面；API 文档在 http://127.0.0.1:8000/docs。

数据默认存储在 `data/app.db`（SQLite，WAL 模式）；主密钥首次启动自动生成于 `data/master.key`，
用于加密存储凭据原文与平台 Token——备份 `data/` 时必须连同主密钥一起备份，详见 `docs/DEPLOYMENT.md`。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [docs/INDEX.md](docs/INDEX.md) | 全部文档索引与目录结构 |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | 需求、评价指标、范围、验收映射 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构、数据流、模块边界、技术决策 |
| [docs/INTERFACES.md](docs/INTERFACES.md) | 实体、插件契约、API、状态模型 |
| [docs/SUPPORTED_CHANNELS.md](docs/SUPPORTED_CHANNELS.md) | 渠道能力矩阵（实现/测试状态） |
| [docs/SUPPORTED_CREDENTIALS.md](docs/SUPPORTED_CREDENTIALS.md) | 凭据类型检测与验证能力矩阵 |
| [docs/RESEARCH.md](docs/RESEARCH.md) | 开源工具与平台接口调研 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 测试方法、结果与证据 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Windows / Ubuntu / Docker 部署与备份 |
| [docs/DEMO.md](docs/DEMO.md) | GitHub 演示指南（用户可操作） |
| [docs/TODO.md](docs/TODO.md) | 阶段任务、状态与验收方法 |
| [docs/DEVLOG.md](docs/DEVLOG.md) | 开发记录与真实执行结果 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 跨会话交接 |
| [AGENTS.md](AGENTS.md) | 本项目开发规则与约定 |

## 目录结构

```
backend/          FastAPI 后端（app/ 源码, tests/ 测试, alembic/ 迁移, detection/rules/ 规则）
frontend/         Vue 3 + TypeScript + Element Plus 中文界面
docs/             设计、调研、部署、评估、交接文档
examples/         合成测试样例（无法认证的假凭据，仅用于演示与测试）
scripts/          启动与辅助脚本
```
