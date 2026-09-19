# 技术说明书（TECHNICAL_MANUAL）

> 面向赛题评审与后续维护者：关键技术原理、模块职责、代码实现说明。
> 配套阅读：ARCHITECTURE.md（决策）、INTERFACES.md（契约）、SUPPORTED_*.md（能力）。

## 1. 系统结构

模块化单体：`backend/app/`（FastAPI）+ `frontend/`（Vue3，构建产物由后端托管）+ SQLite(WAL)。
七个子系统通过接口解耦：采集（collectors）→ 检测（detection）→ 存储（models/db）→
复核与统计（services）→ 验证（verification）→ 调度（scheduler）→ 界面（api/views）。

## 2. 关键技术原理

### 2.1 检测引擎（detection/engine.py）

单遍扫描组合多信号，避免单一正则的高误报：

1. **正则层**：规则 YAML 中的模式在全文 finditer，捕获组提取值；
2. **过滤层**（按序）：长度窗 → 占位符（通用词表+重复字符+已知文档示例）→
   规则级禁值（如连接串口令 `password`）→ 香农熵下限 →
   **禁上下文**（如 EXAMPLE）→ **必上下文**（命中行±N 行内需出现变量名/服务域名）；
3. **格式感知层**：PEM 块（BEGIN→END 整块捕获，判定加密状态，OpenSSH 加密性不可判标 unknown）；
   GCP 服务账号 JSON（结构化解析，提取配对字段 client_email/project_id）；
4. **有边界解码**：≥48 字符 Base64 串解码（≤20 次/文件、解码后可打印率≥85%、深度≤1）后重扫；
5. **配对层**：`pairing.with` 规则的候选在行距≤5 内互认，双侧加成（如 AWS SK 60→80）；
6. **重叠消解**：同值且区间重叠的候选按置信度保留一条（消除多规则重复计数）；
7. **置信度**：规则基线 −过滤降权 +配对加成，映射 high(≥80)/medium(≥50)/low。

资源约束：单文件输入截断 1MB（截断标记入证据）；解码次数/长度上限；正则全部预编译。

### 2.2 凭据实体与位置分离（models.py, services.py）

- **凭据实体**：指纹 = HMAC-SHA256(主密钥派生 pepper, 类型+"\0"+值+配对字段)。
  同值同类型归并；不同类型、不同配对（不同账号）不合并。指纹不可反推原文
  （低熵密码不以普通哈希作公开标识）。
- **出现位置**：location_hash = SHA256(平台|URL|仓库|路径|版本|行|内容哈希)。
  唯一约束 (credential_id, location_hash) → 同一位置重复扫描只更新 last_seen_at，
  不新建事件；同凭据跨文件/跨仓库自然形成多位置关联。
- 复核（pending/confirmed/false_positive/ignored）、置信度、验证状态三个维度独立，
  任何操作留 ReviewLog 痕迹（含 reveal 访问审计）。

### 2.3 时间模型

七类时间字段分开存（UTC）：source_published_at（必须带依据+置信度）、
source_updated_at、fetched_at、detected_at、first/last_seen_at、verified_at。
采集器给不出可靠公开时间时（GitHub 文件、本地文件）一律 confidence=none →
界面显示"未知"、不参与时延统计。时延分布仅统计 medium/high 置信样本并展示样本数。

### 2.4 采集器插件（collectors/）

`ContentItem` 统一元数据（版本标识、公开时间口径、大小），采集器只产出不落库。
预算（条数/字节/时长）与限流（429/403+Retry-After 或剩余配额=0 → 置 rate_limited 优雅收尾）
在流水线逐项执行。安全：压缩包内存逐成员读取拒绝路径穿越成员、跳过符号链接、
512MB 总量熔断；二进制 NUL 探测跳过。

### 2.5 持久化调度（scheduler.py + pipeline.py）

APScheduler 只做心跳 tick（默认 20s，可配）；任务状态全部在数据库：
- 领取语义：`run_task` 检查状态后置 running → 天然防重叠；
- 抖动：next_run_at = now + interval × U(0.9, 1.1)；
- 恢复：启动时 running 批次 → interrupted，任务 → pending 等待重排；
- 幂等：内容版本缓存 (source, version_id, path, content_hash) 唯一；
- 采集协程在 worker 线程的事件循环中执行（API 上下文内则另起线程循环，
  见 pipeline._run_async），数据库同步会话按线程隔离。

### 2.6 验证模块（verification/）

与采集/检测零耦合。状态机 11 态（INTERFACES.md §3）。关键实现约束：
- 只允许固定端点（如 GitHub `GET /user`）；`follow_redirects=False` 且校验最终域名；
- 401→invalid；403+配额耗尽→rate_limited；其余 4xx/5xx→inconclusive；
  网络异常→network_error；无验证器→unsupported（检测能力保留）；
- 证据仅存端点与状态码，不落响应体；每次验证追加 VerificationResult 历史；
- 自动验证开关默认关，开启后也仅作用于有验证器的类型。

### 2.7 安全基础设施（security.py, main.py）

- 敏感值（凭据原文、配对、平台 Token）Fernet 加密；主密钥外部化（env > data/master.key）；
- API 默认脱敏：secret 只出 preview（head+****+tail）；原文仅 POST reveal 且写审计；
- 导出 CSV 公式注入防护（=+-@ 前缀加 `'`）；流式导出避免大结果集阻塞；
- 可选 `CCS_ACCESS_TOKEN` 单用户令牌（cookie/Bearer），本地默认绑定 127.0.0.1。

## 3. 模块职责速查

| 模块 | 职责 | 关键类/函数 |
| --- | --- | --- |
| app/config.py | 环境配置（CCS_*） | get_settings |
| app/db.py | 引擎/WAL/UTC 会话 | engine, SessionLocal, get_session |
| app/models.py | 13 张表 ORM | Base 及全部实体 |
| app/security.py | 加密/指纹/脱敏/占位符 | encrypt_text, credential_fingerprint, mask_preview |
| app/detection/registry.py | 规则加载与自检 | RuleRegistry.load/validate_tests |
| app/detection/engine.py | 检测管线 | DetectionEngine.scan |
| app/detection/rules/*.yaml | 35 条规则+正反例 | — |
| app/collectors/base.py | 采集契约/注册表 | ContentItem, BaseCollector, register |
| app/collectors/{local_dir,archive,github}.py | 三个采集器 | 各 .items() |
| app/pipeline.py | 扫描编排/预算/入库 | run_task, _execute |
| app/scheduler.py | 心跳/领取/恢复 | start_background, recover_interrupted |
| app/services.py | 去重入库/复核/统计/导出 | ingest_candidate, overview_stats, iter_export_rows |
| app/verification/{base,verifiers,worker}.py | 验证契约/实现/队列 | enqueue, _process_job |
| app/api/* | REST 路由 | api_router |
| app/main.py | 应用工厂/生命周期 | create_app, init_db |

## 4. 扩展指南（赛题评价维度）

- **新增凭据规则**：在 `detection/rules/` 任一 YAML 追加一条（含 positives/negatives），
  重启后自动同步 RuleRecord 并出现在【渠道与规则】页；跑 `validate_tests()` 即回归。
- **新增渠道**：实现 `BaseCollector`（key/category/platform/items/test_connection）→
  `register` 装饰 → 界面即可创建来源；限流与预算由框架统一执行。
- **新增验证器**：实现 `BaseVerifier`（固定端点+状态映射）→ `register` 实例；
  无合规最小验证的类型不要实现，标 unsupported。
