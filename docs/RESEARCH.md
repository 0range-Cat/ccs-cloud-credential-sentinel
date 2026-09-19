# 技术调研（RESEARCH）

调研日期：2026-09-19。详细数据与来源链接见子文档：
[research/draft-tools.md](research/draft-tools.md)（开源工具）、
[research/draft-platforms.md](research/draft-platforms.md)（平台接口）。
两份草稿均由调研子智能体逐项核实产生，无法核实的条目已标注"待核实"。

## 一、开源工具结论与复用决策

| 工具 | 版本/日期 | 许可证 | 关键事实 | 决策 |
| --- | --- | --- | --- | --- |
| Gitleaks | v8.30.1（2026-03-21） | MIT | 纯离线；约 165 条内置规则；CLI 子进程 + JSON 报告；`gitleaks git/dir/stdin` | **不作为内置主引擎**（D1）。其 git 历史扫描（`gitleaks git`）在阶段2 作为可选补充引擎通过子进程接入，结果转统一模型；自定义规则格式可作为导入适配目标 |
| TruffleHog | v3.97.5（2026-09-16） | AGPL-3.0 | 700+ 检测器；**验证默认开启**；Go 程序 | 仅借鉴其检测器/验证器设计；**严禁 import/复制其代码**（AGPL 传染）；因其默认在线验证与本项目"检测阶段禁用验证"冲突，不引入运行链路 |
| detect-secrets | 1.5.0 | Apache-2.0 | 27 插件；部分插件有 verify 外呼（如 AWS POST sts）；baseline 机制 | 借鉴 baseline/误报抑制思想；不引入运行时依赖，避免双引擎重叠 |
| Androguard | 4.1.4（2026-06-01） | Apache-2.0 | 纯 Python，APK 静态解析 | 阶段3 APK 采集器以库方式复用 |
| 镜像层方案 | docker-py 7.2.0 / python-dxf 12.1.1 / skopeo v1.24.1 / crane v0.22.1 | 各自 Apache-2.0 等 | OCI Distribution API 拉层 + tarfile 解析 | 阶段3 用 "registry API 取层 → Python tarfile 解析"，处理 `.wh.` whiteout |

**要点印证**：TruffleHog/detect-secrets 的在线验证默认行为说明"不因库自带验证功能就信任"的必要性；
本项目在 `detection/` 与 `pipeline.py` 中不调用任何验证逻辑，验证只存在于独立 `verification/` 模块。

## 二、平台接口结论（详见 draft-platforms.md）

| 渠道 | 可行性 | 要点（2026-09-19 核实） |
| --- | --- | --- |
| GitHub | 可行（建议 PAT） | REST 匿名 60 次/h（本机实测命中共享 IP 403）、认证 5,000 次/h；Code Search 强制认证、10 次/min、单查询 1,000 条上限；Events 约 300 条/90 天窗口；以 commit `since`/事件 id 做增量 |
| Gitee | 部分可行 | 内容/树接口匿名实测 200（base64 正文）；匿名搜索返回空数组；官方限速数字待核实 |
| MediaWiki | 可行 | 无需登录；`list=recentchanges` 实测 200；游标 `rccontinue`（实测样例值已记录） |
| 微博 | **不可行** | 无合规公开检索接口；需登录 Cookie；访客通道失效；不做任何绕过 |
| 博客园 | 可行 | `feed.cnblogs.com/blog/sitehome/rss` 实测 200 |
| Stack Overflow | 可行 | 免 key 匿名 `quota_max=300`/天；>30 req/s 丢包 |
| CSDN / 掘金 | 不可行（官方接口） | 无官方公开接口；如需覆盖将以合规网页抓取方式单独评估，不虚报为"已接入" |
| RSS/Sitemap | 可行 | feedparser 6.0.14（BSD-2-Clause）；sitemap 单文件 ≤50,000 URL/50MB，`lastmod` 作游标 |
| Docker Hub | 可行 | 匿名 token+manifest 实测打通；匿名 100 次拉取/6h（每 IPv4 或 /64） |
| ghcr.io | 待复核 | 匿名 token 实测 DENIED（疑似环境特异性） |
| 阿里云容器镜像 | 部分可行 | 标准 OCI 401 Bearer 匿名流程；限速待核实 |
| 微信/支付宝小程序 | **不可行** | 无合法公开获取他人小程序包的渠道；仅支持合法取得的产物上传/目录分析 |

对阶段1的影响：GitHub 采集器按"REST 树+blob、Token 可选、限流显式语义"实现（已实现）；
本机网络 403 属共享出口 IP 配额耗尽，真实验收按 docs/DEMO.md 在用户环境执行。

## 三、待核实清单（后续阶段补充）

1. GitHub tree 接口截断阈值（10 万条目）与 Events 90 天窗口的官方原文。
2. Gitee 官方限速数字与搜索接口认证要求。
3. CSDN RSS 是否完全失效。
4. ghcr.io 匿名 DENIED 是否为环境特异性。
5. 阿里云容器镜像匿名拉取限速。
6. detect-secrets 库级关闭验证的 API（若未来以库方式复用）。
7. skopeo/crane 的 Windows 原生二进制可用性（阶段3）。
8. apkutils2 与 detect-secrets baseline schema 权威定义。
