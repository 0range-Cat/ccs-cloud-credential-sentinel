# 交接文档（HANDOFF）

> 每次会话结束前更新。禁止记录真实密钥。

## 当前状态（2026-09-19，会话1：主控，阶段1 完成）

- 分支：main；最近提交：a2162c1（前端+演示路径）。
- 已完成：T0.1~T0.4（调研与设计）、T1.1~T1.10（最小完整闭环）。
- 测试证据：`cd backend && .venv/Scripts/python -m pytest` → 38 passed（真实执行）。
- 可运行成果：后端 uvicorn + 前端 dist 托管 + 35 条检测规则 + 3 采集器 +
  1 最小验证器（默认关闭）+ 中文六页面界面 + CSV/JSON 脱敏导出。
- 真实服务冒烟：导入样例 → 16 凭据/17 位置，重复扫描幂等，全链路脱敏。

## 新会话必读顺序

AGENTS.md → docs/REQUIREMENTS.md → docs/ARCHITECTURE.md → docs/INTERFACES.md →
docs/TODO.md → 本文件；然后 `git log --oneline` 与 `git status`。

## 下一步（按优先级）

1. **请用户执行 docs/DEMO.md**（GitHub 公开发现真实验收，回填 EVALUATION.md §4）——
   这是当前唯一阻塞真实接入验收的事项（开发网络 api.github.com=403）。
2. 阶段2（T2.1~T2.6）：Gitee（调研确认匿名可用，先行）、MediaWiki（rccontinue 游标）、
   通用 RSS/Sitemap/URL（feedparser 选型完成）、博客园/StackOverflow、GitHub 历史扫描与
   种子驱动发现；微博按"明确记录障碍"口径处理。
3. 阶段3/4 可与阶段2 并行：容器镜像（Docker Hub 匿名流程调研打通）、APK（Androguard）、
   验证器扩展（AWS STS GetCallerIdentity 优先，实现前先复核最小验证合规）。

## 环境事实（勿重复踩坑）

- Windows 11 + Git Bash；Python 3.13.9；Node 24；Docker 29 已装未用于本项目。
- 后台子智能体并发上限 1 个（第二个会 user concurrency limit exceeded，排队重试即可）。
- Git Bash curl 发中文 JSON body 会 GBK 乱码——测试用 Python 客户端或界面操作。
- alembic.ini 保持纯 ASCII（GBK 控制台问题）。
- zip 在 Windows 下写入时反斜杠被规范化为 `/`，路径穿越防护按"段级 .. 检查"实现且已测试。
- 冒烟产生的 data/ 已清理，首次启动会重建（主密钥自动生成）。

## 关键技术决策（详见 ARCHITECTURE.md §2，均已在代码与测试中落地）

D1 自研检测引擎为主（Gitleaks 阶段2 作可选子进程补充）；D2 同步 ORM+worker 线程异步采集
（pipeline._run_async 兼容事件循环内调用）；D3 APScheduler 心跳+DB 声明；
D4 HMAC 指纹（类型+值+配对）；D5 Fernet+主密钥外部化；D6 回环绑定+可选访问令牌；
D7 验证独立默认关（TruffleHog 默认开启在线验证——反向印证）；D8 资源限制内建。

## 未提交改动

无（工作区干净；data/、logs/、.venv、node_modules、dist 均已 gitignore）。

## 外部阻塞与缺配置

| 事项 | 需要 | 状态 |
| --- | --- | --- |
| GitHub 真实验收 | 用户在其网络执行 DEMO.md | 待用户 |
| Gitee/MediaWiki 真实验收 | 无需账号即可部分验收（调研接口匿名可用）；搜索类需 Token | 阶段2 |
| 微博 | 无合规公开接口——按障碍记录口径处理，不绕过 | 阶段2 记录 |
| 小程序公开监控 | 无合法公开获取途径——仅上传/目录分析 | 已在矩阵标注 |
| 浏览器自动化（T5.4） | 安装 Playwright 浏览器 | blocked |
