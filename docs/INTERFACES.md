# 接口契约（INTERFACES）

状态：阶段 0 基线。字段变更需同步本文件与迁移脚本。

## 1. 核心实体（models.py）

| 实体 | 关键字段 | 说明 |
| --- | --- | --- |
| Source 采集源 | name, category, platform, collector_key, config_json(seeds/include/exclude/budget/schedule), enabled | 渠道接入定义 |
| Task 监控任务 | source_id, mode(manual/continuous), status, interval_sec, next_run_at, last_error | 每来源一个执行实例 |
| ScanRun 执行批次 | task_id, status, trigger, stats_json, started/finished_at | 每次执行一条 |
| Cursor 采集游标 | task_id, cursor_key, cursor_value, updated_at | 分页/时间位点，唯一(task_id,cursor_key) |
| SourceContent 来源内容 | source_id, run_id, kind, platform, origin_url, repo, path, version_id, content_hash, content(≤上限), content_truncated, size, published_at, published_source, published_confidence, source_updated_at, fetched_at, detection_status | 版本缓存唯一(source_id,version_id,path,content_hash) |
| Credential 凭据实体 | fingerprint(唯一,HMAC), type, vendor, rule_id, rule_version, confidence, secret_encrypted, paired_encrypted, preview, review_status, verification_status, verified_at, first_seen_at, last_seen_at | 去重后的"同一凭据" |
| Occurrence 出现位置 | credential_id, content_id, category, platform, origin_url, repo, path, line_start, version_id, version_kind, context_masked, content_hash, run_id, detected_at, first_seen_at, last_seen_at, location_hash(唯一), evidence_json | "同一次出现"；location_hash=sha256(category|platform|origin_url|path|version_id|line|content_hash) |
| ReviewLog 复核/审计 | credential_id, action(confirm/false_positive/ignore/restore/reveal_access), note, actor, created_at | 人工操作全部留痕 |
| VerificationJob | credential_id, verifier_id, requested_by(single/batch/auto), status(queued/running/finished/cancelled) | 验证队列 |
| VerificationResult 验证历史 | job_id, credential_id, verifier_id, verifier_version, status, evidence_json(非敏感), latency_ms | 每次验证追加，不覆盖 |
| RuleRecord 规则 | id(稳定字符串主键), title, type, vendor, version, license, enabled, builtin, file_sha | 启动时从 YAML 同步 |
| IgnoreRule 忽略规则 | scope_type(rule/path_glob/fingerprint_prefix/category), scope_value, reason, enabled | 命中=标记 ignored，不删除 |
| AppSetting | key(主键), value_json, sensitive, updated_at | 平台Token等 sensitive=true 加密 |
| Capability 能力清单 | id(kind:key), kind(collector/verifier/channel/rule), status(planned/implemented/offline_tested/live_verified), meta_json | 界面"渠道与规则"页数据源 |

## 2. 时间字段语义（全 UTC）

- `source_published_at`：能证明的公开时间；必须带 published_source（依据）与
  published_confidence(none/low/medium/high)。无证据 → NULL，界面显示"未知"。
  Git 提交时间/文件 mtime/首次抓取时间不得冒充公开时间。
- `fetched_at`：抓取时间；`detected_at`：本次检测时间；
- `first_seen_at/last_seen_at`：系统视角；`verified_at`：验证时间；
- commit_authored_at 等来源时间存 evidence_json / content 元数据，单独展示。

## 3. 状态模型

- Task.status: pending → running → (paused | done | failed | cancelled)；running 可取消。
- ScanRun.status: running → completed | failed | cancelled | interrupted（重启恢复时标记）。
- Review: pending → confirmed | false_positive | ignored →（restore→pending）；全部留痕。
- Verification（凭据当前状态 + 每次历史）:
  not_requested / queued / running / valid / invalid / inconclusive / missing_context /
  unsupported / rate_limited / network_error / error。
  规则：401/403 不一律 invalid（区分认证失败与权限不足）；限流/网络故障/服务不可用不算 invalid；
  valid 需要充分证据；格式校验通过 ≠ 在线有效。

## 4. 插件契约

### 4.1 Collector 采集器

```python
@dataclass
class ContentItem:
    kind: str                 # file / page / blob / layer_entry / apk_entry ...
    platform: str             # github / gitee / mediawiki / weibo / ...
    origin_url: str | None    # 原始可访问 URL
    repo: str | None          # 仓库/账号/空间标识
    path: str                 # 平台内路径
    version_id: str           # commit sha / tag / digest / revision / 页面版本…
    version_kind: str         # commit/digest/revision/tag/app_version/none
    text: str | None          # 文本内容（二进制由采集器决定是否抽取文本）
    size: int
    published_at: datetime | None; published_source: str; published_confidence: str
    source_updated_at: datetime | None
    fetched_at: datetime
    extra: dict               # 渠道特有元数据

class BaseCollector:
    key: str; category: str; platform: str; version: str
    def __init__(self, config: dict, settings_svc): ...
    async def items(self) -> AsyncIterator[ContentItem]: ...   # 增量依据 config/cursors
    def test_connection(self) -> dict: ...                     # 用设置页配置的采集账号测试
```

约束：实现者不写库、不做检测；必须遵守预算（max_items/max_bytes/max_seconds）与限流
（429/403 + Retry-After → 结束本轮并记录 rate_limited）；认证信息只从 settings_svc 读取。

### 4.2 检测规则（detection/rules/*.yaml → RuleRecord）

```yaml
id: aws-access-key-id            # 稳定 ID，不改名
title: AWS Access Key ID
type: aws_access_key_id          # 凭据类型（SUPPORTED_CREDENTIALS.md 维护）
vendor: aws
version: 1
license: MIT
patterns: ['(?<![A-Z0-9])(AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])']
secret_group: 0
min_length: 20; max_length: 20
min_entropy: 3.0                 # 可选，对捕获值计算香农熵
required_context: []             # 任一命中即可；搜索范围=命中行±context_window 行
forbidden_context: ['EXAMPLE', 'YOUR_', 'xxxx']   # 命中即丢弃（占位符）
known_examples: []               # 已知文档示例值，直接丢弃
pairing: {with: aws-secret-access-key, max_line_distance: 5, boost: 10}
confidence: 85                   # 基础置信度；配对成功 +boost，仅前缀命中 -10
verifier: github_pat             # 关联验证器 ID，可为 null
tests: {positives: [...], negatives: [...]}       # 注册表自检 + pytest 共用
```

引擎组合：前缀/正则 → 占位符/熵过滤 → 上下文（变量名/服务域名）→ 格式感知
（.env/YAML/JSON/INI 键值、连接 URL、服务账号 JSON）→ 有边界 Base64 解码（深度≤2）
→ AK/SK 等配对（同文件、行距≤阈值）→ 置信度分级（high≥80 / medium≥50 / low）。
高熵字符串本身不构成凭据；弱特征（密码/数据库口令）必须依赖上下文。

### 4.3 Verifier 验证器

```python
class BaseVerifier:
    id: str; version: str; supported_types: list[str]; required_fields: list[str]
    endpoint_hint: str            # 固定服务端点说明；禁止把采集内容当目标
    def missing_context(self, cred) -> str | None: ...   # 缺字段返回原因
    async def verify(self, cred, settings_svc, http_factory) -> Outcome:
        # Outcome(status, evidence: dict[非敏感], latency_ms)
```

硬性要求：只发判断认证状态所需的最小请求；`follow_redirects=False` 且校验最终域名；
不读业务数据、不枚举资源、不写操作；超时/重试/限流策略自声明；
无满足要求的验证方式 → 不实现验证器，Capability 标 unsupported（保留检测）。

## 5. REST API（前缀 /api，JSON）

| 方法/路径 | 说明 |
| --- | --- |
| GET /overview/stats | 总览统计（渠道/类型/状态/时延分布，含样本数与口径） |
| GET/POST /sources, PATCH/DELETE /sources/{id} | 来源 CRUD（含 seeds、预算、调度配置） |
| POST /sources/{id}/run | 立即触发一次扫描 |
| GET /tasks, POST /tasks/{id}/pause\|resume\|cancel\|retry, GET /tasks/{id}/runs | 任务管理 |
| GET /findings?q&type&review&verify&category&page | 凭据列表（默认脱敏） |
| GET /findings/{id} | 详情：全部出现位置+上下文（脱敏）+证据 |
| POST /findings/{id}/reveal | 显式查看原文（写审计） |
| POST /findings/{id}/review {action,note} | 人工复核 |
| POST /findings/batch-review {ids, action, note} | 批量复核 |
| POST /findings/{id}/verify；POST /findings/batch-verify {ids} | 提交验证 |
| GET /verification/jobs?status、GET /verification/history?credential_id | 队列与历史 |
| GET /channels | 渠道/采集器/验证器能力矩阵 |
| GET /rules?enabled, PATCH /rules/{id} {enabled} | 规则管理 |
| GET/PUT /settings, POST /settings/test-connection {target} | 设置；连接测试用采集账号（绝不用发现凭据） |
| GET /export/findings.csv\|json（带筛选+masked 参数） | 流式导出；CSV 防公式注入 |
| POST /import/archive（上传 zip/tar）、POST /import/directory {path}、POST /import/git {repo} | 本地导入分析入口（不虚增渠道类别） |
| GET /system/info | 版本、数据库、调度器状态 |

响应默认脱敏：secret → preview（如 `ghp_4a9C****JkL`）；原文仅 reveal 返回；
导出默认 masked=true，显式传 masked=false 才输出原文。

## 6. ContentItem 时间字段与平台能力记录

各采集器必须在 extra 中如实记录可得的时间信息（如 GitHub pushed_at 属于仓库而非文件，
published_confidence=none）；平台限制（索引延迟、结果上限）登记在 Capability.meta_json 与
SUPPORTED_CHANNELS.md，不得在统计中冒充发现延迟。
