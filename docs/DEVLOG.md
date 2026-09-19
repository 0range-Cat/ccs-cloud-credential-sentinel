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

### T0.2 调研 — done

- 子智能体1（开源工具）：产出 docs/research/draft-tools.md。核实：Gitleaks v8.30.1（MIT，
  约 165 规则，纯离线）；TruffleHog v3.97.5（AGPL-3.0，**验证默认开启**）；detect-secrets 1.5.0
  （Apache-2.0，部分插件 verify 会外呼）；Androguard 4.1.4（Apache-2.0）。8 项待核实已标注。
- 子智能体2（平台接口）：产出 docs/research/draft-platforms.md（352 行，24 条来源链接）。
  实测：MediaWiki recentchanges 200（rccontinue 游标）、博客园 RSS 200、StackOverflow 匿名
  quota 300/天、Gitee 内容/树接口匿名 200、Docker Hub 匿名 token+manifest 打通；
  结论：微博无合规公开检索接口；CSDN/掘金无官方接口；小程序无合法公开获取途径。
- 已整合为 docs/RESEARCH.md（含决策：TruffleHog 因 AGPL+默认在线验证不引入运行链路）。
- 环境限制记录：后台子智能体同时只能运行 1 个（并发限制），平台调研首次启动失败后重跑成功。

## 2026-09-19（会话1：阶段1实现）

### T1.1~T1.7 后端 — done

- 提交序列：7da25c7（骨架）→ 388c544（检测引擎+35 规则）→ b377088（核心模块+API）→
  92a03a5（测试）→ a2162c1（前端+演示）。
- 规则自检冒烟：首次发现 5 处样例问题（字符计数偏差/引号可选性/组检查），修复后
  `规则数: 35 / 规则自检通过`。
- Alembic：autogenerate 基线 659df6833a92，upgrade→downgrade→upgrade 链路实测通过。
  踩坑：alembic.ini 含中文注释在 GBK 控制台触发 UnicodeDecodeError，改纯 ASCII。
- 测试开发中修复的真实缺陷：
  1) 验证器注册的是类而非实例（TypeError）；
  2) `BaseCollector` 缺 `rate_limited` 默认属性 → 流水线 internal_error；
  3) `trigger_manual_run` 先置 running 与 `run_task` 防重叠检查冲突 → 扫描被跳过（发现数 0 的根因）；
  4) API 事件循环内调用 `asyncio.run` 报错 → pipeline 增加 `_run_async` 线程适配；
  5) verification_api 缺 import Credential（NameError）。
  全部以测试回归锁定。

### T1.9 测试证据 — done

- `cd backend && .venv/Scripts/python -m pytest` → **38 passed, 3 warnings**（2026-09-19）。

### T1.8 前端 + 真实服务冒烟 — done

- `npm install` + `npm run build` → 构建成功（dist 由后端 StaticFiles 托管）。
- uvicorn 实跑（127.0.0.1:8766）：
  - `/api/system/info`：35 规则 / 3 采集器 / 1 验证器；
  - 导入样例目录 → candidates=17、new_credentials=16、new_occurrences=17、completed；
  - 发现列表 16 条全部脱敏；GitHub PAT 样例 2 位置关联；Twilio 配对加成 55→75/60→80；
  - 幂等：重复扫描 items_skipped=7、新增 0，唯一凭据/位置不变；
  - detection_latency.sample_count=0（公开时间未知，未冒充）。
- 冒烟后已清理 data/（含临时主密钥与测试库），交付干净初始状态。
- 已知终端限制：Git Bash curl 发中文 JSON body 会编码错乱（控制台 GBK），Python/浏览器无此问题。

### T1.10 演示路径 — done（真实接入验收待用户）

- examples/demo_repo 合成样例（无法认证的假值）+ docs/DEMO.md 六步演示指南。
