# 平台公开内容获取/检索接口调研（草稿）

- 项目：云上凭据泄露自动化检测系统（网络安全创新大赛）
- 调研日期：2026-09-19
- 调研人：平台接口调研子智能体
- 调研环境说明：本机为 Windows + Git Bash，网络出口为共享数据中心 IP（`172.96.160.129`）。实测中 GitHub 未认证配额被同出口 IP 其他用户耗尽（60/h 用满即 403）；`docs.gitee.com` 本机与远程抓取工具均无法建立 TLS 连接。凡无法核实之处均标注"待核实"或"待本机网络复核"，未编造任何接口细节。

## 可行性一览

| 渠道 | 结论 | 一句话理由 |
|---|---|---|
| GitHub REST/Code Search/Events | 可行（需认证） | 公开 API 完善；未认证仅 60 次/小时，Code Search 强制认证 |
| Gitee API v5 | 部分可行 | 内容/树接口实测可用；搜索匿名返回空、官方限额文档不可达，待核实 |
| MediaWiki Action API | 可行 | 无需登录，`recentchanges` 支持游标增量，实测直连可用 |
| 微博 | 不可行 | 无合规公开检索接口，需账号登录态，存在访问控制与风控 |
| 博客园 cnblogs | 可行 | RSS/Atom 公开可用（实测 200） |
| CSDN | 不可行（官方接口） | 无官方公开 API，历史 RSS 已不稳定 |
| 掘金 | 不可行（官方接口） | 无官方开放平台，web 接口为非官方内部接口 |
| Stack Overflow API | 可行 | 无需 key 即可调用，匿名 300 次/天（实测），带 key 10,000/天 |
| RSS/Atom + Sitemap（通用） | 可行 | feedparser（BSD-2-Clause）成熟；Sitemap lastmod 可作游标 |
| 容器镜像（Docker Hub/ghcr/阿里云） | 可行/待复核 | Docker Hub 匿名拉取实测成功；ghcr 匿名令牌实测被拒待复核；阿里云标准 OCI 匿名流程 |
| 微信/支付宝小程序包 | 不可行 | 无合法公开获取途径，不予绕过 |

---

## 1. GitHub

### 采集入口
- REST API 基地址 `https://api.github.com`：
  - 仓库内容：`GET /repos/{owner}/{repo}/contents/{path}?ref={branch}`（返回 base64 内容）
  - Git 树：`GET /repos/{owner}/{repo}/git/trees/{branch_or_sha}?recursive=1`（一次取全仓库文件清单；超限会返回 `truncated:true`，截断阈值官方标注约 10 万条目/7MB —— 本次未能直接抓取该文档页，**待本机网络复核**）
  - 提交：`GET /repos/{owner}/{repo}/commits?since={ISO8601}&until={ISO8601}&per_page=100`
  - Gist：`GET /gists/public?per_page=100`、`GET /users/{username}/gists`、`GET /gists/{id}`（gist 内容含各文件明文）
- Code Search：`GET /search/code?q={query}`（限定词如 `language:`、`filename:`、`path:` 等）
- Events：`GET /events`、`GET /repos/{owner}/{repo}/events`、`GET /users/{user}/events/public`（PushEvent 等可发现新提交）

### 认证需求
- REST 核心接口：未认证可用但限额极低（按 IP 60 次/小时）；建议使用 PAT（fine-grained 或 classic）认证，认证后 5,000 次/小时/用户。
- Code Search：**强制认证**（官方 2023-03 变更公告：所有 code search 端点均要求认证）。

### 速率限制与结果上限（官方数字）
- 未认证：60 次/小时/IP（官方文档已核实，本机实测亦命中该限制：`X-RateLimit-Limit: 60`，同出口 IP 配额被耗尽返回 403）。
- 认证：5,000 次/小时/用户；GitHub App 安装最低 5,000/h 并可上调。
- 次级限制：REST 每分钟不超过 900 "points"（GET 计 1 点、写操作计 5 点）、最多 100 并发。
- Code Search：10 次/分钟；**每次搜索最多返回 1,000 条结果**（per_page 最大 100，翻页最多 10 页），超此范围需按时间/仓库维度切分查询。
- Search API 通用：有独立的更严格限流（官方文档仅写明"更严格"，具体每类上限以 changelog/文档为准）。

### 增量监控方式
- 仓库级：轮询 `GET /repos/{owner}/{repo}/commits?since={上次水位}`，游标为 commit 的 SHA 与时间戳。
- 全局发现：轮询 Events API（`/events` 或目标用户/仓库 events），游标为事件 `id`/`created_at`；也可用 `/search/commits?q=committer-date:>...` 按时间切分。
- Gist：轮询 `GET /gists/public` 按 `updated_at` 过滤（官方无全局 gist 的时间过滤参数，需本地过滤）。

### 已知限制/风险
- 本开发环境 `api.github.com` 可达（`/rate_limit` 返回 200），但共享出口 IP 未认证配额极易被耗尽——**必须配 PAT 才能稳定工作**。
- Code Search 结果 1,000 条上限；搜索索引只覆盖默认分支（官方对 code search 的说明，**待本机网络复核**）。
- Events API 返回上限约 300 条、保留窗口约 90 天（多篇学术/工程资料引用官方文档，官方页面本次未能直接抓取，**待复核**）；更早数据需改用 GH Archive（每小时公开事件归档）。
- 平台条款：抓取需遵守 GitHub Acceptable Use / 服务条款，只能经官方 API 获取。

### 接入建议
**可行（核心渠道，需配置 PAT）。** 内容/提交/ gist 列表用 REST 轮询 + `since` 增量；代码关键词检索用 Code Search（认证、10/min、1,000 条上限，需将关键词矩阵按仓库/时间分片）；全局新内容发现用 Events 轮询（90 天窗口内）。注意其余接口细节（tree 截断阈值、code search 索引范围）标注待本机网络复核。

### 来源（调研日期 2026-09-19）
- REST 限流：https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api （已抓取核实）
- Search/Code Search：https://docs.github.com/en/rest/search/search ；变更公告 https://github.blog/changelog/2023-03-10-changes-to-the-code-search-api/
- Events：https://docs.github.com/en/rest/activity/events ；GH Archive：https://www.gharchive.org/
- 本机实测：`/rate_limit` 200；`/search/code` 未认证 403（rate limit exceeded）

---

## 2. Gitee（API v5）

### 采集入口
- 基地址 `https://gitee.com/api/v5`：
  - 仓库内容：`GET /repos/{owner}/{repo}/contents/{path}?ref={branch}`
  - Git 树：`GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=`
  - 提交：`GET /repos/{owner}/{repo}/commits`
  - 搜索：`GET /search/repositories?q={kw}`、`GET /search/issues`（需核实）
- 文档：https://docs.gitee.com/docs/api/5/ 、Swagger：https://gitee.com/api/v5/swagger

### 认证需求
- 未认证可调用内容/树类只读接口（实测 200）；带 `access_token`（OAuth2/私人令牌）可获得更高配额与搜索能力（**搜索部分待核实**，见下）。

### 速率限制与结果上限
- 实测响应头：`X-RateLimit-Limit: 60`、`X-RateLimit-Remaining: 54~57`（匿名，窗口期未见文档说明）。
- 官方速率限制文档页 `https://docs.gitee.com/docs/api/5/rate-limiting` 本机 curl（TLS 复位）与远程抓取工具均无法访问，**官方具体数字待核实**。
- 搜索接口实测异常：匿名 `GET /search/repositories?q=nginx|vue|openharmony` 均返回 `200` + 空数组 `[]`，疑似匿名搜索被限制或需 `access_token`，**待核实**。

### 增量监控方式
- 对已列入监控的仓库轮询 `commits` 接口（时间水位）；`contents`/`trees` 按 commit SHA 比对。搜索接口若需 access_token 方可用，则增量发现依赖定期关键词轮询 + 本地去重。

### 已知限制/风险
- 中文平台，网络可达性好（本机直连 200）。
- 官方文档站访问不稳；匿名搜索不可用；配额窗口与认证配额数字均待核实。
- 平台条款：需遵守 Gitee 服务条款与 robots 规则。

### 接入建议
**部分可行。** 内容/树/提交接口实测可用，可作为 GitHub 的国内补充渠道；但搜索与配额细节待核实，接入前应先注册 Gitee OAuth 应用/私人令牌并复核官方限额。

### 来源（调研日期 2026-09-19）
- 本机实测：`/repos/openharmony/docs/contents/README.md` 200（base64 内容正常）；`/git/trees/master` 200；`/search/repositories?q=...` 200+空
- API 文档：https://gitee.com/api/v5/swagger ；速率限制页：https://docs.gitee.com/docs/api/5/rate-limiting （**待核实，本次不可达**）

---

## 3. MediaWiki（Action API）

### 采集入口
- 任意 MediaWiki 站点：`https://<域名>/w/api.php`（或 `/api.php`），核心参数 `action=query`。
- 最近变更（增量发现）：`list=recentchanges`；页面修订：`prop=revisions`。
- **真实可用样例（本机实测 200，返回正常 JSON）：**

```text
https://zh.wikipedia.org/w/api.php?action=query&list=recentchanges&rcprop=title%7Ctimestamp%7Cids%7Cuser&rclimit=5&format=json
```

实测返回：`{"batchcomplete":"","continue":{"rccontinue":"20260919095846|202663846","continue":"-||"},"query":{"recentchanges":[ ... {"type":"categorize","ns":14,"title":"...","pageid":905624,"revid":94439637, ...}]}}`

- 修订查询样例：`https://zh.wikipedia.org/w/api.php?action=query&prop=revisions&titles=主页面&rvprop=ids|timestamp|comment&format=json`

### 认证需求
- 匿名即可查询公开 wiki；无强制登录。需按 Wikimedia User-Agent 政策提供自定义 UA，并可用 `maxage`/`smaxage`、`maxlag` 控制负载。

### 速率限制与结果上限
- 官方对 API 无硬性 QPS 数字，靠 etiquette 约束（合理频率、缓存头、`maxlag`）；单次查询条数上限默认 500（bot 权限 5,000）（`rclimit` 等参数，参见 https://www.mediawiki.org/wiki/API:Limits ）。

### 增量监控方式
- 轮询 `list=recentchanges`，游标为 `rccontinue`（实测格式：`<时间戳>|<rcid>`，如 `20260919095846|202663846`），携带 `continue` 参数续传；也可按 `rcstart`/`rcend` 时间窗、`rctype=edit|new` 过滤。

### 已知限制/风险
- 维基百科对高频抓取有限制；近期变更的评论/摘要字段可能含敏感串，需注意个人信息处理合规。
- 国内网络对维基百科可达性因地区而异（本机实测可达，其他站点如 MediaWiki.org 未逐一实测）。

### 接入建议
**可行。** 无需账号、支持标准游标增量，适合作为"公开 Wiki 页面变更"类数据源；实现上用 `rccontinue` 游标 + 自定义 UA + 限速轮询。

### 来源（调研日期 2026-09-19）
- API 手册：https://www.mediawiki.org/wiki/API:RecentChanges 、https://www.mediawiki.org/wiki/API:Revisions 、https://www.mediawiki.org/wiki/API:Limits
- 本机实测：上文样例 URL 返回 200 与 `rccontinue` 游标

---

## 4. 微博

### 采集入口
- 官方开放平台：https://open.weibo.com （OAuth2.0 + Open API）
- 网页端接口：`m.weibo.cn/api/container/getIndex?containerid=100103type=1&q=<关键词>`、`weibo.com/ajax/statuses/searchqb?...` 等前端接口（非官方开放 API）

### 认证需求
- 网页端搜索接口**需登录 Cookie**：未登录请求返回"Sina Visitor System"访客页；早年可用的访客（visitor）Cookie 通道近年已基本失效，风控明显收紧。
- 官方开放平台需企业/个人开发者认证 + OAuth2 授权；搜索类接口基本不对普通开发者开放，文档多年未更新。

### 速率限制与结果上限
- **无官方公开数字**（开放平台接口权限逐应用审批）；网页端接口无公开限额说明。

### 增量监控方式
- 若走网页接口只能按关键词高频轮询 + Cookie 池，属于对访问控制的规避，本项目不采用。

### 已知限制/风险
- **结论（诚实记录）：无合规公开检索接口，需账号配置，存在访问控制。** 网页接口依赖登录态、风控强、抓取过多会冻结账号；第三方商业 API（如 TikHub 等）属于转售数据，合规性需另行评估，不作为项目默认方案。

### 接入建议
**不可行（默认不接入）。** 原因：无无需登录的公开检索接口；官方开放平台搜索权限不开放；任何自动化获取都需账号 Cookie 并规避风控，违反平台访问控制，存在封号与法律风险。若大赛确需覆盖微博源，应作为"人工/授权数据"单独申报。

### 来源（调研日期 2026-09-19）
- 开放平台：https://open.weibo.com
- 现状佐证（社区）：weibo-api-sdk 文档（需 Cookie/登录态）、bindog 新浪访客系统分析（访客通道失效背景）、2025 年多篇爬虫实践文章

---

## 5. 知识分享平台

### 5.1 CSDN
- **采集入口**：文章页 `https://blog.csdn.net/<用户名>/article/details/<id>`；无官方 API；历史 RSS 地址 `https://blog.csdn.net/<用户名>/rss/list` 现多数失效或内容不全（社区反馈，**官方无支持文档，待核实**）。
- **认证需求**：网页匿名可读；接口反爬较强。
- **速率限制**：无官方数字。
- **增量监控**：无官方途径；只能依赖站内搜索页/第三方 RSSHub 自建实例（非官方、稳定性差）。
- **已知限制/风险**：强反爬、无官方订阅渠道。
- **接入建议**：**不可行（无官方接口）**；如确需覆盖，仅限低频网页采集并遵守 robots，或经 RSSHub 公共/自建实例（标注为社区方案，非官方）。

### 5.2 博客园（cnblogs）—— RSS/Atom 公开可用（实测）
- **采集入口**：
  - 站点首页 Atom：`https://feed.cnblogs.com/blog/sitehome/rss` —— 实测 `HTTP 200`，`Content-Type: application/xml`，Atom 格式（`<feed xmlns="http://www.w3.org/2005/Atom">`）
  - 用户博客 RSS：`https://www.cnblogs.com/<用户名>/rss` —— 实测 302 重定向至 `https://feed.cnblogs.com/blog/u/<数字UID>/rss/`（重定向后即为公开订阅源）
  - 分类聚合：`https://feed.cnblogs.com/blog/sitehome/picked/rss`（精选，**待核实**）
- **认证需求**：无。
- **速率限制**：无官方数字；建议遵守一般 RSS 轮询礼仪（>= 5~10 分钟间隔，带自定义 UA）。
- **增量监控**：轮询 RSS，游标为条目 `id`/`published` 时间戳；博客园文章 URL 形如 `/p/<postId>` 可本地去重。
- **已知限制/风险**：站点 feed 仅含首页/精选窗口内容，单用户 feed 需拿到数字 UID（可由 302 Location 获得）。
- **接入建议**：**可行。** 匿名、标准 Atom、实现成本低。
- 来源：本机实测（2026-09-19，见上）

### 5.3 掘金（juejin.cn）
- **采集入口**：无官方开放平台/API。`api.juejin.cn/content_api/v1/...` 为网页前端使用的**内部接口**（社区抓包收集，如 `content/article/query_list`），非官方承诺，随时可变更。
- **认证需求**：内部接口普遍需登录态 Cookie（`sessionid` 等）与签名头。
- **速率限制/结果上限**：无官方数字（非官方接口）。
- **增量监控**：无官方途径。
- **已知限制/风险**：依赖非公开接口违反平台意愿，存在风控与稳定性风险。
- **接入建议**：**不可行（无官方公开检索 API）**；官方渠道缺失，不建议接入。
- 来源（2026-09-19）：GitHub `chenzijia12300/juejin-api`（"掘金网站web端API收集"）、掘金社区文章（JueJin-MCP 明确声明"不依赖任何非公开 API"佐证官方 API 缺失）

### 5.4 Stack Overflow / Stack Exchange API
- **采集入口**：`https://api.stackexchange.com/2.3/`，如：
  - 搜索：`GET /2.3/search/advanced?site=stackoverflow&q=<kw>&pagesize=100`
  - 最新问题增量：`GET /2.3/questions?site=stackoverflow&since=<epoch>&pagesize=100`
  - 站点信息（含配额）：`GET /2.3/info?site=stackoverflow`
- **认证需求**：**无需 key 即可调用**（匿名共享 IP 配额）；注册应用可免费获取 key / access_token 提升配额。
- **速率限制与结果上限（官方文档 + 实测）**：
  - 实测匿名 `/2.3/info` 返回 `quota_max: 300`（当天剩余 `quota_remaining` 随调用递减）—— 匿名按 IP 每日约 300 次。
  - 官方 throttle 文档：单 IP 每秒超过 30 次请求将被丢弃（封禁约 30 秒~几分钟）；带 key/access_token 的应用默认日配额 10,000（每用户最多 5 个配额）。带 key 的确切共享配额规则**待进一步复核**。
  - 分页 `pagesize` 最大 100，`backoff` 字段提示翻页间隔。
- **增量监控**：`since`/`fromdate`（Unix 时间戳）+ `page`；游标为问题 `creation_date` 水位。
- **已知限制/风险**：部分接口（写操作）需 OAuth；匿名配额按 IP 共享，数据中心 IP 易被同 IP 用户挤占（与 GitHub 同理）。
- **接入建议**：**可行。** 无需登录、官方支持、有明确配额语义，适合作为技术社区凭据泄露线索源（申请免费 key 更稳）。
- 来源（2026-09-19）：https://api.stackexchange.com/docs/throttle 、https://api.stackexchange.com/docs/search ；本机实测 `/2.3/info`

---

## 6. 通用：RSS/Atom 与 Sitemap 作为采集入口

### 采集入口
- RSS/Atom：站点 `/rss`、`/feed`、`/atom.xml`、`/index.xml` 等约定路径 + HTML `<link rel="alternate" type="application/rss+xml">` 发现。
- Sitemap：`/sitemap.xml`、`/sitemap_index.xml`，以及 `robots.txt` 中的 `Sitemap:` 行；协议规范 https://www.sitemaps.org/zh_CN/ 。
- Sitemap index 允许嵌套；`<lastmod>` 字段可作增量水位。

### 认证需求
- 公开站点均匿名。

### 速率限制与结果上限
- 协议层面：单个 sitemap 文件上限 50,000 条 URL / 50MB（未压缩）（sitemaps.org 协议规定）；RSS 无上限规定，由站点自控。访问频率需遵守 robots.txt 与各站礼仪。

### Python 解析库（许可证）
- **feedparser**（RSS/Atom 统一解析）：PyPI 实测当前版本 6.0.14，许可证 **BSD-2-Clause**（`requires_python >= 3.10`）。
- Sitemap（XML）：标准库 `xml.etree.ElementTree`（PSF 许可）或 `lxml`（BSD 许可）；robots.txt 解析用标准库 `urllib.robotparser`（PSF）。
- 注：feedparser 依赖 `sgmllib3k`（源自 Python 标准库 sgmlib 的 py3 移植，PSF 系许可，**待核实其 PyPI 许可标注**）。

### 增量监控方式
- RSS：轮询 + 条目 GUID/`published` 水位去重；Sitemap：`lastmod` 水位比对。

### 已知限制/风险
- 国内大量平台（CSDN、掘金等）已不再原生提供 RSS；RSSHub 等社区网关可补齐但属第三方、非官方。

### 接入建议
**可行（通用兜底层）。** 对提供 RSS/Sitemap 的目标（博客园、各大文档站、镜像仓库更新日志等）以 feedparser 统一实现低成本增量采集。

### 来源（调研日期 2026-09-19）
- https://pypi.org/pypi/feedparser/json （实测许可证字段）
- https://www.sitemaps.org/zh_CN/ ；feedparser 文档 https://feedparser.readthedocs.io/

---

## 7. 容器镜像（Docker Hub / ghcr.io / 阿里云公共镜像仓库）

### 采集入口（OCI Distribution API，三家同构）
- `GET /v2/` → 匿名返回 `401` + `WWW-Authenticate: Bearer realm="<token端点>",service="<service>"`（实测三家均如此）
- `GET <realm>?service=<service>&scope=repository:<name>:pull` → 匿名获取 Bearer token
- `GET /v2/<name>/manifests/<tag|digest>`（带 `Accept: application/vnd.oci.image.index.v1+json` 等）→ 清单（含层 digest 列表）
- `GET /v2/<name>/blobs/<digest>` → 层/配置 blob（通常 302 到 CDN）；`GET /v2/<name>/tags/list` → 标签枚举；`/_catalog` 为可选端点
- Docker Hub 附加 Hub API：`https://hub.docker.com/v2/repositories/<ns>/<repo>/tags?page_size=100&ordering=last_updated`（匿名，**本次未实测，待核实**）

### 认证需求
- 公共镜像：匿名 token 即可拉取（无需账号）；私有镜像需登录凭据。

### 速率限制与结果上限
- **Docker Hub（官方文档核实）**：匿名用户 **每 6 小时 100 次拉取，按 IPv4 地址或 IPv6 /64 子网计**；认证免费用户 200 次/6h；付费不限。本机实测匿名拉取 `library/alpine:latest` 清单返回 200，响应头 `docker-ratelimit-source: 172.96.160.129`、`ratelimit-limit: 100;w=3600`、`ratelimit-remaining: 100;w=3600` —— 头部显示的窗口（3600s）与文档"6 小时"表述存在差异，**以官方文档 6h/100 次为准并标注待复核**。
- **ghcr.io**：官方文档称公共包支持匿名拉取；但本机实测匿名 token 端点 `https://ghcr.io/token?service=ghcr.io&scope=repository:distroless/base:pull` 返回 `{"errors":[{"code":"DENIED",...}]}`，manifest 403 —— 与预期不符，**待本机网络复核**（匿名限流无公开数字）。
- **阿里云公共镜像仓库**（`registry.cn-hangzhou.aliyuncs.com` 等）：`/v2/` 实测 401 + `WWW-Authenticate: Bearer realm="https://dockerauth.cn-hangzhou.aliyuncs.com/auth"`，标准 OCI 匿名流程；公共仓库匿名拉取可行，官方匿名限速数字未见公开文档，**待核实**。

### 增量监控方式
- 轮询 `tags/list` 或 Hub API `ordering=last_updated`；游标为 tag 集合快照/最后更新时间；对目标 tag 用 digest 变更判断更新。

### 已知限制/风险
- 匿名配额按 IP/子网共享（Docker Hub），数据中心出口极易触限；批量扫描层内容体积大，需控制并发与缓存（按 digest 去重，只拉新增层）。
- 合规边界：仅处理**公开**镜像的公开层内容；不得尝试私有仓库或绕过限流。

### 接入建议
**可行（Docker Hub 匿名拉取已实测打通）；ghcr/阿里云为"标准流程可用但配额细节待复核/待核实"。** 实现要点：`/v2/` 探测 → 匿名 token → manifests → 按 digest 选择性拉取 blobs；对层内容做明文凭据扫描（本项目核心场景之一）。

### 来源（调研日期 2026-09-19）
- Docker Hub 限流：https://docs.docker.com/docker-hub/usage/ （已抓取核实：匿名 100/6h 每 IPv4 或 IPv6 /64；免费认证 200/6h）
- OCI Distribution Spec：https://github.com/opencontainers/distribution-spec/blob/main/spec.md
- ghcr：https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- 阿里云容器镜像服务文档：https://help.aliyun.com/document_detail/60994.html （匿名限速**待核实**）
- 本机实测：三家 `/v2/` 401 响应头；Docker Hub 匿名 token+manifest 200；ghcr 匿名 DENIED

---

## 8. 小程序（微信 / 支付宝）

### 采集入口
- 无。微信小程序包（`.wxapkg`）仅随微信客户端分发并在本地加密存储；微信公众平台/开放社区只提供"微信开发者工具"供开发者管理**自己的**代码包。支付宝小程序包同理，平台后台仅支持开发者本人或授权项目（服务商/模板流程）下载代码包。

### 认证需求
- 获取任何小程序包都需要开发者账号对**自有/授权**项目的登录态；不存在面向任意小程序的公开下载接口。

### 速率限制与结果上限
- 不适用（无公开获取途径）。

### 增量监控方式
- 不适用。

### 已知限制/风险
- 社区存在本地缓存提取与反编译工具（如 wxapkg 解包工具），属于**绕过平台加密与访问控制**的逆向行为，有明确法律与合规风险。本项目明确不寻找、不使用此类方法。

### 接入建议
**不可行（无合法公开获取途径）。** 如实记录：小程序包不作为数据源；若大赛评审需要覆盖该面，只能以"平台方授权/运营者自查"等合法合作形式另行设计。

### 来源（调研日期 2026-09-19）
- 微信开发者文档/工具下载：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html （仅开发者工具，无代码包公开下载）
- 支付宝开放平台文档中心：https://opendocs.alipay.com/ （仅开发者工具与自有项目管理）
- 社区现状佐证：wxapkg 反编译工具仓库与教程的存在本身说明"仅能逆向获取"，反向印证无官方公开渠道

---

## 来源链接清单（调研日期均为 2026-09-19）

1. GitHub REST 限流：https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
2. GitHub Search API（Code Search）：https://docs.github.com/en/rest/search/search
3. GitHub Code Search 变更公告（认证要求、10 次/分钟）：https://github.blog/changelog/2023-03-10-changes-to-the-code-search-api/
4. GitHub Events API：https://docs.github.com/en/rest/activity/events
5. GH Archive（事件历史归档）：https://www.gharchive.org/
6. Gitee API v5 Swagger：https://gitee.com/api/v5/swagger
7. Gitee 速率限制文档（本次不可达，待核实）：https://docs.gitee.com/docs/api/5/rate-limiting
8. MediaWiki API:RecentChanges：https://www.mediawiki.org/wiki/API:RecentChanges
9. MediaWiki API:Revisions：https://www.mediawiki.org/wiki/API:Revisions
10. MediaWiki API:Limits：https://www.mediawiki.org/wiki/API:Limits
11. 维基百科 recentchanges 实测样例：https://zh.wikipedia.org/w/api.php?action=query&list=recentchanges&rcprop=title%7Ctimestamp%7Cids%7Cuser&rclimit=5&format=json
12. 微博开放平台：https://open.weibo.com
13. 博客园站点 Atom（实测 200）：https://feed.cnblogs.com/blog/sitehome/rss
14. Stack Exchange API 限流文档：https://api.stackexchange.com/docs/throttle
15. Stack Exchange API search：https://api.stackexchange.com/docs/search
16. feedparser PyPI 元数据（BSD-2-Clause，6.0.14）：https://pypi.org/pypi/feedparser/json
17. Sitemap 协议：https://www.sitemaps.org/zh_CN/
18. Docker Hub pull usage and limits：https://docs.docker.com/docker-hub/usage/
19. OCI Distribution Spec：https://github.com/opencontainers/distribution-spec/blob/main/spec.md
20. GitHub Container Registry 文档：https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
21. 阿里云容器镜像服务：https://help.aliyun.com/document_detail/60994.html
22. 微信开发者工具下载页：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html
23. 支付宝开放平台文档中心：https://opendocs.alipay.com/
24. 掘金非官方接口收集仓库（佐证"无官方 API"）：https://github.com/chenzijia12300/juejin-api

## 待核实项汇总

| 编号 | 事项 | 原因 |
|---|---|---|
| T1 | GitHub：tree 接口截断阈值（10 万条/7MB）、code search 索引分支范围、Events 保留窗口 90 天 | 官方对应文档页本次未直接抓取成功，仅二手来源；本机 api.github.com 匿名配额被共享 IP 耗尽 |
| T2 | Gitee：官方速率限制数字、搜索接口是否必须 access_token | docs.gitee.com 本机与抓取工具均 TLS 失败；实测匿名搜索返回空数组 |
| T3 | CSDN：历史 RSS 地址是否完全失效 | 社区反馈，无官方文档 |
| T4 | Stack Exchange：带 key 的确切共享配额规则 | throttle 文档页面表述需进一步核对 |
| T5 | Docker Hub：实测响应头 `w=3600` 窗口与文档"6 小时"差异 | 需在独立网络环境复核 |
| T6 | ghcr.io：匿名拉取 DENIED 是否为环境特异性 | 需本机网络复核 |
| T7 | 阿里云公共镜像仓库匿名拉取限速 | 无公开官方数字 |
| T8 | Docker Hub Hub API（tags 排序增量）匿名可用性 | 本次未实测 |
