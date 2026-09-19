# 文档索引

| 文档 | 用途 | 状态 |
| --- | --- | --- |
| [../README.md](../README.md) | 项目简介、快速启动 | 持续维护 |
| [../AGENTS.md](../AGENTS.md) | 开发规则与约定 | 持续维护 |
| [MASTER_PROMPT.md](MASTER_PROMPT.md) | 任务完整约束存档 | 已固化 |
| [DELIVERABLES.md](DELIVERABLES.md) | 四项交付件与评价维度→真实数字对照 | 答辩口径单一来源 |
| [REQUIREMENTS.md](REQUIREMENTS.md) | 需求、评价指标、范围、验收映射 | 已确认 |
| [RESEARCH.md](RESEARCH.md) | 开源工具与平台接口调研（含日期与链接） | 持续更新 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构、数据流、模块边界、技术决策 | 阶段0基线 |
| [INTERFACES.md](INTERFACES.md) | 实体、插件契约、API、状态模型 | 阶段0基线 |
| [TODO.md](TODO.md) | 阶段任务、状态、验收方法 | 每任务更新 |
| [DEVLOG.md](DEVLOG.md) | 开发记录与真实执行结果 | 每任务更新 |
| [HANDOFF.md](HANDOFF.md) | 跨会话交接 | 每会话结束更新 |
| [SUPPORTED_CHANNELS.md](SUPPORTED_CHANNELS.md) | 渠道能力矩阵 | 随实现更新 |
| [SUPPORTED_CREDENTIALS.md](SUPPORTED_CREDENTIALS.md) | 凭据类型能力矩阵 | 随实现更新 |
| [EVALUATION.md](EVALUATION.md) | 测试方法、结果、证据 | 随测试更新 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Windows/Ubuntu/Docker 部署、备份恢复 | 随实现更新 |
| [DEMO.md](DEMO.md) | GitHub 演示指南 | 阶段1提供 |
| [TECHNICAL_MANUAL.md](TECHNICAL_MANUAL.md) | 技术说明书（原理/模块/实现说明） | 随实现完善 |
| research/ | 子智能体调研草稿（draft-tools.md, draft-platforms.md） | 阶段0 |

## 目录结构说明

```
backend/
  app/
    main.py            FastAPI 应用工厂、启动恢复、静态托管
    config.py          配置（环境变量 CCS_*，pydantic-settings）
    db.py              SQLAlchemy 引擎/会话、SQLite WAL、UTC 基础设施
    models.py          全部 ORM 实体
    schemas.py         Pydantic 请求/响应模型（含脱敏视图）
    security.py        主密钥、Fernet 加密、指纹、脱敏、占位符/熵工具
    settings_service.py运行时设置（平台 Token 加密存储等）
    detection/         检测引擎（registry.py 规则加载, engine.py 扫描, rules/*.yaml）
    collectors/        采集器插件（base.py 契约, local_dir, archive, github）
    pipeline.py        采集→检测→入库→去重 流水线
    scheduler.py       APScheduler + 数据库任务声明/恢复
    verification/      验证器插件与队列（base.py, registry.py, verifiers.py, worker.py）
    services.py        发现入库/复核/统计/导出
    api/               路由（overview, sources, findings, verification, channels, settings, import, export）
    alembic/           数据库迁移
  tests/               pytest 测试（规则/引擎/去重/采集/流水线/导出/验证语义/安全）
frontend/
  src/views/           总览/监控任务/发现/验证中心/渠道与规则/设置
docs/                 本目录
examples/demo_repo/   合成泄露样例仓库（用于演示与测试，凭据均为假值）
scripts/              启动脚本
```
