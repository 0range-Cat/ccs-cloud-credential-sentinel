# TODO（阶段任务与状态）

状态：todo / doing / blocked / done。done 必须有实现 + 验证证据（DEVLOG.md 记录真实结果）。
负责人：主控会话（M）/ 子智能体（S）。

## 阶段 0：调研与设计

| ID | 任务 | 状态 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| T0.1 | 环境检查（目录/Git/Python3.13/Node24/Docker/网络） | done | - | DEVLOG 2026-09-19 |
| T0.2a | 开源工具调研（Gitleaks/TruffleHog/detect-secrets/APK/镜像解析） | doing | - | docs/RESEARCH.md 含链接+日期+许可证 |
| T0.2b | 平台接口调研（GitHub/Gitee/Wiki/微博/知识分享/镜像/小程序） | doing | - | 同上 |
| T0.3 | 文档体系与 Git 规范（README/AGENTS/docs 全套/.gitignore） | done | T0.1 | 提交记录 |
| T0.4 | 数据模型/插件契约/状态模型/能力矩阵定义 | done | T0.3 | INTERFACES.md |

## 阶段 1：最小完整闭环

| ID | 任务 | 状态 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| T1.1 | 后端骨架：配置/DB(WAL)/加密/指纹/脱敏/设置服务 | todo | T0.4 | pytest security 测试过 |
| T1.2 | 检测引擎 + 首批规则（含正反样例与占位符过滤） | todo | T1.1 | test_rules/test_engine 过 |
| T1.3 | 采集器：本地目录 / 压缩包导入 / GitHub 仓库 | todo | T1.1 | mock 平台响应测试过 |
| T1.4 | 流水线：入库/去重/多位置/时间字段/忽略规则 | todo | T1.2,T1.3 | test_dedup 过 |
| T1.5 | 调度：APScheduler tick + DB 声明 + 重启恢复 | todo | T1.4 | test_scheduler 过 |
| T1.6 | 验证框架 + GitHub 最小验证器（默认关闭） | todo | T1.4 | test_verification 过 |
| T1.7 | REST API + 脱敏/导出 CSV(JSON)/审计 | todo | T1.4-T1.6 | API 测试过 |
| T1.8 | Vue3 中文界面（总览/任务/发现/验证/渠道规则/设置） | todo | T1.7 | npm build 成功 + 手动走查 |
| T1.9 | 测试套件整备 + EVALUATION 回填 | todo | T1.7 | 全量 pytest 证据 |
| T1.10 | GitHub 演示路径（合成样例 + DEMO.md） | todo | T1.8 | 用户按 DEMO 执行（真实接入验收待用户） |

## 阶段 2：持续发现与网页类渠道

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T2.1 | 持续监控增强：间隔抖动/限流遵循 Retry-After/游标全面接入 | todo | 单测+长跑记录 |
| T2.2 | Gitee 采集器 | todo | mock 测试；真实验收待用户 token |
| T2.3 | MediaWiki 适配器（recentchanges/修订增量） | todo | 对公开 wiki 实测或 mock |
| T2.4 | 微博适配器（合规边界内；无公开接口则明确记录障碍） | todo | 状态与障碍记录 |
| T2.5 | 知识分享：CSDN/博客园/掘金/StackOverflow + 通用 RSS/Sitemap/URL | todo | mock+样例测试 |
| T2.6 | 种子驱动发现（组织/域名/关键词→任务生成）+ 时间模型展示 | todo | API 测试 |

## 阶段 3：制品类渠道

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T3.1 | 容器镜像：OCI registry manifest/config/layers、digest 去重、历史层与 whiteout、大小限制 | todo | 离线 tar/registry mock 测试 |
| T3.2 | Android APK：Androguard/zip 解析、manifest/资源/字符串、上传+版本监控 | todo | 样例 APK 测试 |
| T3.3 | 小程序产物：合法取得的包/解包目录扫描、公开入口监控可行性记录 | todo | 样例产物测试 + 限制记录 |

## 阶段 4：验证与凭据覆盖扩展（可与阶段2/3部分并行）

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T4.1 | 验证队列 worker：并发/重试/有效期/重新验证 | todo | 语义测试 |
| T4.2 | 逐个接入最小验证器（AWS STS GetCallerIdentity、Gitee、Slack auth.test、OpenAI 等），逐一审查请求行为 | todo | 每个验证器 mock 测试+审查记录 |
| T4.3 | 凭据类型扩展（云厂商/数据库/服务账号/邮件/短信/OAuth…）与配对完善 | todo | 正反样例测试 |
| T4.4 | 自动验证策略（按任务/类型/验证器开关） | todo | 策略测试 |

## 阶段 5：集成、评估与交付

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T5.1 | Windows/Ubuntu/Docker 部署验证 | todo | DEPLOYMENT 按步骤复现 |
| T5.2 | PostgreSQL 模式核心流程验证 | todo | pytest 双库冒烟 |
| T5.3 | 性能与恢复测试（重启恢复/重复扫描幂等/资源占用） | todo | EVALUATION 数据 |
| T5.4 | 关键界面流程浏览器自动化测试 | blocked | 待安装 Playwright 浏览器（环境受限时记录） |
| T5.5 | 评估报告/技术说明书/演示指南定稿 | todo | 四项交付件齐全 |
