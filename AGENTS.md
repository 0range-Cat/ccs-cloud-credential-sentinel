# AGENTS.md — 本项目开发规则（所有会话/子智能体必须遵守）

## 项目定位

网络安全创新大赛赛题"云上凭据泄露的自动化检测"的可交付系统。单人使用、中文界面、
模块化单体、默认不验证。完整需求见 `docs/REQUIREMENTS.md` 与 `docs/MASTER_PROMPT.md`。

## 开工前必读（新会话/新子智能体）

1. `AGENTS.md`（本文件）→ 2. `docs/REQUIREMENTS.md` → 3. `docs/ARCHITECTURE.md`
   → 4. `docs/INTERFACES.md` → 5. `docs/TODO.md` → 6. `docs/HANDOFF.md`
2. `git status` 与最近提交，确认没有未合并的工作，不要从头重建项目。

## 硬性规则

- **先设计后编码**：实现前先更新 `docs/TODO.md` 与相关设计文档；完成后同步更新受影响的文档。
- **状态口径**：区分 规划支持 / 代码已实现 / 离线测试通过 / 真实接入验证通过。
  空接口、静态页面、模拟数据不算实现；没有测试证据不得标 done。
- **不伪造**：不伪造调研结果、不伪造测试结果、不把模拟 valid 计入真实发现；
  平台受限就记录障碍与剩余工作。
- **验证合规**：验证模块只能做"判断认证状态的最小操作"，不读业务数据、不枚举资源、
  不试用计费功能；默认关闭。禁止把采集到的凭据发送到与其所属服务无关的第三方。
- **敏感数据**：`data/`、`*.db`、`.env`、日志、解包产物一律不入 Git；
  凭据原文与平台 Token 必须加密存储；关闭界面脱敏不等于把凭据写入日志/URL/异常。
- **检测合规**：检测阶段禁用第三方引擎自带的在线验证；不引入绕过平台访问控制的能力。
- **Git**：每完成一个可独立验证的改动即提交，消息用 feat/fix/docs/test/refactor/chore 前缀；
  不推送远程、不改写历史；不覆盖无关文件。
- **技术栈锁定**：Python 3.11+ / FastAPI / SQLAlchemy 2 / Alembic / SQLite(WAL)→PostgreSQL /
  httpx / APScheduler / Vue3+TS+Vite+Element Plus。变更选型必须先在 ARCHITECTURE.md 写理由。

## 并行协作约定

- 环境支持子智能体时用子智能体；否则在 `docs/tasks/` 生成可复制的任务提示词，不假装已运行。
- 子智能体只允许写分配目录；共享部分（模型/迁移/依赖锁/公共路由）由主控会话统一修改。
- 发现契约问题先在 HANDOFF.md/TODO.md 提记录，不擅自破坏其他模块。

## 任务状态与验收

- TODO 状态：todo / doing / blocked / done；done 必须附验收命令与真实结果（写在 DEVLOG.md）。
- 被外部条件阻塞（如缺少平台账号）→ 标 blocked 并写明配置需求，转做其他任务。

## 提交检查单

- [ ] pytest 通过（`cd backend && python -m pytest -q`）
- [ ] 前端可构建（`cd frontend && npm run build`，如改动前端）
- [ ] 文档同步（TODO/DEVLOG/能力矩阵/部署说明受影响部分）
- [ ] 未提交任何敏感数据
