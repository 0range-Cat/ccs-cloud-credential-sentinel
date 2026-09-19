# 渠道能力矩阵（SUPPORTED_CHANNELS）

> 口径：渠道类别 ≠ 具体平台；自动监控 ≠ 导入扫描。
> 状态定义：planned（规划）/ implemented（代码已实现）/ offline_tested（离线测试通过，平台响应样例注入）/
> live_verified（真实接入验证通过，需用户账号条件）。
> 本矩阵随实现更新，最后更新：阶段1完成后。

## 总览

| 渠道类别 | 具体平台 | 自动监控 | 导入/手动扫描 | 验证状态 |
| --- | --- | --- | --- | --- |
| 代码托管 | GitHub | offline_tested | offline_tested | 采集器离线测试通过；真实接入待用户执行 DEMO.md |
| 代码托管 | Gitee | planned | planned | 阶段2 |
| Wiki | MediaWiki 兼容 | planned | planned | 阶段2 |
| 微博 | 微博公开内容 | planned | - | 阶段2，受平台访问控制约束 |
| 知识分享 | CSDN/博客园/掘金/StackOverflow | planned | planned | 阶段2；通用 RSS/Sitemap/URL 计划同批 |
| 容器镜像 | OCI/Docker Registry 兼容 | planned | planned | 阶段3 |
| App | Android APK | planned（上传扫描） | planned | 阶段3 |
| 小程序 | 合法取得的产物 | planned | planned | 阶段3 |
| 本地导入 | 本地目录/Git 副本/压缩包 | - | 见实现状态 | 分析与测试入口，不虚增类别数 |

## 明细：GitHub（阶段1）

- 采集入口：REST API `/repos/{owner}/{repo}/git/trees/{branch}?recursive=1` + blobs。
- 认证：无 Token 可低频访问；Token 在设置页配置（GitHub PAT，加密存储）。
- 支持内容：当前分支文件树（文本）；Gist/Issue/历史提交为后续扩展（见 TODO）。
- 增量策略：以 HEAD commit sha + path + blob sha 作为版本缓存；未变化内容跳过。
- 已知限制（如实记录）：代码搜索接口有认证/配额要求且非实时完整；Events API 保留窗口有限；
  `api.github.com` 在当前开发网络环境下返回 403（2026-09-19 测试），真实接入验收需用户环境执行。
- 测试方法：平台响应样例注入（分页/限流/认证过期/异常格式）见 backend/tests/test_collector_github.py。

## 明细：本地导入（阶段1）

- 本地目录扫描、压缩包导入（zip/tar，防路径穿越/解压炸弹/符号链接）、Git 仓库副本（工作区文件）。
- 用途：分析入口与测试入口；在统计中单列，不计入公开渠道类别数。
