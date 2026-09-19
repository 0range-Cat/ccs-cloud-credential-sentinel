# 交接文档（HANDOFF）

> 每次会话结束前更新。禁止记录真实密钥。

## 当前状态（2026-09-19，会话2结束：阶段2 第一批完成）

- 分支：main；最近提交：1bc1b1d（四渠道 live_verified）。
- 阶段0/1 全部 done；阶段2：T2.1/2.2/2.3/2.5(博客园+SO+通用)/2.6/2.7 done，T2.4 微博 blocked。
- 测试证据：`cd backend && .venv/Scripts/python -m pytest` → **54 passed**（2026-09-19）。
- live_verified 渠道（本机实采两轮验证）：Gitee、中文维基百科（MediaWiki）、博客园 RSS
  （经通用采集）、Stack Overflow；数据在 data/live.db（gitignored）。
- 可运行成果：7 个采集器（github/gitee/mediawiki/generic_web/stackoverflow/local_dir/archive）、
  35 条规则、验证模块（默认关）、中文界面（六页+种子发现）、游标增量与限流语义。

## 下一步（按优先级）

1. **GitHub 真实验收**：请用户执行 docs/DEMO.md，或提供只读 PAT 由会话执行
   （本机 api.github.com=403 为共享 IP 配额；raw 200）。
2. 阶段2 收尾：CSDN/掘金合规抓取评估（无官方接口，谨慎、只读、遵守 robots 与频率）。
3. 阶段3：容器镜像（Docker Hub 匿名 token 流程调研已打通）→ tar 层解析 → APK（Androguard）。
4. 阶段4：验证器扩展（AWS STS GetCallerIdentity 优先；实现前逐个审查最小认证合规）。

## 环境事实（勿重复踩坑）

- 后台子智能体并发上限 1 个。
- Git Bash curl 发中文 JSON body 会 GBK 乱码——用 Python 客户端或界面操作。
- alembic.ini 保持纯 ASCII。
- **维基媒体拒绝通用 UA**（403）；采集器统一 UA：`ccs-collector/0.1 (https://localhost; contact: admin@example.com)`。
- MediaWiki formatversion=2 修订对象**无 revid 字段**，按 pageid 映射。
- Stack Overflow `quota_remaining:0` 判断勿写 `x or 1`（falsy 陷阱）。
- Gitee 匿名限流随共享 IP 波动：实采可行但随时可能 403 → 已验证优雅停止。
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
