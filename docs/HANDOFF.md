# 交接文档（HANDOFF）

> 每次会话结束前更新。禁止记录真实密钥。

## 归档声明（2026-10-08）

**项目已于 2026-10-08 归档封存，移交后续人员接手。** 完整项目档案见仓库根
**[归档/](../归档/00-归档总览.md)**（00 总览 / 01 概览与意义 / 02 开发过程 / 03 进度状态 /
04 架构导览 / 05 使用手册 / 06 部署运维 / 07 遗留与接手指南 / 08 文档索引 / 09 经验教训库 /
**10 进度进展与继续工作指南——33 任务推进状态 + 行动卡，继续干活从这里进** /
**11 工作台账——已完成35/进行中3/未完成7/受阻6 逐条状态+验收+阻塞点**）。
归档时基线：74 项测试通过（2026-10-08 复核）；本文以下内容为封存时刻快照，继续有效但以归档文档为最新入口。

## 当前状态（2026-09-19，会话2结束：阶段2/3/4 完成，阶段5 仅剩项已全部闭环）

- 分支：main；最近提交见 `git log --oneline`。
- 阶段0/1 全部 done；阶段2：T2.1/2.2/2.3/2.5(博客园+SO+通用)/2.6/2.7 done，T2.4 微博 blocked。
- 测试证据：`cd backend && .venv/Scripts/python -m pytest` → **54 passed**。
- **live_verified 渠道 7 个**：GitHub（含受控泄露→发现实验）、Gitee、中文维基百科、博客园 RSS、
  Stack Overflow、OCI 容器镜像（alpine:latest）、Android APK（F-Droid）。
- **验证器 8 个**：GitHub PAT（valid+invalid 双例）、AWS AK/SK 配对（SigV4+STS）、Gitee、GitLab、
  Slack、Telegram、npm、Hugging Face（后 6 个真实网络 invalid 实证）。全量测试 **74 passed**；规则 43 条；组织→仓库种子扩展已实现（live 待新 Token：用户 Token 已失效 401）；Androguard 已装并激活 APK manifest。
- 采集器 10 个（+wxapkg 未加密包；加密包合规拒绝）；自动验证策略已实现（默认关）。
- **Docker 部署已实测**（构建+容器运行验证）；评价维度主证据在 docs/DELIVERABLES.md。
- 受控实验：20 凭据/21 位置/14 类型检出；P50=25.5s/P95=26.9s（n=3，轮询 8s）；
  数据 data/latency_log.json（gitignored）。
- 用户 Token 现为第二批（含 Contents:write，已落地加密库）；**实验已完成，建议吊销轮换**。
- GitHub push protection 实测：合成 Twilio SID 被拦 → 官方 bypass API（used_in_tests）流程已固化。
- 用户 Token：仅存 data/github.token（gitignored）+ 设置库 Fernet 加密；**建议实验后吊销轮换**。
- 交付/答辩口径单一来源：docs/DELIVERABLES.md（四交付件+五评价维度→真实数字）。

## 下一步（按优先级）

1. 阶段4 剩余：各验证器 valid 路径待用户自有凭据回填；OpenAI/Anthropic/Stripe 已如实标
   unsupported（无不枚举资源的合规端点）。
2. 阶段5 剩余：仅 Ubuntu 原生部署实测（可选——Docker 即 Linux 路径已实测覆盖；
   若用户愿提供服务器/SSH 可补）。PostgreSQL 冒烟与 Playwright 界面测试均已完成。
3. 可选增强：Androguard 安装解析 APK manifest（当前如实跳过）；CSDN/掘金合规抓取评估。
4. 交付清单核对（十六节逐项）见 docs/DELIVERABLES.md §五；答辩口径以该文件为准。
5. 最终测试基线：**71 passed** + UI 自动化 7/7 + PG 冒烟 + Docker 容器验证。

## 环境事实（勿重复踩坑）

- 后台子智能体并发上限 1 个。
- Git Bash curl 发中文 JSON body 会 GBK 乱码——用 Python 客户端或界面操作。
- alembic.ini 保持纯 ASCII。
- **维基媒体拒绝通用 UA**（403）；采集器统一 UA：`ccs-collector/0.1 (https://localhost; contact: admin@example.com)`。
- MediaWiki formatversion=2 修订对象**无 revid 字段**，按 pageid 映射。
- Stack Overflow `quota_remaining:0` 判断勿写 `x or 1`（falsy 陷阱）。
- Gitee 匿名限流随共享 IP 波动：实采可行但随时可能 403 → 已验证优雅停止。
- Docker Hub blob 会 307 到 CDN：**采集层**需 follow_redirects=True（验证器仍严格禁重定向）。
- MediaWiki formatversion=2 修订对象无 revid（按 pageid 映射）；维基媒体拒通用 UA（403）。
- 本机 live 检查脚本：`cd backend && .venv/Scripts/python ../scripts/live_check.py`（独立库 data/live.db）。

## 关键技术决策

沿用 ARCHITECTURE.md §2 D1~D8。新增：
- D9 采集游标统一走 collector.cursors dict + 流水线持久化（采集器不接触 DB）；
- D10 统一合规 User-Agent 常量 base.USER_AGENT；
- D11 历史提交时间作"公开时间"仅记 low 可信，不参与分钟级时延统计。

## 未提交改动

无（工作区干净）。

## 外部阻塞与缺配置

| 事项 | 需要 | 状态 |
| --- | --- | --- |
| GitHub 真实验收 | 用户执行 DEMO.md 或提供只读 PAT | 待用户 |
| Gitee 稳定采集 | 用户 Gitee Token（可选，匿名已可演示） | 可选 |
| 微博 | 无合规公开接口 | blocked（记录在案） |
| CSDN/掘金 | 无官方接口 | 阶段2收尾评估 |
| 浏览器自动化（T5.4） | 安装 Playwright 浏览器 | blocked |
