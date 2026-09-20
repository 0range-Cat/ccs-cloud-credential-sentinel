# 支持能力清单：公开渠道与凭据类型（含数量口径）

> 交付件 3 + 4 的合并清单，并给出赛题评价方式要求的**全部数量口径**。
> 本文自包含可直接用于评审；更细的单项矩阵见
> [SUPPORTED_CHANNELS.md](SUPPORTED_CHANNELS.md) 与 [SUPPORTED_CREDENTIALS.md](SUPPORTED_CREDENTIALS.md)。
> 状态口径（全文统一）：
> **planned** 规划支持 / **implemented** 代码已实现 / **offline_tested** 离线测试通过（平台响应样例注入）/
> **live_verified** 真实渠道实采验证通过（含证据链接）/ **blocked** 外部条件受限（如实记录原因，不做绕过）。
> 最后更新：2026-09-19。

---

## 一、数量口径总表（先看这里）

| 口径 | 数量 | 说明 |
| --- | --- | --- |
| 赛题公开渠道类别 | **7 类** | 代码托管 / Wiki / 微博 / 知识分享 / 容器镜像 / App / 小程序 |
| 其中已实现类别 | **5 类** | 代码托管、Wiki、知识分享、容器镜像、App |
| 其中合规受限类别 | 2 类 | 微博 = blocked（无合规公开接口）；小程序 = 容器解析仅支持未加密包（加密包不做解密），均如实标注 |
| 具体平台 / 入口总数（在线 + 制品） | **10 个** | GitHub、Gitee、MediaWiki、博客园、Stack Overflow、通用 RSS/Atom/Sitemap/URL、OCI Registry、APK 下载入口、未加密 wxapkg、（另有本地目录/压缩包导入，属分析入口，**不计入**渠道数） |
| 其中 live_verified | **7 个** | 7/8 在线与制品入口完成真实渠道实采验证 |
| 可检索/检测的凭据类型 | **43 类** | 43 条真实规则，全部带正反样例并通过注册表自检 |
| 可最小在线验证的类型 | **8 类** | GitHub PAT（valid+invalid 双例）、AWS AK/SK 配对、Gitee、GitLab、Slack、Telegram、npm、Hugging Face |
| 明确不支持在线验证的类型 | 3 组 | OpenAI/Anthropic/Stripe（无"不枚举资源"的合规端点）、数据库连接串/口令（无法保证仅认证）、SSH 私钥/钉钉 Webhook（无目标或即用即失效）——**unsupported，检测能力保留** |

> 口径纪律：类别数与平台数**分开报**；自动监控与导入分析**分开报**；检测能力与验证能力**分开报**；
> 实现状态与真实接入状态**分开报**；别名/变体/重复规则不拆分凑数。
> 全部证据见 [EVALUATION.md](EVALUATION.md)。

---

## 二、支持的公开渠道列表（10 个入口，逐渠道）

### 2.1 代码托管（2）

| # | 渠道 | 状态 | 采集入口 | 支持内容 | 增量机制 | 关键限制（如实记录） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GitHub | **live_verified** | REST `/repos` `/git/trees` `/git/blobs` `/commits`；Token 可选（设置页，加密存储） | 当前分支全部文本文件；**提交历史扫描**（新增/修改文件逐版本） | blob sha 版本缓存 + 历史游标 `last_commit_scanned` | 匿名 60 次/时、认证 5000 次/时；树可能 truncated（已透传标记）；文件级公开时间不可得（历史用提交时间，low 可信）；Code Search 需认证且 10 次/分、单查询 1000 条（未使用，不冒充实时可搜） |
| 2 | Gitee | **live_verified** | API v5 trees+blobs；Token 可选 | 当前分支文本文件 | blob sha 版本缓存 | 匿名限流不稳定（共享 IP），生产建议 Token；限速官方数字待核实 |

### 2.2 Wiki（1）

| # | 渠道 | 状态 | 采集入口 | 支持内容 | 增量机制 | 关键限制 |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | MediaWiki 兼容（中文维基百科实测） | **live_verified** | Action API `recentchanges` + `prop=revisions` | 变更页面修订内容、标题、页面 URL | `rccontinue` 游标（增量续扫实测） | 需站点策略合规 UA（内置）；修订时间戳=该版本公开时间（medium 可信，参与时延统计）；内容为抓取时刻最新修订 |

### 2.3 知识分享（3）

| # | 渠道 | 状态 | 采集入口 | 支持内容 | 增量机制 | 关键限制 |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 博客园 | **live_verified** | 官方 RSS（`feed.cnblogs.com`） | 正文（HTML 剥离后） | ETag/Last-Modified 条件请求（304 实测） | 用户 RSS 302 至统一地址 |
| 5 | Stack Overflow | **live_verified** | API 2.3 search + questions(withbody) | 问题标题+正文、标签、链接 | 问题 ID+最后活跃时间版本缓存 | 免 key 配额 300/天；尊重 backoff/quota |
| 6 | 通用 RSS/Atom/Sitemap/URL | **live_verified** | 任一订阅源/站点地图/页面 | 条目正文、站点页面文本 | ETag/Last-Modified；sitemap lastmod（low 可信）；内容哈希 | 覆盖任何提供订阅源或站点地图的站点（CSDN/掘金无官方接口，若有合规抓取路径可经此接入，另行评估） |

### 2.4 容器镜像（1）

| # | 渠道 | 状态 | 采集入口 | 支持内容 | 增量机制 | 关键限制 |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | OCI/Docker Registry 兼容（Docker Hub 实测；ghcr/阿里云同协议） | **live_verified** | Distribution API：token → manifest → config → layers | 每层文件文本；**当前视图可见 vs 历史层残留**（whiteout/opaque 语义，`in_final_view` 标记） | config digest 作镜像版本；层 digest 内容缓存 | 层总量/成员数/大小熔断；构建时间=low 可信；blob 307→CDN（采集层跟随重定向） |

### 2.5 App（1）

| # | 渠道 | 状态 | 采集入口 | 支持内容 | 增量机制 | 关键限制 |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | Android APK（F-Droid 公开下载入口实测） | **live_verified** | 上传 / 本地路径 / 公开下载 URL 监控 | assets/res-raw/META-INF/配置文本；**classes*.dex 可打印字符串**；包名/版本（可选 Androguard） | 整包 sha256 为版本（重复下载自动跳过） | 纯静态不执行未知应用；二进制 manifest 未装 Androguard 时如实跳过；IPA 未实现不计入 |

### 2.6 小程序（1）

| # | 渠道 | 状态 | 采集入口 | 支持内容 | 增量机制 | 关键限制 |
| --- | --- | --- | --- | --- | --- | --- |
| 9 | 未加密 wxapkg 小程序包 | offline_tested | 上传 / 本地路径 / 公开下载 URL | 容器内文本条目（js/json/wxss/配置） | 整包 sha256 为版本 | **加密包（V1MMWX）拒绝解密（合规边界）**；线上小程序无合法公开获取途径（RESEARCH.md 记录）；解包目录可经本地目录扫描 |

### 2.7 导入分析入口（不计入渠道数）

| # | 入口 | 状态 | 说明 |
| --- | --- | --- | --- |
| 10 | 本地目录 / Git 仓库副本 / 压缩包（zip/tar） | offline_tested | 分析与测试入口；防路径穿越/符号链接/解压炸弹；单列统计不虚增渠道类别 |

### 2.8 合规受限渠道（如实记录，不做绕过）

| 渠道 | 状态 | 原因（2026-09-19 调研核实） |
| --- | --- | --- |
| 微博 | **blocked** | 无合规公开检索接口：需登录 Cookie、访客通道失效、开放平台搜索权限不对普通开发者开放。保留任务；不做任何绕过访问控制的实现 |
| CSDN / 掘金 | planned | 无官方公开接口；如需覆盖将以合规网页抓取方式单独评估（频率/robots/只读），不虚报为已接入 |

---

## 三、支持的凭据类型列表（43 类，全带正反样例）

规则文件：`backend/app/detection/rules/`（cloud / cloud_url / devplatform / services / keys_db 五组）。
每条规则含：稳定 ID、类型、厂商、版本、许可证、正则、长度/熵窗、上下文要求、占位符过滤、
配对规格、基础置信度、正反样例（正例必须命中、反例必须不误报——`test_rules_registry.py` 自检）。

### 3.1 云厂商（9）

| 类型 | 规则 ID | 置信度 | 配对 | 验证器 |
| --- | --- | --- | --- | --- |
| AWS Access Key ID（AKIA/ASIA） | aws-access-key-id | 80 | ↔ SK | **aws-sts-getcalleridentity**（STS GetCallerIdentity，需 AK+SK 配对） |
| AWS Secret Access Key | aws-secret-access-key | 60（配对+20） | ↔ AK | 同上 |
| 阿里云 AccessKey ID（LTAI） | aliyun-access-key-id | 75 | ↔ SK | — |
| 阿里云 AccessKey Secret | aliyun-access-key-secret | 60（配对+10） | ↔ AK | — |
| 腾讯云 SecretId（AKID） | tencent-secret-id | 75 | ↔ Key | — |
| 腾讯云 SecretKey | tencent-secret-key | 60（配对+10） | ↔ Id | — |
| Azure 存储账户密钥 | azure-storage-account-key | 80 | — | — |
| Azure AD 客户端密钥 | azure-ad-client-secret | 75 | — | — |
| GCP 服务账号 JSON | gcp-service-account-json | 95 | client_email/project_id | — |

### 3.2 代码与制品平台（7）

| 类型 | 规则 ID | 置信度 | 验证器 |
| --- | --- | --- | --- |
| GitHub PAT（ghp_/gho_/ghs_/ghu_/ghr_/github_pat_） | github-pat | 90 | **github-pat**（GET /user；valid+invalid 双例实证） |
| GitLab PAT（glpat-） | gitlab-pat | 85 | **gitlab-pat**（GET /api/v4/user） |
| Gitee 私人令牌（32hex+上下文） | gitee-token | 70 | **gitee-token**（GET /api/v5/user） |
| npm 发布令牌（npm_） | npm-token | 85 | **npm-whoami** |
| PyPI API Token（pypi-） | pypi-token | 85 | — |
| Hugging Face Token（hf_） | huggingface-token | 85 | **huggingface-whoami**（whoami-v2） |
| Docker Hub PAT（dckr_pat_） | dockerhub-token | 85 | — |

### 3.3 AI / 邮件 / 短信 / OAuth（9）

| 类型 | 规则 ID | 置信度 | 配对 | 验证器 |
| --- | --- | --- | --- | --- |
| OpenAI API Key（T3BlbkFJ 结构 / sk-proj- / 上下文） | openai-api-key | 90 | — | —（无不枚举资源端点，unsupported） |
| Anthropic API Key（sk-ant-） | anthropic-api-key | 90 | — | 同上 |
| SendGrid API Key（SG.xxx.yyy） | sendgrid-api-key | 90 | — | — |
| Mailgun API Key（key- + 上下文） | mailgun-api-key | 80 | — | — |
| Resend API Key（re_） | resend-api-key | 85 | — | — |
| Twilio Account SID（AC+32hex） | twilio-account-sid | 55（配对+20） | ↔ AuthToken | — |
| Twilio Auth Token | twilio-auth-token | 60（配对+20） | ↔ SID | — |
| OAuth 客户端密钥（通用，client_secret 上下文） | oauth-client-secret | 65 | — | — |
| Google OAuth 客户端密钥（GOCSPX-） | google-oauth-client-secret | 90 | — | — |

### 3.4 私钥 / 数据库 / 配置载体（10）

| 类型 | 规则 ID | 置信度 | 特性 | 验证器 |
| --- | --- | --- | --- | --- |
| 私钥块（RSA/EC/DSA/OpenSSH/PGP） | private-key-block | 95 | 标记加密状态（OpenSSH=unknown，如实） | unsupported（无目标不猜测） |
| 数据库连接串（MySQL/PG/MongoDB/Redis/MSSQL） | db-connection-url | 70 | URL 语义解析+弱口令拒绝 | unsupported（无法保证仅认证） |
| 配置文件通用密钥赋值（KEY/TOKEN/SECRET 后缀） | generic-env-assignment | 55 | 强上下文+熵≥3.2 | unsupported（弱特征） |
| 配置文件口令 | password-with-context | 35 | 需人工复核 | unsupported |
| Slack Token（xox[baprs]-） | slack-token | 90 | — | **slack-auth-test** |
| Telegram Bot Token（数字:AA…） | telegram-bot-token | 85 | — | **telegram-getme** |
| Stripe Live Key（sk_live_） | stripe-live-key | 95 | — | —（读余额/客户即业务数据，unsupported） |
| Stripe Test Key（sk_test_） | stripe-test-key | 35 | 弱信号 | — |
| 钉钉机器人 Webhook（URL 内 access_token） | dingtalk-webhook | 90 | — | unsupported（webhook 即可用，验证=发消息，不做） |
| 飞书/企业微信应用密钥（app_secret/corpsecret） | feishu-wecom-secret | 80 | — | — |

### 3.5 验证器合规说明（答辩要点）

8 个验证器全部满足最小验证要求：固定官方端点的身份确认接口；`follow_redirects=False`
且校验最终域名；不枚举资源（模型/仓库/存储桶/域名清单类接口一律不用——OpenAI/Anthropic/
Stripe 由此判 unsupported）；不读业务数据；无写操作；限流（429/backoff/配额头）与
权限不足（403）**不判 invalid**；证据仅存端点与状态码，响应体不入库；
每次验证追加历史。GitHub 验证已完成 valid（用户自有凭据）与 invalid（合成）双例；
其余 7 个已在真实网络验证 invalid 语义，valid 路径需对应平台自有凭据（用户可逐个回填）。

---

## 四、数量口径的诚实性说明（对应赛题"实现状态与真实接入状态分开"）

1. **35 类可检测**指"规则+正反样例自检通过"，不等于"在真实平台数据上验证过精确率"
   ——后者按渠道×类型在 EVALUATION.md 逐步回填（受控实验已覆盖 14 类的真实检出）。
2. **7 个 live_verified** 均有一轮以上真实公网实采证据（EVALUATION.md §4 记录请求量、
   增量验证与限流行为）；GitHub 受控泄露→发现实验（20 凭据/21 位置、P50=25.5s）为其中最强证据。
3. **blocked/planned/unsupported 是结论而非未完成**：微博（无合规接口）、加密小程序包
   （不做解密）、OpenAI 类验证器（无不枚举资源端点）均给出了原因与替代口径。
