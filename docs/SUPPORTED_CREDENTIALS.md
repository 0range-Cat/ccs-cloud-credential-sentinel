# 凭据类型能力矩阵（SUPPORTED_CREDENTIALS）

> 更新：2026-09-19 阶段1完成。
> 口径：本矩阵只列**有真实规则**的类型（35 条规则 / 35 个类型，别名与变体已合并）；
> 规则文件：`backend/app/detection/rules/`（cloud / devplatform / services / keys_db 四组）。
> 检测状态：**offline_tested** = 有正反样例测试且注册表自检通过（tests/test_rules_registry.py）。
> 最小在线验证与检测状态分开报告；无验证器 ≠ 检测能力缺失。
> "验证器 planned" 指阶段4 按最小认证原则逐个接入（见 TODO T4.2）。

## 汇总

- 检测：35 条规则 / 35 个类型，全部 offline_tested（正反样例即测试）。
- 最小在线验证：1 个已实现并离线测试（GitHub PAT），3 个阶段4 优先接入，其余标 unsupported/planned。
- 每条规则含：稳定 ID、类型、厂商、版本、许可证、正则、上下文要求、占位符过滤、
  配对规格、基础置信度、正反样例。

## 云厂商（9）

| 类型 | 规则 ID | 检测 | 验证 | 说明 |
| --- | --- | --- | --- | --- |
| AWS Access Key ID | aws-access-key-id | offline_tested | planned（STS GetCallerIdentity） | 排除文档示例值 |
| AWS Secret Access Key | aws-secret-access-key | offline_tested | 同上 | 强上下文+AK 配对加成 |
| 阿里云 AccessKey ID | aliyun-access-key-id | offline_tested | planned | LTAI 前缀 |
| 阿里云 AccessKey Secret | aliyun-access-key-secret | offline_tested | planned | 上下文+AK 配对加成 |
| 腾讯云 SecretId | tencent-secret-id | offline_tested | planned | AKID 前缀 |
| 腾讯云 SecretKey | tencent-secret-key | offline_tested | planned | 上下文+配对加成 |
| Azure 存储账户密钥 | azure-storage-account-key | offline_tested | planned | 需 AccountName/域名上下文 |
| Azure AD 客户端密钥 | azure-ad-client-secret | offline_tested | planned | client_secret 上下文 |
| GCP 服务账号 JSON | gcp-service-account-json | offline_tested | planned | JSON 结构化解析+配对字段 |

## 代码与制品平台（7）

| 类型 | 规则 ID | 检测 | 验证 | 说明 |
| --- | --- | --- | --- | --- |
| GitHub PAT（ghp_/gho_/ghs_/ghu_/ghr_/github_pat_） | github-pat | offline_tested | **offline_tested**（GET /user） | 唯一已实现验证器 |
| GitLab PAT | gitlab-pat | offline_tested | planned（GET /api/v4/user） | |
| Gitee 私人令牌 | gitee-token | offline_tested | planned（GET /api/v5/user） | 上下文+32位十六进制 |
| npm 令牌 | npm-token | offline_tested | planned | |
| PyPI 令牌 | pypi-token | offline_tested | planned | |
| Hugging Face 令牌 | huggingface-token | offline_tested | planned | |
| Docker Hub PAT | dockerhub-token | offline_tested | planned | |

## AI / 邮件 / 短信 / OAuth（9）

| 类型 | 规则 ID | 检测 | 验证 | 说明 |
| --- | --- | --- | --- | --- |
| OpenAI API Key | openai-api-key | offline_tested | planned | T3BlbkFJ 结构 / sk-proj- / 上下文 |
| Anthropic API Key | anthropic-api-key | offline_tested | planned | sk-ant- |
| SendGrid API Key | sendgrid-api-key | offline_tested | planned | |
| Mailgun API Key | mailgun-api-key | offline_tested | planned | 需 mailgun 上下文 |
| Resend API Key | resend-api-key | offline_tested | planned | |
| Twilio Account SID | twilio-account-sid | offline_tested | planned | 配对加成 |
| Twilio Auth Token | twilio-auth-token | offline_tested | planned | 上下文+配对加成 |
| OAuth 客户端密钥（通用） | oauth-client-secret | offline_tested | planned | client_secret 上下文 |
| Google OAuth 客户端密钥 | google-oauth-client-secret | offline_tested | planned | GOCSPX- |

## 私钥 / 数据库 / 配置载体（10）

| 类型 | 规则 ID | 检测 | 验证 | 说明 |
| --- | --- | --- | --- | --- |
| 私钥块（RSA/EC/DSA/OpenSSH/PGP） | private-key-block | offline_tested | **unsupported**（无目标不尝试） | 标记加密状态；OpenSSH 加密状态标 unknown |
| 数据库连接串（MySQL/PG/MongoDB/Redis/MSSQL） | db-connection-url | offline_tested | **unsupported**（无法保证仅认证） | URL 语义解析+弱口令拒绝 |
| 配置文件通用密钥赋值 | generic-env-assignment | offline_tested | **unsupported**（弱特征） | KEY/TOKEN/SECRET 后缀+熵过滤 |
| 配置文件口令（弱特征） | password-with-context | offline_tested | **unsupported** | 低置信度 35，需人工复核 |
| Slack Token | slack-token | offline_tested | planned（auth.test） | |
| Telegram Bot Token | telegram-bot-token | offline_tested | planned（getMe） | |
| Stripe Live Key | stripe-live-key | offline_tested | planned | |
| Stripe Test Key | stripe-test-key | offline_tested | — | 低置信度 35 |
| 钉钉机器人 Webhook | dingtalk-webhook | offline_tested | **unsupported**（webhook 即凭据即可用，不做发送验证） | |
| 飞书/企业微信应用密钥 | feishu-wecom-secret | offline_tested | planned | |

## 统计口径说明

- "检测 offline_tested" 指规则在标注样本集上正例命中、反例不误报（见 EVALUATION.md §2），
  不等同于在真实平台数据上验证过精确率。
- 内置规则总数（35）不可宣传为"已验证可发现 35 类真实泄露"——真实渠道验收按渠道×类型
  在 EVALUATION.md 逐步回填。
- 验证状态 independent 于复核状态与置信度，三者不互相覆盖。
