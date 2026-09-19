# 架构设计（ARCHITECTURE）

状态：阶段 0 基线。重大变更必须在此记录理由与迁移影响。

## 1. 总体形态

模块化单体，单机可持续运行，可选 Docker Compose。不做微服务、不引入 Redis/K8s。

```
                    ┌─────────────────────────────────────────────┐
                    │              FastAPI 应用 (main.py)          │
                    │  REST API (/api/*)  +  静态托管 frontend/dist │
                    └───────┬──────────────────────┬──────────────┘
                            │                      │
        ┌───────────────────▼───────┐   ┌──────────▼──────────────┐
        │  调度器 scheduler.py       │   │  services.py / api/*    │
        │  APScheduler 心跳 + DB声明 │   │  统计/复核/导出/设置      │
        └───────┬───────────────────┘   └──────────┬──────────────┘
                │ 线程池（可配置 worker 数）          │
        ┌───────▼──────────────────────────────────▼──────────────┐
        │                      pipeline.py                         │
        │  Collector 插件 → ContentItem → detection.engine → 入库   │
        └───────┬────────────────────────┬────────────────────────┘
                │                        │
   ┌────────────▼──────────┐   ┌─────────▼─────────────────────┐
   │ collectors/ 插件       │   │ verification/ 插件+队列（独立） │
   │ local_dir/archive/     │   │ 默认关闭；最小认证语义          │
   │ github (+后续渠道)      │   └───────────────────────────────┘
   └────────────────────────┘
                │
   ┌────────────▼───────────────────────────────┐
   │ SQLAlchemy 2 ORM → SQLite(WAL)/PostgreSQL  │
   │ 凭据原文/平台Token Fernet 加密（主密钥外部化）│
   └────────────────────────────────────────────┘
```

## 2. 关键技术决策（ADR 摘要）

| # | 决策 | 理由 | 迁移影响 |
| --- | --- | --- | --- |
| D1 | 自研检测引擎为主引擎（规则 YAML 注册表），不以 Gitleaks/TruffleHog 为内置主引擎 | 需要统一结果模型（配对/上下文/置信度/多位置）与严格的"禁用在线验证"边界；Gitleaks 规则格式可作为后续导入适配器 | 如需引入 gitleaks 作为补充离线引擎，通过 detection/adapters 增加，不改变数据模型 |
| D2 | 数据库同步 SQLAlchemy；采集用 httpx.AsyncClient，在独立 worker 线程内以 asyncio.run 驱动 | SQLite + 同步 ORM 最稳；异步只集中在网络 I/O，避免 aiosqlite 全链路复杂化 | 换 PostgreSQL 仅改连接串 |
| D3 | 调度 = APScheduler 心跳 tick + 数据库任务声明（UPDATE claim） | 任务/游标/结果全部持久化，重启可恢复；APScheduler 只负责按时触发 tick，不承载任务状态 | 无 |
| D4 | 凭据指纹 = HMAC-SHA256(主密钥派生 pepper, 类型+"\0"+规范化值) | 稳定、不可对外反推，低熵密码不暴露普通哈希作公开标识 | pepper 变化会导致历史指纹失效——文档写明主密钥依赖 |
| D5 | 敏感字段（凭据原文、配对字段、平台 Token）Fernet 加密存储 | 主密钥来自 CCS_MASTER_KEY 环境变量或 data/master.key（自动生成，0600，不入库） | 备份必须含主密钥（DEPLOYMENT.md） |
| D6 | Web 单用户：默认绑定 127.0.0.1；可选 CCS_ACCESS_TOKEN 开启简单口令（cookie 会话） | 不建多人权限体系，但远程部署需基础访问保护 | 无 |
| D7 | 验证模块完全独立：验证器仅声明固定服务端点；默认 auto_verify=false | 采集到的一切地址不得自动成为验证目标 | 无 |
| D8 | 资源限制内建：内容大小上限、正则输入截断、解包总量/比率限制、路径穿越拒绝、并发/速率可配置 | 防解压炸弹、防灾难回溯输入放大、控内存 | 无 |

## 3. 数据流

1. **任务创建**：用户在界面创建来源（seed：仓库地址/组织/关键词/URL/目录路径）→
   `sources` + 自动生成 `tasks`（手动模式立即触发，持续模式按 interval_sec 调度）。
2. **执行**：scheduler tick 发现到期任务 → 线程池领取（run_token 声明，防重叠）→
   `scan_runs` 记录批次 → collector 按 task 配置拉取 ContentItem（含版本号/时间信息）。
3. **增量**：`(source_id, version_id, path, content_hash)` 唯一 → 已见内容直接跳过；
   游标 `cursors` 记录分页/时间位点；条件请求/版本缓存减少下载。
4. **检测**：engine 对每个内容项跑规则 → 候选（含置信度、证据、配对）→ 忽略规则过滤
   （标记而非删除）→ 入库。
5. **入库去重**：凭据按指纹 get_or_create；位置按 location_hash get_or_create；
   同凭据多位置关联；重复扫描仅更新 last_seen_at。
6. **复核/验证**：界面人工复核写 review_logs；验证请求进入 verification_jobs 队列，
   worker 按 verifier 插件执行，结果追加 verification_results。
7. **展示/导出**：API 默认脱敏；reveal 需显式 POST 并审计；导出 CSV/JSON 流式输出。

## 4. 模块边界

- `collectors/*` 只产出 `ContentItem`（平台元数据+内容+版本+可得的时间信息），不接触数据库写入逻辑。
- `detection/*` 只消费文本，产出候选；不知道来源是什么平台。
- `pipeline.py` 是唯一同时理解采集与检测结果的组装层。
- `verification/*` 不 import collectors/detection 的任何运行时逻辑，只通过凭据实体接口。
- `api/*` 只调 services 层，不直接拼 ORM 查询（导出除外，走专用流式查询）。

## 5. 并发与资源模型

- 线程池大小 `CCS_WORKERS`（默认 2）；每个任务运行设预算：max_items / max_bytes /
  max_seconds / max_file_size（source.config_json 配置，默认值在 settings）。
- 速率：per-host 最小间隔 + 429/403 时读 Retry-After，超限记 rate_limited 结束本轮。
- 稳定轮询加 ±10% 抖动；同一任务不允许并行运行（DB 声明保证）。
- 解包目录 `data/tmp/` 有总量配额与过期清理；`data/cache/` 存原始内容副本（可配保留天数）。

## 6. 时区与时间

- DB 全部存 UTC（SQLAlchemy DateTime(timezone=False) 约定 UTC，写入前统一 `now_utc()`）。
- 展示时区为设置项 display_timezone，默认 Asia/Shanghai（zoneinfo，Windows 需 tzdata 包）。

## 7. 安全基线

- 本地默认 127.0.0.1；远程部署走反向代理或开启 CCS_ACCESS_TOKEN。
- 凭据原文/平台 Token Fernet 加密；reveal 接口留审计（review_logs action=reveal_access）。
- 日志不打印凭据原文、完整上下文、平台 Token。
- CSV 导出防公式注入（=+-@ 前缀转义）；大导出流式响应。
