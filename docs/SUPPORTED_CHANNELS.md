# 渠道能力矩阵（SUPPORTED_CHANNELS）

> 更新：2026-09-19 阶段2 第一批完成。
> 口径：渠道类别 ≠ 具体平台；自动监控 ≠ 导入扫描（本地导入不计入公开渠道类别数）。
> 状态：planned / implemented / offline_tested（平台响应样例注入测试）/
> **live_verified（真实公网渠道实采验证，含证据）** / blocked（外部条件受限，如实记录）。

## 总览

| 渠道类别 | 具体平台/入口 | 状态 | 增量机制 |
| --- | --- | --- | --- |
| 代码托管 | **GitHub** | **live_verified**（认证态实采+历史扫描+最小验证 valid/invalid） | 版本缓存（blob sha）；提交历史游标 last_commit_scanned |
| 代码托管 | **Gitee** | **live_verified** | 版本缓存 |
| Wiki | **MediaWiki 兼容** | **live_verified** | rccontinue 游标（增量续扫已实测） |
| 微博 | 微博 | **blocked**（无合规公开接口，不绕过） | — |
| 知识分享 | **博客园（RSS）** | **live_verified** | ETag/Last-Modified 条件请求 |
| 知识分享 | **Stack Overflow** | **live_verified** | 版本缓存 + 配额自读 |
| 知识分享 | **通用 RSS/Atom/Sitemap/URL** | **live_verified**（经博客园实测） | ETag/Last-Modified |
| 知识分享 | CSDN / 掘金 | planned（无官方接口，合规抓取单独评估） | — |
| 容器镜像 | OCI/Docker Registry | planned（阶段3） | digest |
| App | Android APK | planned（阶段3） | — |
| 小程序 | 合法取得的产物 | planned（阶段3） | — |
| 本地导入 | 本地目录/压缩包 | offline_tested | 内容哈希/成员元数据 |

**计入口径的实数**：公开渠道类别 **5/7 有实现**（微博 blocked、小程序 planned，均如实标注）；
具体平台/入口 **8 个**（GitHub、Gitee、MediaWiki、博客园、Stack Overflow、通用订阅入口、
OCI Registry、APK 下载入口），其中 **7 个 live_verified**；上传扫描/本地导入不计入。

## 明细

### Gitee（live_verified）
- 入口：`https://gitee.com/api/v5` repos/trees/blobs；Token 可选（设置页）。
- 实采证据（2026-09-19，scripts/live_check.py）：openharmony/docs 实采内容入库，
  第二轮 6/7 命中版本缓存跳过；匿名限流触发时 rate_limited 优雅停止并如实记录。
- 限制：匿名限流不稳定（共享出口 IP），生产建议配置 Token；限速数字待核实。

### MediaWiki 兼容（live_verified）
- 入口：`{站点}/api.php` recentchanges + prop=revisions；命名空间可配。
- 实采证据：中文维基百科实采 6 条修订入库；rccontinue 游标推进，第二轮拉到全为新变更。
- 亮点：修订时间戳=该版本公开发布时间（confidence=medium，来源=mediawiki_revision_timestamp），
  可参与发现时延统计。
- 踩坑记录：formatversion=2 下修订对象无 revid 字段（按 pageid 映射）；
  维基媒体拒绝通用 UA（需描述性 UA+联系方式，已内置合规 UA）。

### 博客园 RSS / 通用 RSS·Sitemap·URL（live_verified）
- 入口：feed_url / sitemap_url / url 三种模式；平台标识取主机名。
- 实采证据：博客园首页 RSS 实采 6 条；第二轮 ETag → 304 Not Modified 跳过。
- Sitemap：lastmod 为站点自述，公开时间记 low 可信；单 URL 用内容哈希去重。

### Stack Overflow（live_verified）
- 入口：API 2.3 search/advanced + questions?filter=withbody；免 key 配额 300/天。
- 实采证据：关键词检索实采 6 条问题正文；第二轮版本缓存 6/6 跳过；尊重 backoff/quota。

### GitHub（live_verified，2026-09-19 认证态实采）
- 当前文件树 + 提交历史扫描（新→旧、游标截断、历史层残留语义）。
- 实采证据（2026-09-19，认证态）：用户公开仓库实采 12 个当前文件 + 53 条历史提交内容；
  公共示例仓库实采 1 条；版本缓存与限流语义生效。
- 验证器实证：用户自有凭据 → **valid（HTTP 200，707ms）**；合成假凭据 → **invalid（401）**。
  （过程修复：worker.http_factory 返回形状与验证器契约不一致的 TypeError，回归测试锁定。）
- 剩余待办：受控"泄露→发现时延"实验需该仓库 Contents:write 权限（DELIVERABLES.md §三）。
- 限制（如实）：文件级公开时间不可得（历史扫描用提交时间，low 可信）；Code Search 需认证
  且 10次/分、单查询 1000 条上限。

### 容器镜像（live_verified，2026-09-19）
- 入口：OCI Distribution API（Docker Hub 匿名 token 流程实测；ghcr/阿里云同协议适配）。
- 语义：config digest 为镜像版本（重扫自动跳过）；逐层 tar 解析；
  **whiteout/opaque 处理**区分"当前视图可见"与"历史层残留"（extra.in_final_view 标记）；
  层被删除不意味着历史凭据不存在——所有层都扫描。
- 公开时间：镜像配置 created 为构建时间（low 可信），不冒充发布时间。
- 资源限制：层总量/单成员大小/成员数量/解压总量熔断；符号链接与设备文件跳过。
- 实测：alpine:latest 匿名拉取 40 条层文件；修复记录：blob 307 到 CDN 需跟随重定向（采集层，
  验证器仍禁重定向）。

### Android APK（live_verified，2026-09-19）
- 入口：上传 / 本地路径 / **公开下载 URL 监控**（内容 sha256 为版本，重复下载自动跳过）。
- 解析：APK=zip；assets/res-raw/META-INF/配置类文本直接扫描；classes*.dex 提取可打印字符串后扫描；
  二进制 AndroidManifest 需 Androguard（可选依赖，未装时如实跳过不假装扫描）。
- 安全：纯静态，不执行未知应用；成员数/大小/解压总量限制。
- 实测：F-Droid 官方 APK（公开下载入口）25 条内容入库（assets + dex 字符串）。

### 微博（blocked）
- 调研结论（RESEARCH.md）：无合规公开检索接口；需登录 Cookie；开放平台搜索权限不对普通开发者开放。
- 系统行为：能力状态 blocked 并给出原因与剩余工作；不做任何绕过访问控制的实现。

## 真实接入验收状态汇总

| 渠道 | live 验收 | 证据位置 |
| --- | --- | --- |
| Gitee | ✅（含限流停止语义） | EVALUATION.md §4 |
| MediaWiki | ✅ | 同上 |
| 博客园 RSS（通用采集） | ✅ | 同上 |
| Stack Overflow | ✅ | 同上 |
| GitHub | 待用户执行 DEMO.md | docs/DEMO.md |
| 微博/CSDN/掘金/镜像/APK/小程序 | 未开始（阶段2/3，部分外部不可行已标注） | TODO.md |
