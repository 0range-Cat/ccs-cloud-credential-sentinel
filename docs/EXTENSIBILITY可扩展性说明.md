# 平台可扩展性与新监控渠道扩展说明

> 回应赛题评价方式第 3 项："平台的可扩展性，新监控渠道的易扩展性"。
> 本文档说明扩展点的**设计**、新增一个渠道的**完整步骤（含真实代码）**，
> 以及"这套机制到底好不好扩展"的**实证数据**。
> 配套：完整契约见 [INTERFACES.md](INTERFACES.md) §4；逐模块实现见 [TECHNICAL_MANUAL.md](TECHNICAL_MANUAL.md) §3。

---

## 一、设计结论（一段话）

系统是**插件化单体**：新增一个监控渠道 = 实现一个 Python 类（约 150~330 行）+ 一个 mock 测试文件；
预算控制、限流优雅停止、游标持久化、内容版本缓存、凭据去重、多位置关联、界面展示、
种子发现、统计口径**全部由框架自动承担**，采集器作者只写"如何从平台拉内容"。
凭据规则（YAML）与验证器（Python 类）是另外两个对称的扩展点，同样不触碰框架代码。

## 二、三个扩展点

### 2.1 渠道采集器（Collector）

**契约**（`backend/app/collectors/base.py`）：

```python
@dataclass
class ContentItem:            # 采集器唯一的输出类型
    kind: str                 # file / page / blob / layer_entry / apk_entry / wxapkg_entry ...
    platform: str             # 平台标识（统计与位置哈希的维度）
    origin_url: str | None    # 原始可访问 URL（可空，如本地内容）
    repo: str | None          # 仓库/账号/站点标识
    path: str                 # 平台内路径
    version_id: str           # 版本标识：commit/blob sha、digest、修订号、整包哈希…
    version_kind: str         # commit/digest/revision/tag/app_version/blob/none
    text: str | None          # 文本内容（二进制自行决定是否抽取文本）
    size: int
    published_at: datetime | None   # 能证明的公开时间（证明不了就 None！）
    published_source: str           # 依据（如 mediawiki_revision_timestamp）
    published_confidence: str       # none/low/medium/high——决定是否参与时延统计
    fetched_at: datetime
    extra: dict               # 渠道特有元数据（whiteout 标记、配对信息…）

class BaseCollector:
    key: str; category: str; platform: str; title: str; version: str
    rate_limited: bool = False          # 触发平台限流时置 True（框架据此优雅停止）
    def __init__(self, config: dict, cursor_store: dict | None = None): ...
    def save_cursor(self, key, value)   # 游标写回，框架持久化到 cursors 表
    async def items(self) -> AsyncIterator[ContentItem]   # 核心方法：产出内容项
    def test_connection(self) -> dict   # 设置页"连接测试"（只用采集账号）
    # 免费获得：include/exclude 通配、单文件大小上限、decode_text 二进制探测、
    #           _path_allowed 过滤、_max_file_bytes 预算
```

**注册即生效**：类上加 `@register` 装饰器并在 `base.py` 底部 import 一行，
随后**零前端改动**——新建来源表单、能力矩阵、种子发现自动出现该渠道。

**实现者必须遵守的三条纪律**（框架无法替你保证的）：
1. 只产出 `ContentItem`，不写库、不做检测（职责分离保证任何渠道的行为可测试）；
2. 公开时间给不出证据就置 None/none——**不得用抓取时间或提交时间冒充公开时间**
   （git 提交时间若使用，必须 `published_confidence="low"` 并写明 source）；
3. 平台限流时置 `rate_limited=True` 并停止产出（不是抛异常）——单渠道失败不拖垮其他渠道。

**完整真实示例**（`collectors/gitee.py` 精简，约 150 行，已 live_verified）：

```python
@register
class GiteeCollector(BaseCollector):
    key = "gitee"; category = "code_hosting"; platform = "gitee"; title = "Gitee 仓库扫描"

    def __init__(self, config, client_factory=None, token="", cursor_store=None):
        super().__init__(config, cursor_store)      # 游标由流水线注入
        self._client_factory = client_factory       # 测试注入 MockTransport 的接缝
        self._token = token or ""                   # 流水线从设置页读出并传入

    async def items(self):
        repo = parse_gitee_repo(self.config.get("repo"))
        max_bytes = self._max_file_bytes()          # 框架预算
        async with self._make_client() as client:
            info = await self._get(client, f"/repos/{repo}")
            tree = await self._get(client, f"/repos/{repo}/git/trees/{branch}?recursive=1")
            for entry in tree.get("tree", []):
                if entry["type"] != "blob" or not self._path_allowed(entry["path"]):
                    continue
                blob = await self._get(client, f"/repos/{repo}/git/blobs/{entry['sha']}")
                text = self.decode_text(base64.b64decode(blob["content"]))
                if text is None:
                    continue
                yield ContentItem(kind="blob", platform=self.platform,
                    origin_url=f"https://gitee.com/{repo}/blob/{branch}/{entry['path']}",
                    repo=repo, path=entry["path"], version_id=entry["sha"],
                    version_kind="blob", text=text, size=entry["size"],
                    published_at=None, published_source="gitee_api",
                    published_confidence="none", extra={"branch": branch})
                if self.rate_limited:               # 平台限流 → 优雅停止
                    return
```

### 2.2 凭据规则（Rule，YAML）

新增一种凭据类型 = 在 `detection/rules/*.yaml` 追加一条：

```yaml
- id: example-provider-key            # 稳定 ID，永不改名
  title: 示例服务 API Key
  type: example_provider_key          # 凭据类型（SUPPORT_MATRIX §三 维护）
  vendor: example
  version: 1
  license: MIT
  confidence: 85                      # 格式自证强度决定基线
  patterns:
    - '(?<![A-Za-z0-9])(ex_[A-Za-z0-9]{32})(?![A-Za-z0-9])'
  secret_group: 1
  min_length: 35
  required_context: ['(?i)example']   # 弱特征必须配上下文
  forbidden_context: ['EXAMPLE', 'your_']
  min_entropy: 3.0
  verifier: null                      # 有最小验证端点再关联
  tests:                              # 正反样例=回归测试=文档
    positives: ['api_key = ex_4f8a2b6c9d1e3f7a5b8c0d2e4f6a8b1c']
    negatives: ['api_key = ex_your_token_here']
```

保存即生效：启动时同步进 `rule_records` 表，【渠道与规则】页可直接启停；
`validate_tests()` 自动回归（正例未命中或反例误报会显式报错）。
规则引擎侧免费获得：占位符过滤、熵窗、上下文窗口、配对、重叠消解、截断保护。

### 2.3 验证器（Verifier）

```python
@register
class ExampleVerifier(BaseVerifier):
    id = "example-whoami"
    title = "示例服务（GET /whoami 身份确认）"
    version = "1.0.0"
    supported_types = ["example_provider_key"]   # 与规则 type 对应
    required_fields = ["secret"]
    endpoint_hint = "https://api.example.com/whoami"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:      # follow_redirects=False 已内置
                resp = await client.get("https://api.example.com/whoami",
                                        headers={"Authorization": f"Bearer {cred.secret}"})
        except httpx.HTTPError:
            return Outcome("network_error", {"endpoint": self.endpoint_hint})
        if resp.url.host != "api.example.com":        # 防重定向外泄凭据
            return Outcome("error", {"reason": "unexpected redirect"})
        # 200=valid / 401=invalid / 429=rate_limited / 其余=inconclusive
        ...
```

合规硬约束（代码评审对照 INTERFACES.md §4.3 逐条检查）：固定端点身份确认；
不枚举资源（模型/仓库/桶/域名清单类接口一律不允许——OpenAI/Anthropic/Stripe 因此判
unsupported）；不读业务数据；无写操作；限流/权限不足≠invalid；响应体不入证据。
**没有合规端点就不实现验证器**，能力矩阵标 unsupported，检测能力保留。

### 2.4 数据库与前端：扩展零迁移

新增渠道/规则/验证器**不需要数据库迁移**：渠道身份存于 `sources.collector_key` 字符串、
规则是数据行、验证器是进程内对象；`capabilities` 表按 seed 自动补行。
只有新增**实体字段**才需要 Alembic 迁移（阶段1至今仅 1 个基线迁移）。

## 三、新增一个渠道的完整步骤（清单式）

1. 调研：平台公开接口、认证、速率限制、增量游标、公开时间可得性（写入 `docs/RESEARCH.md`）；
2. 实现 `collectors/<key>.py`（§2.1 契约 + 三条纪律）；
3. `base.py` 注册 import（1 行）；
4. mock 测试：`tests/test_collectors_*.py` 用 httpx.MockTransport 注入平台响应
   （happy path / 限流 403+配额头 / 401 / 异常格式 / 边界）；
5. `CHANNEL_CAPABILITIES`（services.py）加能力行，状态先 offline_tested；
6. 真实渠道跑 `scripts/live_check.py` 式两轮验证（采集+增量），通过后提升 live_verified；
7. 更新 `SUPPORT_MATRIX.md` / `SUPPORTED_CHANNELS.md` / `DELIVERABLES.md` 数字；
8. 提交（采集器 + 测试 + 文档各自成小提交）。

前端、数据库、导出、复核、验证入口、统计**全程零改动**。

## 四、扩展性实证（不是承诺，是已发生的事实）

2026-09-19 单个开发日内，在同一框架上完成并全部通过测试与真实渠道验收：

| 新增扩展 | 代码量 | 验收结果 |
| --- | --- | --- |
| Gitee 采集器 | ~160 行 | live_verified（实采+限流停止语义） |
| MediaWiki 采集器 | ~200 行 | live_verified（rccontinue 游标增量） |
| 通用 RSS/Sitemap/URL 采集器 | ~260 行 | live_verified（304 条件请求） |
| Stack Overflow 采集器 | ~140 行 | live_verified（配额语义） |
| OCI 容器镜像采集器（含 whiteout 语义） | ~330 行 | live_verified（alpine 实采 40 条层文件） |
| APK 采集器（含 dex 字符串提取） | ~180 行 | live_verified（F-Droid 实采 25 条） |
| wxapkg 采集器（合规拒绝路径） | ~190 行 | offline_tested |
| GitHub 提交历史扫描 + 游标 | ~90 行 | live_verified（53 条历史内容实采） |
| 游标基础设施（一次投入，全渠道复用） | ~60 行 | 后续渠道免实现 |
| 验证器 ×8 | 每个 40~90 行 | 6 个真实网络 invalid 实证 |

期间发现的框架级缺陷共 5 个（验证器注册语义、`rate_limited` 默认值、任务领取语义冲突、
事件循环嵌套、MediaWiki UA 策略），全部以测试回归锁定——扩展过程中框架在被持续加固，
这正是插件化架构的价值：**每个新渠道都在验证并强化同一套机制**。

规则侧实证：43 条规则全部由同一 YAML 契约承载，新增规则零 Python 代码。

## 五、边界与已知约束（如实）

- 采集器作者需自行处理平台鉴权细节与分页（框架提供游标但不理解平台语义）；
- 重度二进制格式（APK 二进制 manifest）依赖可选原生库（Androguard），未装时如实跳过；
- 需要登录态的渠道（微博类）在"不绕过访问控制"前提下可能无法接入——这是合规约束
  而非架构约束，能力矩阵将以 blocked 状态呈现；
- 正则规则对"强上下文弱格式"类凭据（如普通口令）天然低置信度——设计如此，
  由人工复核而非算法冒险兜底。
