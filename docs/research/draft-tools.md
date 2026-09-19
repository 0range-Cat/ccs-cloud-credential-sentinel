# 开源工具调研草稿：凭据泄露检测相关工具现状

- 调研日期：2026-09-19（下文所有"最新版本/发布时间"均以该日为基准核实）
- 调研方式：GitHub Releases / 仓库 README / 源码文件、PyPI（含 PyPI JSON API）、官方文档，逐项核实；无法核实的条目一律标注 **待核实** 并说明原因。
- 用途：为"云上凭据泄露自动化检测系统"（Git / 云存储 / APK / 容器镜像多源扫描 + 在线验证）的选型与复用决策提供依据。

---

## 1. Gitleaks（github.com/gitleaks/gitleaks）

| 字段 | 结论 |
| --- | --- |
| 官方仓库 / 文档 | 仓库：https://github.com/gitleaks/gitleaks ；文档以仓库 README 与 `config/gitleaks.toml` 为主（无独立文档站） |
| 调研日期 | 2026-09-19 |
| 最新版本 / 发布时间 | **v8.30.1，2026-03-21**（GitHub Releases 标记 "Latest"；此前 v8.30.0 为 2025-11-26） |
| 许可证 | **MIT**（仓库侧边栏与 LICENSE 文件） |
| 维护状态 | 活跃但节奏放缓：2025-11 至 2026-03 连续发布 4 个版本；截至调研日 v8.30.1 之后暂无新版本发布（有 issue 提及 v8.30.1 标签曾缺 release 页，已处理）。语言：Go |
| Windows / Ubuntu 可用性 | 均可。官方 Releases 提供多平台二进制（含 `gitleaks_<version>_windows_x64.zip`，社区可经 `scoop install gitleaks`）；Ubuntu 亦可二进制 / Docker / Go 编译安装 |
| Python 集成方式 | **推荐 CLI 子进程调用**（Go 程序，无 Python 库）。三个扫描子命令：`gitleaks git`（扫描 git 历史，底层 `git log -p`）、`gitleaks dir`（目录/文件）、`gitleaks stdin`；`--report-format json --report-path report.json` 输出 JSON；退出码 0=无泄露、1=有泄露或出错（可用 `--exit-code` 自定义） |
| 默认联网行为 | **纯本地、不联网**。README 通篇无任何网络功能，仅做本地正则 + 熵 + 关键词扫描（git/dir/stdin 三种输入均为本地数据） |
| 规则数量与扩展 | 内置默认规则约 **165 条**（`config/gitleaks.toml` 中约 165 个 `[[rules]]`，1Password 至 Zendesk 按字母排列）；扩展方式：自定义 `gitleaks.toml`（`[extend] useDefault = true` 可叠加默认规则，扩展链最深 2 层；规则支持 `id/description/regex/secretGroup/entropy/path/keywords/tags` 与规则级/全局 allowlist） |

**JSON 输出样例**（字段来自 README 自定义模板示例，值为示意）：

```json
{
  "Description": "Uncover a GitHub Personal Access Token",
  "StartLine": 12, "EndLine": 12, "StartColumn": 18, "EndColumn": 54,
  "Line": "github_token = \"ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\"\n",
  "Match": "github_token = \"ghp_XXXX…\"",
  "Secret": "ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "File": "config/settings.py",
  "SymlinkFile": "",
  "Commit": "3f6a1c0b…",
  "Entropy": 3.65,
  "Author": "dev", "Email": "dev@example.com", "Date": "2026-01-01T00:00:00Z", "Message": "init",
  "Tags": null,
  "RuleID": "github-pat",
  "Fingerprint": "3f6a1c0b:config/settings.py:github-pat:12"
}
```

**复用建议**：
- 复用：作为"Git 历史 / 目录"扫描引擎的 CLI 子进程首选（MIT 宽松、零联网、JSON 稳定、单二进制易部署，Windows/Ubuntu 双平台无依赖）；其默认规则文件（MIT）可直接拿来改写成本项目云凭据规则。
- 不复用：其验证能力——Gitleaks 没有在线验证（这正是本项目要自研的"受控验证"卖点之一）；APK/镜像源的解析也不在其职责内。
- 许可证义务：MIT——分发/修改需**保留版权与许可声明**；直接复制其规则文件时同样随附 MIT 声明（建议在项目 NOTICE 中注明"规则基于 gitleaks v8.30.1 修改"）。

---

## 2. TruffleHog（github.com/trufflesecurity/trufflehog）

| 字段 | 结论 |
| --- | --- |
| 官方仓库 / 文档 | 仓库：https://github.com/trufflesecurity/trufflehog ；文档：https://trufflesecurity.com/docs （Configuration file reference 等） |
| 调研日期 | 2026-09-19 |
| 最新版本 / 发布时间 | **v3.97.5，2026-09-16**（3 天前发布；8-9 月连发 v3.97.0~v3.97.5，发布节奏约每周/双周一次） |
| 许可证 | **AGPL-3.0**（仓库侧边栏/LICENSE；v2 时代为 GPL-2.0，v3 起改 AGPL-3.0） |
| 维护状态 | 非常活跃：约 28k stars，几乎每月多个版本，2026-09 仍在新增检测器（如 HumioAPIToken、Resend） |
| Windows / Ubuntu 可用性 | 均可。Releases 提供 `trufflehog_<version>_windows_amd64.zip` 等 Windows 资产；Ubuntu/Kali 有打包（Kali 源内版本 3.94.3）与 Docker 镜像；README 另给 Windows CMD/PowerShell 的 Docker 用法 |
| Python 集成方式 | **CLI 子进程调用**（Go 程序）。数据源子命令：`git / github / gitlab / huggingface / docker / filesystem / syslog / circleci / travisci / gcs / postman / jenkins / elasticsearch / stdin / multi-scan`；`--json` 逐行输出 JSON；`--results=verified,unverified,unknown`（默认三者全出） |
| 默认联网行为 | **默认开启在线验证**（这是与 Gitleaks 的最大差异）。官方旗标为 `--[no-]no-verification`（"Don't verify the results"），即不关闭就验证；README 明言 "Verification eliminates false positives"。命中凭据后会向各云厂商 API 发起校验请求（详见专题 B）。**集成时务必评估外呼合规，必要时显式加 `--no-verification`** |
| 规则数量与扩展 | README 称 **700+ 检测器**（"over 700 credential detectors that support active verification"）、分类 **800+ 种凭据类型**。扩展：① Go 实现 `Detector` 接口（`FromData(ctx, verify, data) []Result`，含关键词预筛/正则/熵）需编译进二进制；② 官方支持 YAML 配置的 **custom detectors**（`detectors:` 下 `keywords / regex / verify(endpoint, headers, unsafe)`，用 `--config` 挂载；本次通过官方文档索引与社区示例核实其存在，具体字段细节**待核实**——官方文档站页面未能直接抓取） |

**JSON 输出样例**（字段名据官方 `--json` 输出与社区解析整理，值为示意）：

```json
{
  "SourceMetadata": { "Data": { "Git": { "commit": "…", "file": "config/settings.py", "email": "…", "repository": "…", "timestamp": "…", "lines": "12-13" } } },
  "SourceID": 1, "SourceType": 1, "SourceName": "git",
  "DetectorType": 2, "DetectorName": "GitHub", "DecoderName": "PLAIN",
  "Verified": true,
  "Raw": "ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "RawV2": "",
  "Redacted": "ghp_****REDACTED****",
  "ExtraData": { "rotation_guide": "https://how-to.rotate-a-secret.com/github", "version": "2" },
  "VerificationError": ""
}
```

**复用建议**：
- 复用：作为**在线验证引擎**与"深度检测器库"以 CLI 子进程方式复用（`--results=verified` 只输出确认存活的凭据，可显著降噪）；其 `docker` 子命令可直接扫镜像（registry/本地 daemon/tarball 三种输入）。
- 不复用：不作为 Python 库 import；不复制其检测器代码/规则进本项目（AGPL 传染）。
- 许可证义务：**AGPL-3.0 有强传染性**——若把它的代码链接进本项目再分发（或对外提供网络服务），整体需开源。通过"独立进程 + 管道/JSON"调用属于聚合（aggregate）而非衍生作品，是业界常见做法，但法律边界存在讨论空间：务必保持**进程隔离、不 import、不静态链接、不复制源码**，并在项目文档中注明以独立程序方式调用。

---

## 3. detect-secrets（github.com/Yelp/detect-secrets）

| 字段 | 结论 |
| --- | --- |
| 官方仓库 / 文档 | 仓库：https://github.com/Yelp/detect-secrets ；文档：仓库 `docs/`（audit.md、filters.md、plugins.md 等） |
| 调研日期 | 2026-09-19 |
| 最新版本 / 发布时间 | **1.5.0，2024-05-06**（PyPI 核实，此后无新版本） |
| 许可证 | **Apache-2.0** |
| 维护状态 | 缓慢但未死：最后实质代码提交为 2025-01-06（Python 3.13 支持），2026-04-02 仅有一次安全审查 workflow 提交；1.x 功能稳定、Yelp 内部仍在用 |
| Windows / Ubuntu 可用性 | 均可。纯 Python（`pip install detect-secrets`），pre-commit hook 集成成熟 |
| Python 集成方式 | **可直接作为库导入**（唯一能 import 的主流引擎，Apache-2.0 允许）；也可 CLI 调用 `detect-secrets scan > .secrets.baseline`。核心概念：baseline（基线快照，只对新增 secrets 告警）+ filters（误报过滤器） |
| 默认联网行为 | **扫描本身离线（正则/熵/关键词），但验证默认开启**。官方文档明言："By default, `detect-secrets` will attempt to verify all secrets"；只有实现了 `verify()` 的插件会真发外呼（如 `AWSKeyDetector` 会 `requests.post('https://sts.amazonaws.com', …GetCallerIdentity, AWS SigV4 签名)`，用 requests 以免依赖 boto3）。`-n / --no-verify` 可关闭网络验证；`--only-verified` 只保留验证为真的结果。**集成时默认应加 `--no-verify`** |
| 规则数量与扩展 | `--list-all-plugins` 列出 **27 个插件**（AWSKey、AzureStorage、GitHubToken、GitLabToken、Slack、Stripe、Telegram、PrivateKey、Base64/Hex 高熵、KeywordDetector 等）。扩展：Python 继承 `RegexBasedDetector` 实现 `secret_type`/`patterns` 并注册插件，或通过 filters 增删误报规则——扩展成本最低 |

**JSON 输出样例**（baseline 格式；`results` 以文件路径为键，字段经 docs/audit.md 核实，值为示意）：

```json
{
  "generated_at": "2026-09-19T00:00:00+00:00",
  "plugins_used": [ { "name": "AWSKeyDetector" }, { "name": "KeywordDetector", "keyword_exclude": "" } ],
  "filters_used": [ { "path": "detect_secrets.filters.heuristics", "filters": ["is_potential_uuid"] } ],
  "results": {
    "config/settings.py": [
      { "type": "AWS Access Key", "filename": "config/settings.py",
        "hashed_secret": "513e0a36963ae1e8431c041b744679ee578b7c44",
        "is_verified": false, "line_number": 12 }
    ]
  },
  "version": "1.5.0"
}
```

**复用建议**：
- 复用：作为 Python **库**直接复用其插件框架与 baseline/filters 机制（宽松许可、可嵌入、增量扫描语义好），项目自研的国内云厂商（阿里/腾讯/华为等）正则可注册成它的自定义插件，从而白嫖其扫描调度与去重逻辑。
- 不复用：其在线验证能力默认关闭（只覆盖 AWS 等少数厂商，且外呼行为与本项目"受控验证"设计冲突）；它不含 APK/镜像源扫描。
- 许可证义务：Apache-2.0——保留 LICENSE/NOTICE 与版权声明；修改过的文件需带变更标注。注意其默认联网验证行为，集成时必须显式 `--no-verify`（库调用则为 `detect_secrets.settings` 相关开关，集成时验证开关以实测为准，**待核实**库级 API 的具体关法）。

---

## 4. Androguard 及 APK 静态分析 Python 库

**主选：Androguard**（github.com/androguard/androguard）

| 字段 | 结论 |
| --- | --- |
| 官方仓库 / 文档 | https://github.com/androguard/androguard ；文档：GitHub Pages（更新中），ReadTheDocs 已过时（README 明示） |
| 调研日期 | 2026-09-19 |
| 最新版本 / 发布时间 | **4.1.4，2026-06-01**（PyPI 核实；GitHub Releases 页面本次渲染不完整，以 PyPI 为准） |
| 许可证 | **Apache-2.0**（Androguard 与 DAD 反编译器同许可） |
| 维护状态 | 复活后缓慢维护：4.x 是"隔多年后的新版本"，约 6.3k stars；`ng` 分支开发下一代版本；被 MobSF 等项目依赖 |
| Windows / Ubuntu 可用性 | 均可。`pip install androguard`，要求 Python ≥ 3.9（classifiers 至 3.14）；纯 Python 为主，跨平台 |
| Python 集成方式 | **库导入为主**：`from androguard.misc import AnalyzeAPK` 可拿到 manifest 元信息、DEX 类/方法、字符串常量池、反汇编；另有 `androguard` CLI。4.x 相对 3.3.5 有功能删减，API 有变动 |
| 默认联网行为 | **纯离线**。本地解析 APK/DEX/AXML，无任何网络请求 |
| 规则数量与扩展 | 非规则型工具；扩展=基于其 API 自由编程（例如遍历 DEX 字符串常量池/资源文件后跑本项目自定义云凭据正则） |

**轻量备选：pyaxmlparser**（github.com/appknox/pyaxmlparser）
- 最新版本 **0.3.31（2024-03-20）**，Apache-2.0，Python 3 库：只解析 APK manifest/图标/签名等元数据（`from pyaxmlparser import APK`），无 DEX 反汇编；维护同样偏慢。
- 另一常见替代 apkutils2 未在本次核实（**待核实**）。

**复用建议**：
- 复用：Androguard 做库导入，负责"APK 解包→DEX 字符串/资源→喂给本项目统一凭据检测管线"；比自研 APK/DEX 解析省一个数量级工作量。
- 不复用：其规则/报告层（本来也没有）；敏感字符串定位需自研。
- 许可证义务：Apache-2.0，保留 LICENSE/NOTICE 即可；注意 4.x API 不稳定，建议锁定版本号并在 requirements 固定。

---

## 5. 容器镜像层解析的 Python 可用方案

按"是否需要 Docker daemon / 是否纯 Python"分四类（版本均于 2026-09-19 核实）：

| 方案 | 版本/时间 | 许可证 | 特点 | Python 集成 |
| --- | --- | --- | --- | --- |
| **docker SDK for Python（docker-py）** | 7.2.0（2026-07-09，PyPI） | Apache-2.0 | 需要 Docker daemon；`client.images.get()/save()` 导出 docker-archive tar 后离线解析 | 库导入 |
| **python-dxf**（Docker Registry v2 客户端） | 12.1.1（2025-05-05，PyPI） | MIT | 纯 Python、**免 daemon** 直连 Registry v2，可取 manifest 与 layer blob（注意 PyPI 上 `dxf` 是 CAD 绘图库，装包名是 `python-dxf`） | 库导入 |
| **oras（oras-py）** | 0.2.43（2026-08-08，PyPI） | Apache-2.0 | OCI Registry as Storage：面向 OCI 制品/镜像的拉取客户端，支持 OCI layout | 库导入 + `oras` CLI |
| **直接实现 Registry HTTP API v2**（requests） | —（规范见 distribution/distribution 文档） | — | `GET /v2/<name>/manifests/<tag>`（带 Accept 头协商 schema2/OCI）→ 取 layer digest → `GET /v2/<name>/blobs/<digest>` 下载层 tar；实现成本低、依赖最少 | 库/自研 |
| **skopeo**（CLI，Go） | v1.24.1（2026-09-16） | Apache-2.0 | `skopeo copy docker://img dir:out` / `oci:out` / `docker-archive:out.tar`，免 daemon；Ubuntu 原生（apt），**Windows 无官方原生支持（经 WSL/容器，待核实）** | CLI 子进程 |
| **crane**（go-containerregistry，CLI） | v0.20~v0.22.1（最新 v0.22.1，2026-09-04） | Apache-2.0 | `crane pull img img.tar`、`crane export img fs.tar`、`crane manifest/blob`；官方资产含 Linux/macOS 多架构，**Windows 资产待核实**（发布页资产列表本次显示不全；可用 `go install` 自行编译） | CLI 子进程 |
| **docker save / 构建期导出** | — | — | `docker save img -o img.tar` 得 docker-archive（`manifest.json` 列出各层）；解析用 Python 标准库 `tarfile` | 库导入 |

**镜像层解析要点**（Python 侧实现参考）：
- docker-archive：`manifest.json` → `Config`（每层 diff_id）+ `Layers`（层 tar 路径）；层 tar 内文件用 `tarfile` 逐个解包扫描。
- OCI layout：`index.json` → `blobs/sha256/…` 下的 manifest → `layers[]`；需按 sha256 校验。
- 白出文件（whiteout）：层 tar 中的 `.wh.<name>`（目录为 `.wh..wh..opq`）表示删除/覆盖，**去重扫描时需处理**，否则会扫到已删除文件里的"幽灵凭据"（这也是"分层扫描比平铺扫描多报"的来源，可设计成特性：报告凭据出现在哪一层）。
- 在线验证一致性提醒：拉取镜像本身就是要访问 registry（预期网络行为）；解析 tar 为纯离线。
- 现成引擎对接：TruffleHog `trufflehog docker --image=…`（支持 registry/daemon/tarball）；Gitleaks 对解包后的层目录跑 `gitleaks dir`。

**复用建议**：
- 复用：推荐"**skopeo copy → OCI layout / docker-archive → Python tarfile 解析层**"或"python-dxf 直连 registry"两条路线（前者成熟稳定、后者纯 Python 部署最简）；TruffleHog 的 docker 子命令可作对照/交叉验证。
- 不复用：不建议本项目从零实现 registry 认证（token 交换、 bearer flow、私库镜像源）全链路——用成熟客户端兜底。
- 许可证义务：docker-py/oras/skopeo 均 Apache-2.0、python-dxf MIT，宽松；随附声明即可。crane/skopeo 以 CLI 进程调用无许可证传染问题。

---

## 专题 A：Gitleaks 自定义规则 gitleaks.toml 完整样例

Gitleaks 的规则文件字段：`id`（唯一标识）、`description`、`regex`（**Go 正则，不支持 lookahead/lookbehind**）、`secretGroup`（提取第几个捕获组作为"秘密"并对其做熵检验）、`entropy`（最小香农熵）、`path`（文件路径正则）、`keywords`（前置快速过滤词，**建议小写**）、`tags`；`[extend] useDefault = true` 可叠加内置默认规则且自定义优先。规则级 allowlist 自 v8.21.0 用 `[[rules.allowlists]]`，全局 allowlist 自 v8.25.0 用 `[[allowlists]]`。

```toml
# gitleaks-custom.toml —— 用法：gitleaks dir --config gitleaks-custom.toml ./target
# 或：gitleaks git --config gitleaks-custom.toml --report-format json --report-path report.json

title = "云凭据检验 自定义规则"

[extend]
useDefault = true        # 叠加 gitleaks 内置 ~165 条默认规则；自定义规则优先级更高
# disabledRules = ["generic-api-key"]   # 如需屏蔽某条默认规则

[[rules]]
id = "aliyun-access-key-id"
description = "阿里云 AccessKey ID（LTAI 前缀）"
regex = '''\b(LTAI)[A-Za-z0-9]{12,28}\b'''
secretGroup = 1
entropy = 3.0
keywords = ["ltai"]
tags = ["cloud", "aliyun"]

[[rules]]
id = "tencentcloud-secret-pair"
description = "腾讯云 SecretId / SecretKey 赋值上下文"
# 注意：Go 正则不支持 (?=...) / (?!...)，用上下文捕获组替代
regex = '''(?i)(?:secret[_-]?(?:id|key))["']?\s*[:=]\s*["']?([A-Za-z0-9/+=]{20,60})'''
secretGroup = 1
entropy = 3.2
keywords = ["secretid", "secretkey"]
tags = ["cloud", "tencent"]

[[rules]]
id = "generic-bearer-token"
description = "泛化 Bearer/Authorization 令牌"
regex = '''(?i)(?:authorization|bearer)["']?\s*[:=]\s*["']?([A-Za-z0-9\-_.~+/]{30,120})'''
secretGroup = 1
entropy = 3.5
keywords = ["authorization", "bearer"]
tags = ["generic"]

# 规则级白名单（v8.21.0+ 语法）：任一条件命中即忽略该 finding
[[rules.allowlists]]
description = "忽略示例值与文档占位符"
condition = "OR"
regexes = ['''(?i)example|placeholder|dummy|x{5,}''']
paths = ['''(^|/)test(s|data)?/''', '''\.md$''']
regexTarget = "secret"   # 对提取出的 secret 匹配（默认），可改为 match / line

# 全局白名单（v8.25.0+ 语法），优先级高于规则级，可用 targetRules 指定作用规则
[[allowlists]]
description = "忽略 CI 生成文件中的提交"
commits = ["known-safe-commit-sha"]
```

> 关键词机制说明：`keywords` 是进正则前的高效预筛（必须出现在匹配附近才进入完整匹配），**必须小写**书写（引擎内部按小写匹配）；`entropy` 只作用于 `secretGroup` 指定捕获组，可显著压制误报。

---

## 专题 B：TruffleHog 检测器 + 验证器架构与验证请求行为

**架构（据 v3 源码结构核实）**：
1. **Source（数据源）**：`git / github / docker / filesystem / s3 …` 各源一个子命令，负责取数据块（commit diff、镜像层、文件流）。
2. **Decoder**：对数据做 plain/hex/base64/utf16 等编码解码，产出候选字节流。
3. **Detector（检测器）**：每个检测器实现 `Detector` 接口，核心方法 `FromData(ctx, verify bool, data []byte) ([]detectors.Result, error)`；内部先做**关键词预筛**（`detectors.PrefixRegex`/keywords）、再跑正则、再按**香农熵**过滤（如 AWS 检测器用 `RequiredIdEntropy/RequiredSecretEntropy`）。部分检测器是"两段式"凭据（如 AWS key ID + secret key，配对成功才出结果），配对信息放 `RawV2`。
4. **Verifier（验证逻辑内嵌于检测器）**：当 `verify=true`（命令行默认 true）时，检测器直接用候选凭据构造对**真实云 API** 的请求：
   - 成功（2xx/SDK 无错）→ `Verified=true` 并附 `ExtraData`（账号、ARN、rotation guide 等）；
   - 明确拒绝（如 403 InvalidClientTokenId）→ `Verified=false` 无错误；
   - 网络错误/异常响应 → `Verified=false` 且带 `VerificationError`（对应 `--results=unknown`）。
5. **输出**：`--json` 逐行输出 `Result` 结构（见上文样例），`Redacted` 字段做脱敏展示。

**验证请求实例 1：GitHub（pkg/detectors/github，v1+ v2）**
- 请求：`GET https://api.github.com/user`
- 头：`Authorization: token <候选token>`、`Content-Type: application/json; charset=utf-8`
- 判定：2xx 且响应体能解析为 `UserRes` → **Verified=true**（另捕获 `X-OAuth-Scopes`、`github-authentication-token-expiration` 响应头）；非 2xx/解析失败 → Verified=false。v2 检测器正则覆盖 `ghp|gho|ghu|ghs|ghr|github_pat` 前缀令牌。

**验证请求实例 2：AWS（pkg/detectors/aws/access_keys）**
- 请求：`GET https://sts.amazonaws.com`（service=sts，region=us-east-1），调用 **STS GetCallerIdentity**，用候选 AccessKeyID/SecretKey 以 AWS SDK v2 静态凭据 + SigV4 签名（含 403 SignatureDoesNotMatch 单次重试的 AWS 特性 workaround）。
- 判定：GetCallerIdentity 成功 → **Verified=true**，ExtraData 附 `account/user_id/arn`；403 `InvalidClientTokenId` → Verified=false（键确定无效）；其他错误 → Verified=false + VerificationError。
- 附加行为：会比对 Thinkst canary token 列表、对形如哈希的"假 secret"直接按误报丢弃。

> 对本项目含义：TruffleHog 的验证是"拿凭据打真实 API"，等价于一次**成功的未授权登录尝试**。在大赛/生产场景对外网客户凭据做验证存在合规与风控问题（云厂商侧可能记录为可疑登录、可能触发审计告警），因此本项目应将"在线验证"设计为**白名单化、可关停、可自建端点的受控验证**：默认仅对用户提供授权的凭据验证，工程上可复用其"verified/unverified/unknown 三态 + VerificationError"语义，但实现自己的验证器（或以 `--no-verification` 跑 TruffleHog、验证交给本项目验证模块）。

---

## 横向对比速览

| | Gitleaks | TruffleHog | detect-secrets | Androguard | 镜像解析方案 |
| --- | --- | --- | --- | --- | --- |
| 语言/形态 | Go 单二进制 | Go 单二进制 | Python 库+CLI | Python 库 | Python 库 / Go CLI |
| 许可证 | MIT | **AGPL-3.0** | Apache-2.0 | Apache-2.0 | Apache-2.0/MIT |
| 最新版本（2026-09-19） | v8.30.1（2026-03-21） | v3.97.5（2026-09-16） | 1.5.0（2024-05-06） | 4.1.4（2026-06-01） | docker-py 7.2.0 / python-dxf 12.1.1 / oras 0.2.43 / skopeo v1.24.1 / crane v0.22.1 |
| 默认联网 | 否 | **是（验证默认开）** | 验证默认开（仅部分插件实际外呼） | 否 | 拉取层时访问 registry（预期） |
| Python 库化 | 否（CLI） | 否（CLI） | **是** | **是** | 是 |
| 规则/检测器量级 | ~165 内置规则 | 700+ 检测器 / 800+ 凭据类型 | 27 插件 | 非规则型 | — |
| 本项目角色 | Git/目录扫描引擎 | 在线验证引擎 + 对照引擎 | 插件框架/baseline 增量扫描 | APK→凭据检测的数据前置层 | 镜像→层 tar 的数据前置层 |

---

## 来源链接清单

**Gitleaks**
- 仓库 / Releases：https://github.com/gitleaks/gitleaks 、https://github.com/gitleaks/gitleaks/releases （v8.30.1，2026-03-21）
- README（安装/用法/自定义规则/JSON 字段）：https://github.com/gitleaks/gitleaks/blob/master/README.md
- 默认规则文件（约 165 条）：https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml
- v8.30.1 缺 release 页 issue：https://github.com/gitleaks/gitleaks/issues/2058

**TruffleHog**
- 仓库 / Releases：https://github.com/trufflesecurity/trufflehog 、https://github.com/trufflesecurity/trufflehog/releases （v3.97.5，2026-09-16）
- README（验证默认开、--results、子命令、700+ 检测器）：https://github.com/trufflesecurity/trufflehog/blob/main/README.md
- GitHub 检测器 v2 / v1（验证请求实现）：https://github.com/trufflesecurity/trufflehog/tree/main/pkg/detectors/github/v2 、https://github.com/trufflesecurity/trufflehog/blob/main/pkg/detectors/github/v1/github_old.go
- AWS 检测器（STS GetCallerIdentity 验证）：https://github.com/trufflesecurity/trufflehog/tree/main/pkg/detectors/aws/access_keys
- 官方文档（Configuration file reference，custom detectors YAML）：https://trufflesecurity.com/docs
- JSON 输出字段（二手佐证）：https://blog.windkube.com/visualize-trufflehog-findings 、https://www.blackhillsinfosec.com/rooting-for-secrets-with-trufflehog
- Kali 打包佐证：https://www.kali.org

**detect-secrets**
- 仓库 / PyPI：https://github.com/Yelp/detect-secrets 、https://pypi.org/project/detect-secrets/ （1.5.0，2024-05-06）
- 插件与验证默认行为（"By default … attempt to verify all secrets"）：https://github.com/Yelp/detect-secrets/blob/master/docs/plugins.md
- AWS 插件 verify 实现（sts.amazonaws.com）：https://github.com/Yelp/detect-secrets/blob/master/detect_secrets/plugins/aws.py
- 提交历史（2025-01-06 最后实质提交）：https://github.com/Yelp/detect-secrets/commits/master

**Androguard / APK**
- 仓库：https://github.com/androguard/androguard ；PyPI：https://pypi.org/project/androguard/ （4.1.4，2026-06-01）
- pyaxmlparser：https://pypi.org/project/pyaxmlparser/ （0.3.31，2024-03-20）

**容器镜像解析**
- docker SDK for Python：https://pypi.org/pypi/docker/7.2.0/json （7.2.0，2026-07-09）
- python-dxf：https://pypi.org/pypi/python-dxf/json （12.1.1，2025-05-05；注意与 CAD 库 `dxf` 区分）
- oras-py：https://pypi.org/pypi/oras/json （0.2.43，2026-08-08）
- skopeo：https://github.com/containers/skopeo/releases （v1.24.1，2026-09-16）
- crane（go-containerregistry）：https://github.com/google/go-containerregistry/releases （v0.22.1，2026-09-04）
- Docker Registry HTTP API v2 规范（参考）：https://github.com/distribution/distribution/blob/main/docs/spec/api.md

**待核实项汇总**（网络受限或页面未能抓取，未采信记忆值）：
1. TruffleHog custom detectors YAML 的完整字段规范（官方文档站页面未能直接抓取，仅确认机制存在）。
2. detect-secrets 库级 API 关闭验证的具体写法（`--no-verify` 为 CLI 已核实；库内 settings 开关未核实）。
3. crane 官方 Release 是否含 Windows 二进制（发布页资产列表本次显示不全）；skopeo 是否有 Windows 原生支持（一般经 WSL/容器）。
4. Androguard GitHub Releases 页面本次渲染不完整，版本号以 PyPI 为准；apkutils2 未核实。
5. detect-secrets baseline 顶层键 `generated_at/filters_used/plugins_used/version` 的完整 schema 未见单一权威文档页（audit.md 仅佐证结果条目字段）。
