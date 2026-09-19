# 需求与验收映射（REQUIREMENTS）

状态：已确认（来自用户需求 + 赛题要求），作为既定条件，不再反复询问。

## 1. 赛题要求 → 系统需求 → 验收位置

| 赛题要求 | 系统需求 | 验收位置 |
| --- | --- | --- |
| 多公开渠道检索泄露凭据 | 7 类渠道全部建设，插件化采集器 | SUPPORTED_CHANNELS.md 能力矩阵 |
| 支持尽可能多的凭据类型 | 规则注册表，类型/厂商/上下文/配对 | SUPPORTED_CREDENTIALS.md + tests |
| 分钟级发现 | 持续监控 + 增量轮询 + 时延统计 | 总览页时延分布、EVALUATION.md |
| 易于新增渠道 | Collector/Verifier/Rule 三个插件契约 | INTERFACES.md §插件契约 |
| 交付源码/技术说明书/渠道列表/类型列表 | 仓库 + TECHNICAL_MANUAL + 两份矩阵 | 交付清单核对 |

评价指标 → 统计口径（第 10 节）：渠道类别数与平台数分开、检测类型与可验证类型分开、
自动监控与导入扫描分开、实现状态与真实接入状态分开。

## 2. 已确认的用户需求（既定条件）

1. 后端与采集/检测逻辑用 Python（3.11+）。
2. 开发机 Windows 11 + Ubuntu 云服务器；Windows/Ubuntu 双端可运行。
3. 并发与扫描规模可配置，不绑定固定服务器。
4. 支持手动指定范围扫描 + 持续自动发现、增量采集。
5. 七类渠道全部属于建设范围（GitHub 完成不算项目完成）。
6. 凭据覆盖由本团队调研后提出并落实（见 SUPPORTED_CREDENTIALS.md）。
7. 发现→入库→展示；有效性验证为独立模块，默认不自动验证。
8. 支持手动单条验证、批量验证、可选开启的自动验证。
9. 验证仅判断认证有效性，不利用凭据做其他操作。
10. 单人使用，中文界面，不建多人/角色权限体系。
11. 界面与导出可选脱敏。
12. 采集账号/Token/接口地址在【设置】页配置，附配置指引。
13. 用户目前仅有自己的 GitHub 仓库可用于真实渠道测试。
14. Git 管理，每个可验证改动单独提交。
15. 先设计后实现；持续维护开发记录、部署文档、目录说明与 TODO。
16. 无固定截止时间，按阶段推进，每阶段可运行、可检查、可演示。

## 3. 关键业务规则（摘要，完整版见 MASTER_PROMPT.md）

- **时间模型**：source_published_at（需证据与可信度）/ source_updated_at / fetched_at /
  detected_at / first_seen_at / last_seen_at / verified_at 分开；未知公开时间存 null 显示"未知"；
  一律 UTC 存储，界面默认 Asia/Shanghai。
- **去重**：凭据实体（受保护指纹）与出现位置（location_hash）分离；
  同凭据多位置关联；重复扫描只更新 last_seen；不同账号/端点/组合不错误合并；
  失效/误报记录不自动删除。
- **验证状态机**：not_requested / queued / running / valid / invalid / inconclusive /
  missing_context / unsupported / rate_limited / network_error / error。
  401/403 不一律视为 invalid；限流/网络故障不算 invalid；每次验证追加历史。
- **验证合规**：最小认证操作；不枚举资源；不读业务数据；不经重定向泄露凭据；
  无合适验证器的类型标 unsupported，保留检测能力。
- **误报**：先保留候选再分级复核；忽略规则有作用范围与原因记录；
  "真实但失效"与"误报"是不同结论。
- **统计**：命中次数 / 去重凭据数 / 唯一位置数 / 疑似候选 / 人工确认 / 验证有效·失效·无法判断
  分别统计；复核状态、置信度、验证状态是三个独立维度。
- **脱敏**：默认脱敏；显示原文需显式操作并留审计；凭据原文与设置中的平台 Token 分开管理加密。

## 4. 验收标准（对应 MASTER_PROMPT 第十六节）

整体完成 = 核心流程可运行 + 七类渠道均有具体实现与清晰状态 + 主要类型有真实规则与正反样例
+ 验证默认关闭且合规 + 统计/去重/时间口径经测试 + 双平台部署可复现 + 文档与代码一致
+ Git/测试/任务状态可追溯 + 无宣传性虚报。
受外部条件限制无法验收的部分，交付"已实现部分 + 待验收项"清单。

## 5. 验收映射（需求 → 证据）

| 需求 | 证据 |
| --- | --- |
| 检测规则有效 | backend/tests/test_rules*.py（正反样例） |
| 去重/多位置 | backend/tests/test_dedup.py, test_pipeline_e2e.py |
| 采集器行为（分页/限流/认证过期） | backend/tests/test_collectors*.py（平台响应样例注入） |
| 验证语义与默认关闭 | backend/tests/test_verification*.py |
| 导出 CSV 注入防护/脱敏 | backend/tests/test_export.py |
| 端到端流程 | backend/tests/test_pipeline_e2e.py（API 层） |
| 浏览器自动化 | TODO 阶段5（工具就绪后补充，见 TODO T5.4） |
| 真实渠道（GitHub） | docs/DEMO.md 由用户执行，结果回填 EVALUATION.md |
