# 工具源代码技术说明书

> 交付件 2。本文档面向评审与后续维护者，完整描述系统使用的关键技术原理与各模块代码功能实现。
> 配套文档：[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)（渠道与凭据支持清单及数量口径）、
> [EXTENSIBILITY.md](EXTENSIBILITY.md)（可扩展性设计与实证）、[ARCHITECTURE.md](ARCHITECTURE.md)（决策记录）、
> [EVALUATION.md](EVALUATION.md)（测试与评估证据）。
> 版本：0.1.0（2026-09-19）；代码与文档同仓库可追溯。

---

## 1. 系统概述

### 1.1 定位与能力边界

本系统是面向"云上凭据泄露自动化检测"赛题的单机可持续运行平台：对公开渠道与制品
（代码托管、Wiki、知识分享、容器镜像、Android APK、小程序产物、本地导入）中泄露的
凭据进行**采集 → 检测 → 入库去重 → 人工复核 → 可选最小化在线验证 → 脱敏展示与导出**。

能力边界（合规设计，非实现限制）：
- 只检测公开内容中的凭据，不入侵、不绕过平台访问控制/加密（加密小程序包明确拒绝解析）；
- 在线验证默认关闭，且仅允许"判断认证状态的最小请求"（见 §2.6），不读业务数据、不枚举资源；
- 单人使用，中文界面，默认绑定 127.0.0.1，无复杂权限体系。

### 1.2 总体架构

模块化单体（非微服务），九个逻辑子系统通过显式接口解耦：

```
┌──────────────────────────────────────────────────────────────┐
│                 FastAPI 应用（main.py，端口 8000）              │
│        REST API (/api/*)  +  静态托管前端（frontend/dist）      │
└──────────┬───────────────────────────────┬───────────────────┘
           │                               │
┌──────────▼────────────┐      ┌───────────▼───────────────────┐
│ 调度器 scheduler.py    │      │ API 路由层 api/*（9 组路由）    │
│ APScheduler 心跳 tick  │      │ 总览/来源/发现/验证/规则/       │
│ + 数据库任务声明领取    │      │ 设置/导入/种子发现/导出         │
└──────────┬────────────┘      └───────────┬───────────────────┘
           │ 线程池（CCS_WORKERS，默认2）    │
┌──────────▼────────────────────────────────▼───────────────────┐
│                       流水线 pipeline.py                        │
│  Collector插件产出ContentItem → 版本缓存去重 → 检测引擎 →        │
│  忽略规则过滤 → 凭据指纹入库 → 位置location_hash去重 → 游标持久化 │
└──────────┬────────────────────────────────┬───────────────────┘
           │                                │
┌──────────▼────────────┐      ┌────────────▼──────────────────┐
│ 采集子系统 collectors/  │      │ 验证子系统 verification/       │
│ 10 个插件（§3.4）       │      │ 8 个最小验证器 + 队列 worker    │
│ 异步 httpx 拉取         │      │ （独立进程线程，默认关闭）       │
└──────────┬────────────┘      └───────────────────────────────┘
           │
┌──────────▼─────────────────────────────────────────────────────┐
│ 检测子系统 detection/：规则注册表（YAML×35）+ 多信号引擎          │
│ 存储层 SQLAlchemy 2 ORM × 13 表 → SQLite(WAL) / PostgreSQL      │
│ 敏感字段 Fernet 加密（主密钥外部化）                               │
└─────────────────────────────────────────────────────────────────┘
```

数据流（一次持续监控轮询）：
`APScheduler tick（20s）→ 发现到期任务 → 线程池领取（防重叠）→ 创建 ScanRun 批次 →
采集器按预算产出 ContentItem → (source,version_id,path,content_hash) 版本缓存查重 →
新内容落库 SourceContent → 检测引擎产出 Candidate → 忽略规则匹配 →
凭据按 HMAC 指纹 get_or_create / 位置按 location_hash get_or_create →
提交事务 → 采集器游标写回 cursors 表 → 更新任务 next_run_at（±10% 抖动）`。

### 1.3 技术栈与运行形态

| 层 | 选型 | 版本（锁定于 backend/requirements.txt） |
| --- | --- | --- |
| 后端框架 | FastAPI + Uvicorn | 0.141.1 / 0.53.0 |
| ORM / 迁移 | SQLAlchemy 2（同步会话）+ Alembic | 2.0.54 / 1.20.0 |
| 数据库 | SQLite(WAL) 默认；PostgreSQL 可选 | PG 实测 psycopg 3.3.6 |
| 采集网络 | httpx（异步客户端 + MockTransport 可注入） | 0.28.1 |
| 调度 | APScheduler BackgroundScheduler（仅心跳） | 3.11.3 |
| 安全 | cryptography Fernet | 50.0.1 |
| 前端 | Vue 3 + TypeScript + Element Plus + Vite | vue 3.5 / vite 6 |
| 测试 | pytest（71 项）+ Playwright/Chromium（界面 7 流程） | 9.1.1 / 1.63.0 |
| 部署 | Windows/Ubuntu 原生 uvicorn；Docker 多阶段镜像 | 实测通过 |

运行形态：`uvicorn app.main:app` 单进程；采集协程在 worker 线程的事件循环中执行
（API 同步触发时自动另起线程事件循环，见 pipeline._run_async）；验证队列独立线程；
调度心跳独立线程。数据目录 `data/`（数据库 + 主密钥 + 临时区），不入版本库。

---

## 2. 关键技术原理（详细）

### 2.1 凭据检测引擎：多信号组合管线

单条正则的误报率在真实数据上不可用，本引擎将检测拆为**七步组合管线**
（`detection/engine.py::DetectionEngine.scan`），每一步的输出进入下一步过滤或增强：

1. **正则捕获层**：每条规则（YAML）含 1~6 个预编译正则，`finditer` 全文扫描；
   捕获组 `(?P<secret>...)` 或 `secret_group` 指定值位置；同时记录命中行号
   （二分查找行偏移表 `offsets`）与匹配区间 `span`。
2. **长度窗与占位符过滤**：`min_length/max_length` 硬窗；占位符判定
   （`security.is_placeholder`）= 通用词表（your_/example/xxxx/changeme…，共 30+ 词元，
   大小写不敏感子串匹配）+ 重复字符检测（长度≥12 且字符集≤4）+ 常见弱口令名。
   被拒候选**不丢弃**而是标记 `rejected_candidate=True` 保留在结果中
   （证据可查、测试可断言"为什么没检出"，入库阶段才过滤）。
3. **已知文档示例拒绝**：规则级 `known_examples`（如 AWS 文档示例 AKIAIOSFODNN7EXAMPLE）精确匹配拒绝。
4. **规则级禁值**：`forbidden_secret_values` 正则作用于**捕获值及全部捕获组**——
   数据库连接串规则靠它拒绝 `user:password@` 这类文档占位（口令在第 2 组）。
5. **熵过滤**：`min_entropy` 对捕获值计算香农熵（`security.shannon_entropy`），
   如通用配置赋值规则要求 ≥3.2 bit/字符。
6. **上下文验证**：`required_context`（任一命中即可）与 `forbidden_context`（命中即拒）
   在**命中行 ±context_window 行**（默认 ±3）的窗口文本中搜索——变量名/服务域名等弱上下文信号。
   例：`gitee-token` 规则的 32 位十六进制串必须附近出现 gitee/private_token/access_token。
7. **格式感知与增强层**（详见下）+ **配对**（§2.1.1）+ **重叠消解**（§2.1.2）。

**格式感知层**（在正则层之外的三类结构化扫描）：
- **PEM 块捕获**（`_scan_block`）：`capture_block: true` 的规则从 `-----BEGIN ... PRIVATE KEY-----`
  匹配开始，向后搜索 `-----END ...-----` 收整块；证据记录 `key_type`（RSA/EC/OPENSSH…）与
  `encrypted` 状态（头含 ENCRYPTED 或 `Proc-Type: 4,ENCRYPTED` → True；OpenSSH 无法判定 →
  `"unknown"`，如实标注）。
- **结构化 JSON**（`_scan_structured`）：`structured: gcp_service_account` 规则对整体
  `json.loads` 成功且 `type=="service_account"` 且含 `private_key`/`client_email` 的对象，
  产出候选并把 client_email/project_id 作为**配对字段**带入。
- **有边界 Base64 解码**（`_scan_base64`）：`[A-Za-z0-9+/]{48,}={0,2}` 连续段尝试解码
  （≤20 次/文件、解码后 ≤200KB、可打印率 ≥85%、递归深度 ≤1），解码文本递归重扫并把
  `decoded_base64=True` 写入证据。资源上限防"解码炸弹"。

#### 2.1.1 AK/SK 配对

规则 YAML 声明 `pairing: {with: <对方规则id>, max_line_distance: N, boost: B}`。
引擎在 `_apply_pairing` 中对每对候选检查行距 ≤N，命中则：
- 双侧 `confidence += boost`（如 AWS Secret Access Key 60→80）；
- 双侧证据写入 `paired_with`（对方规则与行号）**及 `paired` 字段值**
  `{对方类型: 对方捕获值}`——这是成对验证器（AWS STS 需要 AK+SK）的数据来源，
  同时使凭据指纹包含配对值：**同一 SK 配不同 AK 视为不同账号**（不同指纹，不合并）。

#### 2.1.2 重叠消解

同一文本片段常被多条规则命中（如 `GITHUB_TOKEN=ghp_...` 同时命中 github-pat 与
generic-env-assignment）。`_resolve_overlaps` 按**置信度降序**保留首个候选，
后续与已保留候选"同捕获值且区间重叠"的丢弃——同值同区间只产出最高置信度的一条，
避免跨规则重复计数；置信度相同时按区间起点+规则 ID 稳定排序。

#### 2.1.3 置信度模型

`最终置信度 = 规则基线 confidence ± 配对 boost`，钳制 [0,100]；
展示分级 high(≥80) / medium(≥50) / low。基线由规则作者按"格式自证强度"设定：
自证强（Slack xoxb-、Stripe sk_live_）90~95；依赖上下文（Azure AccountKey、腾讯云 SK）60~80；
弱特征（配置文件口令 password-with-context）仅 35，必须人工复核。
**高熵字符串本身不构成候选**——引擎没有"纯熵"规则。

### 2.2 凭据实体与出现位置分离：去重模型

"同一凭据"与"同一次出现"是两个实体（`models.py::Credential / Occurrence`）：

- **凭据指纹**（`security.credential_fingerprint`）：
  `HMAC-SHA256( pepper, 类型 + "\\0" + 捕获值 [+ "\\0" k=v 每个配对字段] )`。
  pepper = `sha256("ccs-fingerprint-v1:" + 主密钥)` 派生——指纹稳定可重算，但**不可由指纹反推原文**，
  低熵密码也不会以普通哈希形态泄露（无 pepper 的哈希可被彩虹表攻击）。
  入库时 `get_or_create`：存在则仅更新 `last_seen_at` 并取置信度最大值。
- **位置哈希**（`security.location_hash`）：
  `SHA256(平台 | 原始URL | 仓库 | 路径 | 版本号 | 行号 | 内容哈希)`——
  唯一约束 `(credential_id, location_hash)`：同一位置重复扫描**不新建事件**，仅更新
  `last_seen_at`；同凭据跨文件/跨仓库自然形成多位置关联；
  同一位置出现不同凭据（同一行两个密钥）也不冲突。
- **内容级版本缓存**（`models.SourceContent`）：唯一约束
  `(source_id, version_id, path, content_hash)`。流水线对每个 ContentItem 先查该键，
  命中即 `items_skipped++` 直接跳过——这是增量扫描的第一道闸（GitHub blob sha、
  镜像层 digest、APK 整包 sha256、RSS 链接+日期等都归一为 version_id）。
- 复核/审计：`ReviewLog` 记录 confirm/false_positive/ignore/restore/**reveal_access**
  （查看原文留痕）与自动忽略（命中忽略规则时 system 写入）。

实测口径：重复扫描同仓库 → `items_skipped=全部、new_credentials=0、new_occurrences=0`，
唯一凭据与位置数量不变（tests/test_pipeline_dedup + 真实服务冒烟）。

### 2.3 时间模型与发现时延口径

七类时间字段全部分开存储（UTC，naive），禁止互相冒充（`models.py` + `INTERFACES.md §2`）：

| 字段 | 语义 | 由谁写入 |
| --- | --- | --- |
| source_published_at | 能证明的内容公开时间 | 采集器，必须带 published_source（依据）与 published_confidence |
| published_confidence | none / low / medium / high | 采集器声明：修订时间戳=medium；镜像构建时间/git 提交时间/sitemap lastmod=low；GitHub 文件/本地文件=none |
| source_updated_at | 来源侧更新时间 | 采集器 |
| fetched_at | 抓取时间 | 流水线 |
| detected_at / first_seen_at / last_seen_at | 检测时刻 / 系统首末发现 | 流水线 |
| verified_at | 验证完成时刻 | 验证 worker |

- 公开时间未知 → 存 NULL，界面显示"未知"，**不参与时延统计**；
  总览页时延分布只取 `published_confidence ∈ (medium, high)` 的样本并显示样本数。
- commit_authored_at 等来源时间存 extra/证据，单独展示。
- 时延实验（受控源）另行记录 T0（推送完成时刻，第一手证据）与 T1，方法见
  `scripts/latency_experiment.py`；结果 P50=25.5s / P95=26.9s（n=3，轮询 8s）。

### 2.4 增量采集机制

三个机制叠加实现"持续监控不重复劳动"：

1. **版本缓存**（§2.2 第三道闸）：内容不变即整项跳过（网络零请求，除列表接口）。
2. **采集游标**（`cursors` 表，`pipeline._persist_cursors`）：采集器通过注入的
   `cursor_store` dict 读写游标（`save_cursor`），运行结束由流水线统一持久化；
   下次运行预载。实例：MediaWiki `rccontinue`（增量续扫已实测）、RSS 的
   ETag/Last-Modified（304 Not Modified 跳过，实测）、GitHub 历史扫描的
   `last_commit_scanned`（新提交优先、碰到游标即止，实测）。
3. **条件请求**：generic_web 采集器带 If-None-Match / If-Modified-Since，服务端 304 → 零下载。

**限流与预算**（框架统一执行，采集器免实现）：
- 预算：`max_items / max_bytes / max_seconds`（来源配置可覆盖全局默认），逐项检查，
  停止原因记入批次统计（budget_items/budget_bytes/budget_time）；
- 限流：采集器置 `rate_limited=True`（HTTP 403+配额头 / 429 / Retry-After），流水线
  以 `stop_reason=rate_limited` **优雅停止**（不是失败），不拖垮其他渠道；
  GitHub blob 下载间隔按 `rate_per_sec`（默认 2/s）节流；
- 资源熔断：压缩包/wxapkg/APK 的成员数、单成员大小、解压总量上限；
  检测输入 1MB 截断（截断标记入证据）；tar 成员符号链接/设备文件跳过、
  zip 绝对路径与 `..` 段拒绝。

### 2.5 持久化调度与崩溃恢复

- **心跳+声明**：APScheduler 每 `CCS_SCHEDULER_TICK_SECONDS`（默认 20s）触发一次
  `scheduler._tick`，查询 `mode=continuous AND status=pending AND next_run_at<=now` 的任务，
  逐个置 `running` 后提交线程池执行 `pipeline.run_task`。
  `run_task` 自身再校验状态（`already_running` 跳过）——两级防重叠；
  手动触发（`trigger_manual_run`）不在触发时置状态，统一由 run_task 领取，避免语义冲突。
- **抖动**：`next_run_at = now + interval × U(0.9, 1.1)`，避免固定节律。
- **恢复**：启动时 `recover_interrupted` 把上次"运行中"的批次标 `interrupted`
  （原因 `interrupted_by_restart` 写入批次统计）、任务回 `pending` 等待重排——
  结合版本缓存与位置唯一约束，重启后重跑天然幂等。
- **采集协程宿主**：`pipeline._run_async` 探测当前线程事件循环——worker 线程直接
  `asyncio.run`；API 请求上下文（已在循环内，如同步触发/测试）则另起单线程池执行，
  避免 `asyncio.run` 嵌套异常（实测踩坑后固化）。

### 2.6 最小化在线验证

设计原则（`verification/base.py` 契约 + `verifiers.py` 实现）：

- **固定端点身份确认**：每个验证器只调用目标平台的"我是谁"类接口——
  GitHub `GET /user`、AWS `STS GetCallerIdentity`、Gitee `/api/v5/user`、
  GitLab `/api/v4/user`、Slack `auth.test`、Telegram `getMe`、npm `whoami`、
  HF `whoami-v2`。**不枚举**仓库/存储桶/模型/域名（OpenAI/Anthropic/Stripe 因此标
  unsupported——它们没有不枚举资源的验证端点）；不写操作；不读业务数据。
- **状态机 11 态**（INTERFACES.md §3）与映射纪律：
  200→valid；401→invalid；**403 分语义**（GitHub 配额头=rate_limited、GitLab 权限不足=
  inconclusive、AWS SigV4 拒签=invalid）；429/backoff/ratelimited→rate_limited；
  5xx→inconclusive；网络异常→network_error（绝不算 invalid）；
  无验证器→unsupported（检测能力保留）；缺配对→missing_context（不入队即落结果）。
- **SigV4**（`_sigv4_headers`）：stdlib 实现的最小 AWS4-HMAC-SHA256（GET+空载荷，
  host/x-amz-date 签名头），仅用于 STS GetCallerIdentity；`missing_context` 强制要求
  AK+SK 成对（未配对不猜测目标）。
- **防凭据外泄**：`follow_redirects=False` + `_guard_redirect` 校验最终域名；
  证据仅存 `{endpoint, http_status[, ok/error]}`——**响应体永不入库/入日志**；
  Slack/Telegram 解析 JSON 仅取 ok/error 标志。
- **队列语义**：单条/批量/自动三种入口统一走 `verification_jobs` 队列；
  worker 线程按 `max_per_minute` 限速逐个执行；每次验证**追加** `verification_results`
  历史（不覆盖）；完成后更新凭据当前 `verification_status/verified_at`。
- **自动验证策略**（`auto_enqueue_due`）：默认关闭；开启后每 tick 限量（默认 5）——
  not_requested 且有验证器→入队；valid/invalid 超 `reverify_days`→重验；
  rate_limited/network_error/error/inconclusive 超 1 小时→重试；queued/running 不重复。

### 2.7 安全设计

- **静态加密**：凭据原文、配对字段、平台 Token 以 Fernet 加密存储；
  主密钥来源优先级 `CCS_MASTER_KEY` 环境变量 > `data/master.key`（首次自动生成）；
  主密钥不入库不入 Git，备份必须连同密钥（DEPLOYMENT.md §4）。
- **脱敏**：API 与界面默认只出 `preview`（`mask_preview`：头部 2~6 字符 + `****` + 尾部 2~4）；
  原文仅 `POST /api/findings/{id}/reveal` 返回并写 reveal_access 审计；
  **界面自动化测试断言"页面 HTML 中凭据原文零出现"**。
- **导出安全**：CSV 公式注入防护（`csv_escape_cell`：值首字符 ∈ {=,+,−,@} 前加 `'`）；
  流式生成（yield_per + 生成器）避免大结果集阻塞；默认 masked=true。
- **访问保护**：默认绑定 127.0.0.1；`CCS_ACCESS_TOKEN` 开启单用户令牌
  （cookie httponly / Bearer 双通道，`/api/login` 换发）。
- **采集侧安全**：压缩包/wxapkg/APK 路径穿越段拒绝、符号链接/设备文件跳过、
  解压总量/成员数/单成员上限熔断；加密小程序包拒绝解密（合规边界）。
- **日志纪律**：日志不含凭据原文、完整上下文、平台 Token；`git grep` 提交前复查真实密钥。

---

## 3. 代码功能实现说明（逐模块）

### 3.1 基础设施层

| 模块 | 功能与关键实现 |
| --- | --- |
| `app/config.py` | pydantic-settings，前缀 `CCS_`；`resolved_db_url()` 默认 `sqlite:///data/app.db`；`static_dir` 支持容器注入；`background` 开关供测试禁用后台线程 |
| `app/db.py` | 引擎/会话工厂；SQLite 连接事件挂 PRAGMA（WAL、外键、busy_timeout、NORMAL）；`utcnow()` 全库 naive UTC；`get_session()` FastAPI 依赖 |
| `app/security.py` | §2.2 指纹、§2.7 加密/脱敏、熵、占位符判定；`_master_secret()` 主密钥两级来源与自动生成 |
| `app/settings_service.py` | 运行时设置（20 个键）：sensitive 项 Fernet 加密落 `app_settings` 表；`all_settings()` 默认遮盖敏感值只回 configured 布尔 |

### 3.2 数据模型（models.py，13 表）

`sources`（采集源定义：category/platform/collector_key/config_json）、
`tasks`（执行实例：mode/status/interval/next_run_at/last_error）、
`scan_runs`（批次：status/trigger/stats_json）、`cursors`（游标，唯一 task+key）、
`source_contents`（内容版本缓存：唯一四元组 + published 三字段 + content 截断存储 200KB）、
`credentials`（凭据实体：唯一指纹 + 加密原文/配对 + 复核状态 + 验证状态 + 首末发现）、
`occurrences`（位置：唯一 credential+location_hash + 位置元数据 + 脱敏上下文 + evidence_json）、
`review_logs`（复核与审计）、`verification_jobs`（队列）、`verification_results`（追加式历史）、
`rule_records`（规则注册表快照，enabled 开关跨重启保留）、`ignore_rules`（四类作用域）、
`app_settings`（运行时设置）、`capabilities`（能力清单：planned/implemented/offline_tested/
live_verified/blocked）。迁移：`alembic/versions/659df6833a92_baseline`，启动时
`init_db()` 先 Alembic、异常回退 `create_all`。

### 3.3 检测子系统（detection/）

- `registry.py`：`Rule` dataclass（20 字段，含预编译正则与上下文正则）；
  `load()` 校验必填字段并聚合 `file_sha`；`validate_tests()` 对每条规则跑自带正反样例
  （正例必须命中、反例必须不命中，排除 rejected_candidate）——**样例即测试即文档**。
- `engine.py`：§2.1 全部管线；输出 `Candidate`（rule_id/version/type/vendor/secret/
  confidence/行号/span/verifier_id/evidence）。资源约束常量在文件头（1MB 输入、
  20 次解码、20K 块字符等）。
- `rules/*.yaml`（4 组 35 条）：cloud（9：AWS/阿里云/腾讯云/Azure×2/GCP 服务账号）、
  devplatform（12：GitHub/GitLab/Gitee/Slack/npm/PyPI/HF/DockerHub/Telegram/Stripe×2/钉钉/飞书企微）、
  services（8：OpenAI/Anthropic/SendGrid/Mailgun/Resend/Twilio×2/OAuth×2）、
  keys_db（6：私钥块/数据库连接串/通用配置赋值/配置口令）。每条含 positives/negatives。

### 3.4 采集子系统（collectors/，10 个插件）

契约（`base.py`）：`ContentItem` 数据类（kind/platform/origin_url/repo/path/version_id/
version_kind/text/size/published 三字段/fetched_at/extra）+ `BaseCollector`
（`items()` 异步生成器、`test_connection()`、include/exclude 通配、大小上限、
`decode_text` 二进制 NUL 探测、`rate_limited` 标志、`cursor_store` 游标）+ `register` 装饰器。

| 采集器 | 要点 |
| --- | --- |
| `local_dir` | os.walk 跳过 .git/node_modules 等；mtime+size 哈希作版本；不冒充公开时间 |
| `archive` | zip/tar 内存逐成员：`_entry_safe` 拒绝绝对路径与 `..` 段；tar 跳过符号链接/设备；512MB 总量熔断；zip CRC+size 作版本 |
| `github` | 树递归（truncated 透传）+ blob base64；认证可选（设置页 Token）；限流=优雅停止；`fetch_history` 提交历史扫描（新→旧、`last_commit_scanned` 游标、提交时间=low 可信、blob 404 软跳过）；连接测试只用于采集账号 |
| `gitee` | API v5 同构实现（token 可选、限流/认证语义对齐） |
| `mediawiki` | recentchanges（rccontinue 游标）→ 批量 prop=revisions 取内容；formatversion=2 下按 **pageid** 映射（修订对象无 revid，实测踩坑）；修订时间=medium 可信公开时间；合规 UA（维基媒体拒通用 UA） |
| `generic_web` | feedparser 解析 RSS/Atom（ETag/LM 条件请求、HTML 剥离、发布时间=medium）；sitemap 解析（lastmod=low）；单 URL（内容哈希版本）；平台标识=主机名 |
| `stackoverflow` | search/advanced → questions?filter=withbody 两步；尊重 backoff 与 quota_remaining；创建时间=medium |
| `oci_registry` | 镜像引用解析（library/ 前缀、digest/tag）、匿名 Bearer token 流程、多架构清单选择（amd64 优先）、**config digest 作镜像版本**、逐层 gzip tar 解析、whiteout/opaque 按层序应用（先作用于下层再入本层文件）产出 `in_final_view` 标记、构建时间=low；层 307→CDN 需跟随重定向（验证器仍禁重定向） |
| `apk` | APK=zip：assets/res-raw/META-INF/文本后缀直接扫；classes*.dex 提取 ≥8 字符可打印串后扫；二进制 AndroidManifest 需 Androguard（未装如实跳过）；URL 下载入口监控以整包 sha256 为版本；PK 头校验 |
| `wxapkg` | 未加密容器格式解析（0xBE，条目 offset 相对正文起点）；加密包（V1MMWX）明确拒绝（合规边界）；索引/正文/条目三级越界校验 |

### 3.5 流水线与调度（pipeline.py / scheduler.py）

- `run_task(task_id, trigger)`：两级防重叠领取 → 创建 ScanRun → 合并预算配置 →
  `_build_collector`（注入游标与平台 Token）→ `_execute`（§2.4）→ 批次统计/状态落库 →
  游标持久化 → 持续任务写 `next_run_at`（抖动）。异常分级：CollectorError/未知异常 →
  批次 failed + 任务 failed + last_error；限流 → 正常停止 + rate_limited 标记。
- `_execute`：asyncio 驱动采集器；逐项做版本缓存查重、内容落库（截断 200KB）、
  检测（排除 rejected）、忽略规则匹配（`match_ignore_rules`：rule/path_glob/fingerprint_prefix/
  category 四作用域）、`ingest_candidate` 入库；每项提交事务。
- `_run_async`：事件循环探测（§2.5）。
- `scheduler.py`：`start_background`（恢复+启动心跳）、`_tick`（到期任务领取 +
  **自动验证策略调用**）、`trigger_manual_run`（执行器未启动时同步回退，测试友好）、
  `recover_interrupted`（§2.5）。

### 3.6 验证子系统（verification/）

- `base.py`：`CredentialView`（解密后的最小视图：type/secret/paired）、`Outcome`（status/
  evidence/latency_ms）、`BaseVerifier`（`missing_context` 预检、`spec()` 元数据）、
  注册表与 `verifier_for_type`；`register` 传类自动实例化（防"注册了类"契约错误）。
- `verifiers.py`：8 个验证器（§2.6）+ `_sigv4_headers`（SigV4 最小实现）。
- `worker.py`：`enqueue`（无验证器类型**立即落 unsupported 结果**并更新状态——保留检测能力）/
  `enqueue_batch` / `auto_enqueue_due`（§2.6 策略）/ `_process_job`（解密→missing_context 预检→
  `asyncio.run(verify)`→结果追加→凭据状态更新）/ `_loop`（队列线程，per-verifier 限速）/
  `http_factory`（按设置注入 proxy/timeout，**返回即客户端**——与验证器契约一致）。

### 3.7 业务服务与 API

- `services.py`：规则记录同步（enabled 状态跨重启保留）、能力清单 seed（只增不覆盖已演进状态）、
  忽略规则匹配、`ingest_candidate`（§2.2）、复核状态机（四转换+restore，全部留痕）、
  reveal（解密+审计）、`overview_stats`（分口径统计：命中/去重/位置/复核/验证分布/
  最近批次/时延 P50·P95 含样本数与口径说明）、导出行迭代与 CSV 转义。
- `api/`（9 组路由）：overview（stats+system/info）、sources（CRUD+立即运行+任务四操作+批次）、
  findings（列表多条件分页/详情/reveal/review/batch-review/verify/batch-verify）、
  verification_api（jobs/history/verifiers）、channels（能力矩阵+采集器+验证器+规则启停）、
  settings_api（GET/PUT/连接测试/三种本地导入——连接测试用**采集账号**，与发现凭据隔离）、
  discover（种子发现：一次生成多渠道任务；纯关键词不冒充代码搜索并如实提示认证限制）、
  export_api（CSV/JSON 流式导出，masked 参数默认 true）。
- `main.py`：应用工厂 + lifespan（init_db → 规则/能力同步 → 调度器+验证 worker 启动，
  `CCS_BACKGROUND=false` 可全禁）→ 可选令牌中间件 → 静态托管（`CCS_STATIC_DIR` 或
  frontend/dist）→ `/api/login`。

### 3.8 前端（frontend/）

Vue 3 `<script setup>` + Element Plus + hash 路由六页：总览（统计卡片/分布表/时延卡含样本数/最近批次）、
监控任务（来源 CRUD、六类采集器动态表单、种子发现批量生成、批次抽屉）、
发现列表（筛选/批量复核/批量验证/详情抽屉含位置·验证历史·审计/reveal 弹窗/导出按钮）、
验证中心（验证器清单/队列/追加历史）、渠道与规则（能力矩阵 + 采集器 + 规则启停开关）、
设置（采集账号/网络并发/预算/验证策略/脱敏导出/连接测试）。
`api.ts` 统一 axios 封装 + Asia/Shanghai 时间格式化 + 状态中文映射。
构建产物由后端 StaticFiles 托管（`base:'./'` 相对路径 + hash 路由免服务端路由配置）。

---

## 4. REST API 清单（/api 前缀，默认脱敏）

| 分组 | 端点 |
| --- | --- |
| 总览 | GET /overview/stats；GET /system/info |
| 来源与任务 | GET/POST /sources；PATCH/DELETE /sources/{id}；POST /sources/{id}/run；GET /tasks；POST /tasks/{id}/pause\|resume\|cancel\|retry；GET /tasks/{id}/runs |
| 发现 | GET /findings（q/type/review/verify/platform/page）；GET /findings/{id}；POST /findings/{id}/reveal；POST /findings/{id}/review；POST /findings/batch-review；POST /findings/{id}/verify；POST /findings/batch-verify |
| 验证 | GET /verification/jobs；GET /verification/history；GET /verification/verifiers |
| 渠道与规则 | GET /channels；GET /rules；PATCH /rules/{id} |
| 设置与导入 | GET/PUT /settings；POST /settings/test-connection；POST /import/directory\|git-local\|archive |
| 种子发现 | POST /discover/seed |
| 导出 | GET /export/findings.csv；GET /export/findings.json（masked 参数） |
| 系统 | POST /api/login（可选令牌） |

---

## 5. 测试与质量保障

- **71 项 pytest**：规则注册表自检（35 条正反样例）、引擎行为（配对/解码/结构化/过滤/消解/截断）、
  安全基础、10 个采集器（平台响应样例注入：happy path/限流/认证过期/穿越拒绝/解压炸弹防护）、
  流水线（去重/多位置/幂等/忽略/恢复/防重叠）、验证语义（默认关闭零验证请求、11 态映射、
  历史追加、禁重定向、SigV4 结构）、API 端到端（设置→扫描→复核→导出→验证→导入→恢复）、
  制品解析（OCI whiteout/最终视图、APK dex、wxapkg 越界/加密拒绝）、种子发现、
  自动验证策略分支。
- **界面自动化**：Playwright+Chromium 7 流程 PASS，含**"页面 HTML 中凭据原文零出现"**脱敏断言；
  截图证据 docs/evidence/。
- **真实渠道验证**：7 渠道 live 实采 + 8 验证器（GitHub valid/invalid 双例 + 6 个真实网络 invalid），
  详见 EVALUATION.md §4。
- 测试可注入性设计：采集器/验证器接受 `client_factory`/`http_factory_override`，
  平台响应用 httpx.MockTransport 注入——测试不发真实网络请求（live 验证是独立脚本）。

## 6. 部署形态

三种形态（DEPLOYMENT.md 详述，前两种实测）：Windows/Ubuntu 原生 uvicorn + 前端 dist 托管；
Docker 多阶段镜像（node 构建前端 → python 运行时，启动自动迁移，数据卷 /app/data）；
数据库 SQLite(WAL) 默认、PostgreSQL 实测可切换（连接串 + 同一迁移）。

## 7. 术语表

**凭据实体/出现位置**（§2.2）、**指纹/location_hash**（§2.2）、**版本缓存**（§2.4）、
**游标**（§2.4）、**最小验证**（§2.6）、**published_confidence**（§2.3）、
**whiteout/opaque**（容器层删除标记，§3.4 oci_registry）、**in_final_view**（当前容器视图可见标记，
对照"历史层残留"）、**push protection bypass**（GitHub 对格式逼真合成凭据的官方豁免通道，
时延实验使用，reason=used_in_tests）。
