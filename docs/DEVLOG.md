# 开发记录（DEVLOG）— 只记真实执行结果

约定：每条记录包含日期、任务ID、实际做的事、实际执行的命令与结果、遇到的问题。
不得写入"计划做"的事；不得记录真实密钥。

## 2026-09-19（会话1：主控）

### T0.1 环境检查 — done

实际执行与结果：

- 工作目录 `G:\2026\我的项目\云凭据检验`，初始为空目录。
- `git --version` → git version 2.53.0.windows.2；user.name=0range-Cat，user.email=2955456920@qq.com（已配置，可直接提交）。
- `python --version` → Python 3.13.9（D:\work\python.exe），满足 3.11+ 要求。
- `node --version` → v24.16.0；`npm --version` → 11.13.0。
- `docker --version` → Docker version 29.7.2。
- 网络：pypi 200、npm registry 200；`api.github.com` → 403（开发网络环境受限）。
  **影响**：GitHub 真实接入验收无法在本机网络完成，采集器以平台响应样例注入方式离线测试；
  真实验收步骤写入 docs/DEMO.md 由用户在其环境执行。

### T0.3 文档体系与 Git 规范 — done

- 建立 README/AGENTS/docs 全套文档（INDEX/REQUIREMENTS/RESEARCH/ARCHITECTURE/INTERFACES/TODO/
  DEVLOG/DEPLOYMENT/SUPPORTED_CHANNELS/SUPPORTED_CREDENTIALS/EVALUATION/HANDOFF/TECHNICAL_MANUAL/
  MASTER_PROMPT/DEMO），.gitignore 排除 data/、日志、.env、*.db、node_modules 等。
- 目录结构初始化：backend/（app+tests+alembic）、frontend/、docs/、examples/、scripts/。

### T0.2 调研 — done

- 子智能体1（开源工具）：产出 docs/research/draft-tools.md。核实：Gitleaks v8.30.1（MIT，
  约 165 规则，纯离线）；TruffleHog v3.97.5（AGPL-3.0，**验证默认开启**）；detect-secrets 1.5.0
  （Apache-2.0，部分插件 verify 会外呼）；Androguard 4.1.4（Apache-2.0）。8 项待核实已标注。
- 子智能体2（平台接口）：产出 docs/research/draft-platforms.md（352 行，24 条来源链接）。
  实测：MediaWiki recentchanges 200（rccontinue 游标）、博客园 RSS 200、StackOverflow 匿名
  quota 300/天、Gitee 内容/树接口匿名 200、Docker Hub 匿名 token+manifest 打通；
  结论：微博无合规公开检索接口；CSDN/掘金无官方接口；小程序无合法公开获取途径。
- 已整合为 docs/RESEARCH.md（含决策：TruffleHog 因 AGPL+默认在线验证不引入运行链路）。
- 环境限制记录：后台子智能体同时只能运行 1 个（并发限制），平台调研首次启动失败后重跑成功。

## 2026-09-19（会话1：阶段1实现）

### T1.1~T1.7 后端 — done

- 提交序列：7da25c7（骨架）→ 388c544（检测引擎+35 规则）→ b377088（核心模块+API）→
  92a03a5（测试）→ a2162c1（前端+演示）。
- 规则自检冒烟：首次发现 5 处样例问题（字符计数偏差/引号可选性/组检查），修复后
  `规则数: 35 / 规则自检通过`。
- Alembic：autogenerate 基线 659df6833a92，upgrade→downgrade→upgrade 链路实测通过。
  踩坑：alembic.ini 含中文注释在 GBK 控制台触发 UnicodeDecodeError，改纯 ASCII。
- 测试开发中修复的真实缺陷：
  1) 验证器注册的是类而非实例（TypeError）；
  2) `BaseCollector` 缺 `rate_limited` 默认属性 → 流水线 internal_error；
  3) `trigger_manual_run` 先置 running 与 `run_task` 防重叠检查冲突 → 扫描被跳过（发现数 0 的根因）；
  4) API 事件循环内调用 `asyncio.run` 报错 → pipeline 增加 `_run_async` 线程适配；
  5) verification_api 缺 import Credential（NameError）。
  全部以测试回归锁定。

### T1.9 测试证据 — done

- `cd backend && .venv/Scripts/python -m pytest` → **38 passed, 3 warnings**（2026-09-19）。

### T1.8 前端 + 真实服务冒烟 — done

- `npm install` + `npm run build` → 构建成功（dist 由后端 StaticFiles 托管）。
- uvicorn 实跑（127.0.0.1:8766）：
  - `/api/system/info`：35 规则 / 3 采集器 / 1 验证器；
  - 导入样例目录 → candidates=17、new_credentials=16、new_occurrences=17、completed；
  - 发现列表 16 条全部脱敏；GitHub PAT 样例 2 位置关联；Twilio 配对加成 55→75/60→80；
  - 幂等：重复扫描 items_skipped=7、新增 0，唯一凭据/位置不变；
  - detection_latency.sample_count=0（公开时间未知，未冒充）。
- 冒烟后已清理 data/（含临时主密钥与测试库），交付干净初始状态。
- 已知终端限制：Git Bash curl 发中文 JSON body 会编码错乱（控制台 GBK），Python/浏览器无此问题。

### T1.10 演示路径 — done（真实接入验收待用户）

- examples/demo_repo 合成样例（无法认证的假值）+ docs/DEMO.md 六步演示指南。

## 2026-09-19（会话2：阶段2 第一批，用户未手动操作，主控继续）

### 网络边界复测

- api.github.com 仍 403（共享出口 IP）；raw.githubusercontent.com 200。
- **Gitee API / 中文维基百科 / 博客园 RSS / Stack Overflow API 均 200 可直连** →
  这四个渠道的 live 验收可在本机完成。

### 阶段2 实现（提交 e81dd9e）

- 游标基础设施：BaseCollector 增 cursor_store（流水线注入 dict，运行后持久化 cursors 表）。
- 新采集器：gitee / mediawiki / generic_web（RSS·Sitemap·URL）/ stackoverflow；
  GitHub 增提交历史扫描（新→旧、游标截断、提交时间=low 可信公开时间）。
- 种子发现 API：POST /api/discover/seed 一次生成多渠道任务；纯关键词不做无认证代码搜索。
- 微博能力状态改 blocked（无合规公开接口，不绕过访问控制）。
- 新增 13+3 项测试。开发中修复：SO `quota_remaining:0` 被 `or 1` 吞掉；历史 blob 404 软跳过；
  采集器注册实例化（类被误注册）等。

### live 验收（提交 1bc1b1d，scripts/live_check.py 两轮实测）

- **MediaWiki**：首轮 0 条 → 排查发现两个真实问题并修复：
  1) 维基媒体对通用 UA 403（curl 200、httpx 默认 UA 403）→ 内置策略合规 UA；
  2) formatversion=2 修订对象无 revid 字段 → 按 pageid 映射。
  修复后实采 6 条修订，rccontinue 游标推进，第二轮拉到全为新变更。
- **博客园 RSS**：实采 6 条；第二轮 ETag → 304 跳过。
- **Stack Overflow**：实采 6 条；第二轮 6/6 版本缓存跳过。
- **Gitee**：首轮实采 7 条（openharmony/docs）+ 第二轮 6/7 缓存跳过；后续匿名限流
  → rate_limited 优雅停止（顺带修复流水线在无产出退出时漏记限流标志）。
- 四渠道真实内容未检出凭据候选（credentials_total=0，如实记录，不冒充发现）。
- 能力清单：Gitee/MediaWiki/博客园/SO/通用订阅 → live_verified；微博 → blocked。
- 最终测试：**54 passed**（2026-09-19）。live 数据保留在 data/live.db（已 gitignore）。

## 2026-09-19（会话2续：GitHub 认证实采 + 验证实证）

### Token 处理（安全）

- 用户提供 fine-grained PAT（聊天中出现 → 建议实验后吊销轮换）。
- 落地：仅写入 `data/github.token`（gitignore 已验证）+ 系统设置库 Fernet 加密；
  未写入任何文档/代码/日志/Git（提交前 `git grep` 复查）。

### 权限探测

- `/user` 200；认证配额 4999/5000 → **此前匿名 403 确为共享 IP 配额限制**。
- 账号 0range-Cat；仅一个公开仓库 `0range-Cat.github.io`（push/admin 显示 true，
  但 fine-grained 实际无 Contents:write —— PUT contents 全部 403
  "Resource not accessible by personal access token"）。
- 建新仓库 403（无 Administration 权限）。
- 结论：可读采集+验证可做；受控泄露实验需用户追加 Contents:write（已写配置需求）。

### GitHub 认证态实采（live）

- 用户公开仓库：12 个当前文件入库；**历史提交扫描 53 条内容入库**（游标增量生效）；
  octocat/Hello-World 1 条。0 凭据候选（真实空结果，不冒充发现）。

### 最小验证实证（live）

- 用户自有凭据 → **valid（200，707ms）**；合成假凭据 → **invalid（401，779ms）**。
- 首次真实调用暴露并修复：worker.http_factory 返回"工厂的工厂"与验证器契约不符 → TypeError。
  mock 测试未覆盖真实工厂路径——已修复，54 项测试回归通过。

### 文档

- 新增 docs/DELIVERABLES.md：四项交付件 + 五个评价维度 → 真实数字与证据对照（答辩口径）。
- GitHub 渠道状态 → live_verified；评价 4/5 的受控实验部分标注为待写权限后执行。

## 2026-09-19（会话2续：阶段3 制品渠道）

### 容器镜像（OCI Registry 采集器）— done，live_verified

- 实现：镜像引用解析（docker.io/library 前缀、digest/tag）、匿名 Bearer token 流程、
  多架构清单选择、config digest 作镜像版本、逐层 gzip tar 解析、
  whiteout/opaque 语义（最终视图按层序：先应用下层删除，再加本层文件——
  测试暴露初版顺序错误后修正）、构建时间=low 可信公开时间、总量/成员数/大小熔断。
- live：alpine:latest 匿名拉取，40 条层文件入库（in_final_view 标记正常）。
- live 修复：Docker Hub blob 307 重定向到 CDN，采集层需 follow_redirects=True
  （验证器仍严格禁重定向——两个模块语义不同）。

### Android APK 采集器 — done，live_verified

- 实现：APK=zip；assets/res-raw/META-INF/配置文本扫描；classes*.dex 可打印字符串提取后扫描；
  Androguard 可选（未安装时二进制 manifest 如实跳过）；上传/本地/公开下载 URL 三种入口；
  内容 sha256 为版本；PK 头校验（修了一个 `len>4` 笔误）。
- live：F-Droid 官方 APK 25 条内容入库（assets + dex 字符串）；
  dex 字符串中的凭据可被引擎检出（测试断言）。

### 测试与提交

- 新增 tests/test_artifacts.py（OCI whiteout/最终视图/引用解析 + APK dex/二进制跳过/非zip拒绝）。
- 旧断言 `github==offline_tested` 更新为 live_verified（状态演进同步测试）。
- 全量 **58 passed**（2026-09-19）。能力清单：container.oci / app.apk → live_verified。

## 2026-09-19（会话2终：Token 轮换 + 受控时延实验完成）

- 用户吊销旧 Token 并追加 Contents:write 后提供新 Token；落地同前（gitignored 文件 + 加密库）。
- 写权限探测 201 → 执行 scripts/latency_experiment.py（新建，可复现）。
- **实验结果：20 凭据 / 21 位置 / 14 类型检出（评价 4）；P50=25.5s / P95=26.9s（n=3，轮询 8s）（评价 5）**。
- 幂等：二次扫描 21 项全部缓存跳过，0 新增。
- 实测插曲：GitHub push protection 拦截合成 Twilio SID（"Secret detected"）；
  按官方 bypass API（reason=used_in_tests）处理后推送成功，流程固化进实验脚本。
  （ghp_ 假值未触发拦截——GitHub 对自家 PAT 有校验位校验，侧面印证格式逼真度差异。）
- 脚本开发中修复：409 竞态重试、已存在跳过、时区 aware/naive 对齐、bytes/str 编码。
- 数据文件：data/latency_log.json（gitignored，含逐批 T0/T1/指纹前缀）。
