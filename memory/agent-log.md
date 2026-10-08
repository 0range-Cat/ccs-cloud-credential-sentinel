# agent-log（跨会话唯一档案 · 一档制四区）

## 状态段

STATE: task=归档封存+GitHub推送 | level=L2-F | route=完整9步(轻量) | confirm=已问(推送GitHub经用户明示授权) | gates_passed=1 | last_errpath=—

- 权威承载=本文件 + AGENTS.md；归档快照=归档/（封存于 2026-10-08）。
- 项目状态：阶段0~5 全部可闭环项完成，74 项测试通过（2026-10-08 复核）；已归档封存待接手。
- 远程仓库：2026-10-08 首次推送 GitHub（origin）；此前项目纪律为不推送远程，该纪律自归档起由用户指令更新为"已推送"。

## 教训区（症状→根因→解决→预防）

- [2026-10-08] Git Bash 下 `pytest -q` 经管道 grep 可能吞掉结果行（输出缓冲差异）→ 直接跑 `python -m pytest` 取末行 passed 汇总 → 验证类命令避免再套 grep 管道取关键行。
- [历史沉淀] 平台类踩坑（维基 UA/MediaWiki revid/SO falsy/Gitee 限流/Docker Hub 307/GitHub push protection/alembic GBK）已固化在 docs/HANDOFF.md 环境事实节与 归档/06 §四，不再重复登记。

## 偏好段

- 语言：中文（标识符/术语除外）；Git 消息 feat/fix/docs/test/refactor/chore 前缀。
- 用户此前纪律"不推送远程、不改写历史"——2026-10-08 起例外：归档推送为用户明示要求（一次性），推送后继续遵守"不改写历史"。

## 流水区

- 2026-10-08 归档会话：全面摸底（24 commits / docs 18 份 / 代码约5000行 / 74 tests 复核通过 exit=0）→ 建 归档/ 九份文档（00~08）→ 同步 HANDOFF/INDEX 归档指针 → 建 memory/agent-log.md → 敏感扫描（git ls-files 无密钥；data/ 全部 gitignored；文案/ 6 PNG+笔记无敏感）→ 提交归档 → 推送 GitHub。
