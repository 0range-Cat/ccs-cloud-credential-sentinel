# TODO（阶段任务与状态）

状态：todo / doing / blocked / done。done 必须有实现 + 验证证据（DEVLOG.md 记录真实结果）。
负责人：主控会话（M）/ 子智能体（S）。

## 阶段 0：调研与设计

| ID | 任务 | 状态 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| T0.1 | 环境检查（目录/Git/Python3.13/Node24/Docker/网络） | done | - | DEVLOG 2026-09-19 |
| T0.2a | 开源工具调研（Gitleaks/TruffleHog/detect-secrets/APK/镜像解析） | done | - | docs/RESEARCH.md + research/draft-tools.md |
| T0.2b | 平台接口调研（GitHub/Gitee/Wiki/微博/知识分享/镜像/小程序） | done | - | docs/RESEARCH.md + research/draft-platforms.md（含实测数据） |
| T0.3 | 文档体系与 Git 规范（README/AGENTS/docs 全套/.gitignore） | done | T0.1 | 提交记录 |
| T0.4 | 数据模型/插件契约/状态模型/能力矩阵定义 | done | T0.3 | INTERFACES.md |

## 阶段 1：最小完整闭环

| ID | 任务 | 状态 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| T1.1 | 后端骨架：配置/DB(WAL)/加密/指纹/脱敏/设置服务 | done | T0.4 | 38 项 pytest 全过（test_security 等） |
| T1.2 | 检测引擎 + 首批规则（35 条，含正反样例与占位符过滤） | done | T1.1 | test_rules/test_engine 过；注册表自检通过 |
| T1.3 | 采集器：本地目录 / 压缩包导入 / GitHub 仓库 | done | T1.1 | test_collectors 过（GitHub 平台响应样例注入） |
| T1.4 | 流水线：入库/去重/多位置/时间字段/忽略规则 | done | T1.2,T1.3 | test_pipeline_dedup 过 |
| T1.5 | 调度：APScheduler tick + DB 声明 + 重启恢复 | done | T1.4 | test_pipeline_dedup（恢复/防重叠）过 |
| T1.6 | 验证框架 + GitHub 最小验证器（默认关闭） | done | T1.4 | test_verification 过（11 态语义/历史追加/零自动验证） |
| T1.7 | REST API + 脱敏/导出 CSV(JSON)/审计 | done | T1.4-T1.6 | test_api_e2e 过；真实服务冒烟通过 |
| T1.8 | Vue3 中文界面（总览/任务/发现/验证/渠道规则/设置） | done | T1.7 | npm build 成功；后端托管实测打开 |
| T1.9 | 测试套件整备 + EVALUATION 回填 | done | T1.7 | 38 passed（2026-09-19 实测） |
| T1.10 | GitHub 演示路径（合成样例 + DEMO.md） | done | T1.8 | 路径就绪；真实接入验收待用户在其网络执行 |

## 阶段 2：持续发现与网页类渠道

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T2.1 | 持续监控增强：游标基础设施（collector↔DB）/区间抖动/限流遵循 | done | 54 项测试 + live 两轮验证（304/版本缓存/游标） |
| T2.2 | Gitee 采集器 | done（live_verified） | live_check 实采+限流停止语义；Token 真实验收待用户配置 |
| T2.3 | MediaWiki 适配器（recentchanges/修订增量） | done（live_verified） | 中文维基百科实采 6 条+游标续扫 |
| T2.4 | 微博适配器 | blocked | 无合规公开接口；障碍与配置需求已记录（SUPPORTED_CHANNELS/RESEARCH） |
| T2.5 | 知识分享：博客园/StackOverflow + 通用 RSS/Sitemap/URL | done（博客园/SO/generic live_verified；CSDN/掘金 planned） | live 两轮实测 |
| T2.6 | 种子驱动发现（组织/域名/关键词→任务生成）+ 时间模型展示 | done | test_discover 3 项；纯关键词不做无认证代码搜索（如实提示） |
| T2.7 | GitHub 历史提交扫描（新→旧+游标+低可信公开时间） | done（offline_tested） | mock 测试含第二轮游标增量断言；真实验收随 DEMO |

## 阶段 3：制品类渠道

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T3.1 | 容器镜像：OCI registry manifest/config/layers、digest 去重、历史层与 whiteout、大小限制 | done（live_verified） | 58 项测试含 whiteout/最终视图断言；alpine:latest 匿名实采 40 条 |
| T3.2 | Android APK：zip/dex 字符串解析、可选 Androguard manifest、上传+URL 版本监控 | done（live_verified） | mock APK 测试；F-Droid 官方 APK 实采 25 条；二进制 manifest 未装 Androguard 时如实跳过 |
| T3.3 | 小程序产物：未加密 wxapkg 容器解析 + 上传/URL 入口；加密包明确拒绝（合规边界，不解密）；解包目录经本地目录扫描 | done（offline_tested） | 测试含加密拒绝/越界拒绝；线上包无合法公开获取途径已记录 |

## 阶段 4：验证与凭据覆盖扩展（可与阶段2/3部分并行）

| ID | 任务 | 状态 | 验收 |
| --- | --- | --- | --- |
| T4.1 | 验证队列 worker：限量限速、自动验证策略（默认关；开启后未验证→入队、超期→重验、瞬态失败→重试） | done | 测试覆盖开关与各分支（test_phase45） |
| T4.2 | 最小验证器：GitHub/Gitee/GitLab/Slack/Telegram/AWS(配对)/npm/HF 共 8 个已接入；OpenAI/Anthropic/Stripe 无不枚举资源的合规验证端点 → unsupported（如实记录） | doing（8 平台；6 个真实网络 invalid 实证） | 71 项测试；真实网络假凭据验证记录见 DEVLOG |
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
