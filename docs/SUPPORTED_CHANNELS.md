# 渠道能力矩阵（SUPPORTED_CHANNELS）

> 更新：2026-09-19 阶段1完成。
> 口径：渠道类别 ≠ 具体平台；自动监控 ≠ 导入扫描（两者分开计，本地导入不虚增类别数）。
> 状态定义：planned（规划）/ implemented（代码已实现）/ offline_tested（离线测试通过，
> 平台响应样例注入）/ live_verified（真实接入验证通过，需用户账号条件）。

## 总览（7 类渠道 + 本地导入）

| 渠道类别 | 具体平台 | 状态 | 自动监控 | 导入/手动扫描 |
| --- | --- | --- | --- | --- |
| 代码托管 | GitHub | **offline_tested** | 仓库树轮询（阶段1 当前文件树；历史扫描阶段2） | 支持指定仓库 |
| 代码托管 | Gitee | planned（阶段2；内容/树接口调研确认匿名可用） | - | - |
| Wiki | MediaWiki 兼容 | planned（阶段2；recentchanges+rccontinue 游标调研可行） | - | - |
| 微博 | 微博 | planned（阶段2；**无合规公开检索接口**，需登录态，如实记录障碍） | - | - |
| 知识分享 | 博客园 RSS / Stack Overflow API | planned（阶段2；调研确认匿名可行） | - | - |
| 知识分享 | CSDN / 掘金 | planned（无官方接口，将以合规抓取单独评估，不虚报） | - | - |
| 知识分享 | 通用 RSS/Sitemap/URL | planned（阶段2） | - | - |
| 容器镜像 | OCI/Docker Registry 兼容 | planned（阶段3；Docker Hub 匿名 token 流程调研打通） | - | - |
| App | Android APK | planned（阶段3；Androguard 选型完成） | - | 上传扫描为输入能力 |
| 小程序 | 合法取得的产物 | planned（阶段3；**无合法公开获取途径**，仅上传/目录分析） | - | 上传扫描为输入能力 |
| 本地导入 | 本地目录 / 压缩包 | **offline_tested** | - | ✅ 支持 |

当前计入"具体平台数"：GitHub（离线测试通过，待真实接入验收）+ 本地目录/压缩包导入（不计入公开渠道）。

## 明细：GitHub（offline_tested，真实接入待用户执行 DEMO.md）

- 采集入口：REST `/repos/{owner}/{repo}` + `/git/trees/{branch}?recursive=1` + `/git/blobs/{sha}`。
- 认证：可选 Token（设置页配置，Fernet 加密）；匿名 60 次/小时、认证 5,000 次/小时（官方口径）。
- 支持内容：当前默认分支全部文本文件（大小≤配置上限、二进制自动跳过）。
  Gist/Issue/评论、Git 历史扫描：阶段2 扩展（TODO 已列）。
- 增量策略：`(source, blob_sha, path, content_hash)` 版本缓存 + fetched 记录；
  已见内容跳过（实测重复扫描 items_skipped=全部）。
- 已知限制（如实记录）：
  - 不假定 Code Search 实时完整（官方限制：10 次/分钟、单查询 1,000 条、需认证）——阶段1 未用 Code Search；
  - 树接口单次有截断阈值，`tree_truncated` 标记已透传到内容元数据；
  - 文件级公开时间不可得 → `published_confidence=none`，界面显示"未知"，不参与时延统计；
  - 本开发网络 `api.github.com` 403（共享出口 IP 配额），真实验收在用户环境按 docs/DEMO.md 执行。
- 测试方法：平台响应样例注入（tests/test_collectors.py）：
  happy path / 限流(403+配额头→优雅停止) / 401→认证失败语义 / 404 语义 / 仓库标识解析。

## 明细：本地导入（offline_tested）

- 本地目录（include/exclude 通配、大小上限、二进制跳过、系统目录排除）。
- 压缩包 zip/tar：内存逐成员读取；拒绝 `..`/绝对路径成员；跳过符号链接/设备文件；
  单文件上限 + 512MB 总量上限（防解压炸弹）。
- Git 仓库副本：按本地目录扫描工作区（`.git` 排除）；远程克隆阶段2 提供。
- 用途：分析入口与测试入口；界面与统计中单列，不计入公开渠道类别数。

## 真实接入验收状态

| 渠道 | 真实验收 | 依据 |
| --- | --- | --- |
| GitHub 公开发现 | **待用户执行** | docs/DEMO.md（用户仅有自己的仓库可用） |
| GitHub 在线验证 | 待用户配置自有测试凭据后执行 | 验证结果不发布到公开仓库 |
| 其余渠道 | 未开始（阶段2/3） | 外部账号/条件未提供，任务保留不放弃 |
