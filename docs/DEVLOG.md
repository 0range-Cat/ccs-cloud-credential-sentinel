# 开发记录（DEVLOG）— 只记真实执行结果

约定：每条记录包含日期、任务ID、实际做的事、实际执行的命令与结果、遇到的问题。
不得写入"计划做"的事；不得记录真实密钥。

## 2026-09-19（会话1：主控）

### T0.1 环境检查 — done

实际执行与结果：

- 工作目录 `G:\2026\我的项目\云凭据检验`，初始为空目录。
- `git --version` → git version 2.53.0.windows.2；user.name=0range-Cat，user.email=2955456920@qq.com（已配置，可直接提交）。
- `python --version` → Python 3.13.9（D:\work\python.exe），满足 3.11+ 要求。
- `node --version` → v24.16.0；`npm --version` → 11.13.0。
- `docker --version` → Docker version 29.7.2。
- 网络：pypi 200、npm registry 200；`api.github.com` → 403（开发网络环境受限）。
  **影响**：GitHub 真实接入验收无法在本机网络完成，采集器以平台响应样例注入方式离线测试；
  真实验收步骤写入 docs/DEMO.md 由用户在其环境执行。

### T0.3 文档体系与 Git 规范 — done

- 建立 README/AGENTS/docs 全套文档（INDEX/REQUIREMENTS/RESEARCH/ARCHITECTURE/INTERFACES/TODO/
  DEVLOG/DEPLOYMENT/SUPPORTED_CHANNELS/SUPPORTED_CREDENTIALS/EVALUATION/HANDOFF/TECHNICAL_MANUAL/
  MASTER_PROMPT/DEMO），.gitignore 排除 data/、日志、.env、*.db、node_modules 等。
- 目录结构初始化：backend/（app+tests+alembic）、frontend/、docs/、examples/、scripts/。

### T0.2 调研 — doing

- 启动子智能体并行调研（开源工具 / 平台接口）。环境限制：后台子智能体同时只能运行一个
  （平台调研首次启动因"user concurrency limit exceeded"失败，待第一个完成后重试）。
- 注意：`api.github.com` 403 预期会影响子智能体联网核实 GitHub 接口细节，无法核实的项标"待核实"。
