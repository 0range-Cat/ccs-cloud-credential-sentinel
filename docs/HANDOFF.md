# 交接文档（HANDOFF）

> 每次会话结束前更新。禁止记录真实密钥。

## 当前状态（2026-09-19，会话2结束：阶段2 GitHub 实采完成）

- 分支：main；最近提交见 `git log --oneline`。
- 阶段0/1 全部 done；阶段2：T2.1/2.2/2.3/2.5(博客园+SO+通用)/2.6/2.7 done，T2.4 微博 blocked。
- 测试证据：`cd backend && .venv/Scripts/python -m pytest` → **54 passed**。
- **live_verified 渠道 5 个**：GitHub（认证态实采 12 文件+53 条历史内容；验证器 valid/invalid 实证）、
  Gitee、中文维基百科、博客园 RSS、Stack Overflow。
- 用户 Token：仅存 data/github.token（gitignored）+ 设置库 Fernet 加密；**建议实验后吊销轮换**。
- 交付/答辩口径单一来源：docs/DELIVERABLES.md（四交付件+五评价维度→真实数字）。

## 下一步（按优先级）

1. **受控"泄露→发现时延"实验**（评价维度5）：需用户给 Token 追加该仓库 Contents:write
   （步骤在 DELIVERABLES.md §三）；完成后自动回填 P50/P95。
2. 阶段3：容器镜像（Docker Hub 匿名流程已调研打通）→ tar 层解析/whiteout → APK（Androguard）。
3. 阶段4：验证器扩展（AWS STS GetCallerIdentity 等，逐个最小认证审查）。
4. CSDN/掘金合规抓取评估（无官方接口）。

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
