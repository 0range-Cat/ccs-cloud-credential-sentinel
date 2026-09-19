# 交接文档（HANDOFF）

> 每次会话结束前更新。禁止记录真实密钥。

## 当前状态（2026-09-19，会话1：主控）

- 分支：main；仓库：本地初始化（无远程，按规则不擅自推送）。
- 已完成任务：T0.1（环境检查）、T0.3（文档体系与 Git 规范）。
- 进行中：T0.2a/T0.2b（调研，子智能体后台运行，注意并发限制：同时只能跑一个后台子智能体）。
- 阶段1 全部任务（T1.1~T1.10）尚未开始或进行中，以 TODO.md 为准。

## 环境事实（后续会话直接采用，勿重复踩坑）

- Windows 11 + Git Bash；Python 3.13.9（D:\work\python.exe）；Node 24 / npm 11；Docker 29 可用。
- 网络：pypi/npm 可达；api.github.com 403 → GitHub 相关只能 mock 测试 + 用户环境真实验收。
- 中文路径 `G:\2026\我的项目\云凭据检验`，Git Bash 下正常工作。

## 下一步

1. 完成 T1.1 后端骨架 → T1.2 检测引擎 → T1.3 采集器 → T1.4 流水线 → T1.5 调度 →
   T1.6 验证框架 → T1.7 API → T1.9 测试 → T1.8 前端 → T1.10 演示路径。
2. 调研完成后整合 docs/RESEARCH.md（合并 docs/research/draft-*.md，标注日期与链接）。

## 关键技术决策（详见 ARCHITECTURE.md §2）

D1 自研检测引擎为主；D2 同步 ORM + 异步采集（worker 线程 asyncio.run）；
D3 APScheduler 心跳 + DB 任务声明；D4 HMAC 指纹；D5 Fernet 加密 + 主密钥外部化；
D6 单用户回环绑定 + 可选访问令牌；D7 验证模块独立且默认关闭；D8 内建资源限制。

## 外部阻塞与缺配置

- GitHub 真实接入：需用户提供环境执行 DEMO.md（或在其网络环境下配置 PAT）。
- Gitee/MediaWiki/微博/知识分享真实验收：对应账号/条件未提供（阶段2处理）。
- 浏览器自动化测试：阶段5 安装 Playwright 浏览器后补充（当前标 blocked）。
