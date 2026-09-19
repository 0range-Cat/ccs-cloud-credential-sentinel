# 测试与评估报告（EVALUATION）

> 更新：2026-09-19 阶段1完成。所有数据均来自真实执行的命令（见 DEVLOG.md），不含估算冒充。

## 1. 测试环境

| 项 | 值 |
| --- | --- |
| 操作系统 | Windows 11（10.0.26200） |
| Python / Node | 3.13.9 / 24.16.0 |
| 依赖版本 | backend/requirements.txt 锁定（fastapi 0.141.1 等） |
| 数据库 | SQLite WAL（临时目录，测试隔离） |
| 执行方式 | `cd backend && .venv/Scripts/python -m pytest` |

## 2. 离线可重复测试结果（2026-09-19 实测：38 passed）

| 测试文件 | 覆盖 | 结果 |
| --- | --- | --- |
| test_rules_registry.py | 35 条规则加载、ID 唯一、每条有正反例、注册表自检（正例命中+反例不误报） | ✅ |
| test_engine.py | AK/SK 配对加成（60→80）、有边界 Base64 解码、PEM 块与加密状态（含 OpenSSH unknown）、GCP 服务账号结构化解析、占位符/文档示例拒绝、低熵拒绝、连接串弱口令拒绝、上下文缺失拒绝、跨规则重叠消解、>1MB 输入截断标记 | ✅ |
| test_security.py | Fernet 加解密回环、指纹稳定性与类型/配对分离、脱敏预览、占位符判定、熵 | ✅ |
| test_collectors.py | 本地目录（过滤/二进制跳过/系统目录排除）、zip（路径穿越拒绝、大文件跳过）、tar（符号链接跳过）、GitHub mock（正常树+blob、**限流 403+配额头→优雅停止并标记**、401→认证失败语义、仓库标识解析） | ✅ |
| test_pipeline_dedup.py | 入库去重、同凭据两文件=1 凭据 2 位置、重复扫描幂等（0 新增）、忽略规则=标记 not 删除（留痕）、公开时间未知口径、重启恢复（running→interrupted、任务回 pending）、防重叠 | ✅ |
| test_verification.py | **扫描链路零验证请求（默认关闭）**、无验证器类型→unsupported 保留检测、HTTP 200/401/403(限流)/403/500 → valid/invalid/rate_limited/inconclusive/inconclusive、网络故障→network_error 不判无效、302 不跟随不判有效、每次验证追加历史、证据不含响应体 | ✅ |
| test_api_e2e.py | 设置（Token 加密+响应脱敏）→连接测试→建来源→运行→发现列表脱敏→详情（位置/上下文/时间）→reveal 审计→复核流转→批量复核→CSV/JSON 导出（脱敏/原文/公式注入防护）→验证队列→渠道规则启停→压缩包导入→任务暂停恢复 | ✅ |

### 精确率/召回率说明（诚实口径）

当前 35 条规则的自检样例=**调优样本**，仅证明规则行为符合设计。
独立评估样本集（真实标注数据）尚未建立——阶段5 按凭据类型分别报告 P/R，
现在不给出任何"总精确率"数字。

## 3. 端到端（真实服务）冒烟结果（2026-09-19，uvicorn 实跑）

- `/api/system/info`：35 规则、3 采集器（archive/github/local_dir）、1 验证器（github-pat）。
- 导入样例目录 → 批次统计：items_seen=7，candidates=17，**new_credentials=16，new_occurrences=17**，
  stop_reason=completed。
- 发现列表：16 条，默认脱敏（如 `ghp_4****kL2b`）；GitHub PAT 样例正确关联 2 个位置；
  Twilio 配对加成生效（SID 55→75、Token 60→80）。
- 幂等：再次运行同来源 → items_skipped=7，new_credentials=0，new_occurrences=0，
  唯一凭据/位置数量不变。
- 统计口径：detection_latency.sample_count=0（所有来源均为"公开时间未知"）——
  系统没有用抓取时间冒充公开时间。
- 前端 dist 由后端托管，页面正常打开。

## 4. 真实渠道测试（live）

### 4.1 已完成：四渠道两轮实采（2026-09-19，scripts/live_check.py，独立库 data/live.db）

方法：对每个真实公网渠道创建来源任务，运行完整流水线（采集→检测→入库→去重）两轮；
第一轮验证采集与检测，第二轮验证增量语义（版本缓存/游标/条件请求）。预算收紧
（max_items=6，rate 2/s）以控制对目标站点的请求量。

| 渠道 | 第一轮 | 第二轮（增量验证） | 结论 |
| --- | --- | --- | --- |
| Gitee（openharmony/docs） | 实采 7 条内容入库 | 6/7 版本缓存跳过 | 实采成功；后续匿名限流触发 → rate_limited 优雅停止（语义验证） |
| 中文维基百科 recentchanges | 实采 6 条修订入库 | 游标推进，拉到全为新变更 | rccontinue 增量有效；修订时间=medium 可信公开时间 |
| 博客园首页 RSS | 实采 6 条 | ETag → **304 未变更跳过** | 条件请求增量有效 |
| Stack Overflow（关键词 api key） | 实采 6 条问题正文 | 6/6 版本缓存跳过 | 增量有效；配额/backoff 语义生效 |

发现数量口径：本轮四个渠道的目标内容（文档/百科/博客首页/技术问答）未检出凭据候选，
`credentials_total=0`——这是真实的空结果，不冒充发现。检测能力由离线样例（EVALUATION §2）
与 GitHub 演示路径（DEMO.md）覆盖。

排查过程中修复的两个真实缺陷（均有测试锁定）：
1. MediaWiki formatversion=2 修订对象不含 revid 字段 → 内容映射全空（改按 pageid 映射）；
2. 采集器无产出即停止时流水线漏记 rate_limited 标志。

另实测确认：维基媒体对通用 UA 返回 403，策略合规 UA（描述+联系方式）返回 200，
采集器已内置合规 UA。

### 4.2 GitHub：待用户执行

| 项 | 状态 |
| --- | --- |
| 公开发现演示 | 待用户按 docs/DEMO.md 执行后回填（本开发网络 api.github.com=403，raw 可用） |
| 在线验证（自有凭据） | 待用户提供本地配置后执行；模拟 valid 不计入真实发现 |
| Gitee/MediaWiki/RSS/SO | ✅ 见 §4.1 |
| 微博 | blocked（无合规公开接口，已记录障碍） |
| CSDN/掘金/镜像/APK/小程序 | 阶段2后半/阶段3 |

## 5. 未完成项与外部限制

1. 真实渠道验收依赖用户账号/网络（DEMO.md 提供步骤）。
2. 浏览器自动化测试未安装（TODO T5.4，blocked：需下载 Playwright 浏览器）。
3. 独立评估样本集未建立（阶段5）。
4. PostgreSQL 模式、Docker、Ubuntu 部署步骤已写未实测（阶段5 T5.1/T5.2）。
5. 长时间运行资源占用与分钟级时延统计：待持续监控演示后回填（DEMO 步骤5）。
