# 凭据类型能力矩阵（SUPPORTED_CREDENTIALS）

> 口径：本矩阵只列**有真实规则**的类型；内置规则总数不等于此处数量（别名/变体合并计）。
> 检测状态：planned / implemented / offline_tested（有正反样例测试）。
> 最小在线验证：supported（有合规最小验证器）/ offline_tested / unsupported（无合规验证办法，保留检测）/
> planned（阶段4）。检测状态与验证状态分开报告。

| 凭据类型 | 厂商 | 规则 ID | 检测状态 | 最小在线验证 | 说明 |
| --- | --- | --- | --- | --- | --- |
| AWS Access Key ID | AWS | aws-access-key-id | 阶段1 | planned（STS GetCallerIdentity，阶段4） | 前缀 AKIA/ASIA |
| AWS Secret Access Key | AWS | aws-secret-access-key | 阶段1 | 同上 | 需上下文/配对 |
| GitHub PAT（经典/细粒度/OAuth/App） | GitHub | github-pat | 阶段1 | supported（GET /user，离线测试） | ghp_/github_pat_/gho_/ghs_ |
| GitLab PAT | GitLab | gitlab-pat | 阶段1 | planned（GET /api/v4/user） | glpat_ |
| Gitee 私人令牌 | Gitee | gitee-token | 阶段1 | planned（GET /api/v5/user） | 上下文+32位十六进制 |
| Slack Token | Slack | slack-token | 阶段1 | planned（auth.test） | xox[baprs]- |
| OpenAI API Key | OpenAI | openai-api-key | 阶段1 | planned | sk-…T3BlbkFJ 结构或上下文 |
| Anthropic API Key | Anthropic | anthropic-api-key | 阶段1 | planned | sk-ant- |
| 私钥块（RSA/EC/OpenSSH/DSA/PGP） | 通用 | private-key-block | 阶段1 | unsupported（不猜测目标） | 标记是否加密 |
| GCP 服务账号 JSON | Google | gcp-service-account-json | 阶段1 | planned | JSON 语义解析 |
| Azure 存储账户密钥 | Microsoft | azure-storage-account-key | 阶段1 | planned | 需 azure 上下文 |
| Azure AD 客户端密钥 | Microsoft | azure-ad-client-secret | 阶段1 | planned | 需 client_secret 上下文 |
| 阿里云 AccessKey ID | 阿里云 | aliyun-access-key-id | 阶段1 | planned | LTAI 前缀 |
| 阿里云 AccessKey Secret | 阿里云 | aliyun-access-key-secret | 阶段1 | planned | 需上下文 |
| 腾讯云 SecretId | 腾讯云 | tencent-secret-id | 阶段1 | planned | AKID 前缀 |
| 腾讯云 SecretKey | 腾讯云 | tencent-secret-key | 阶段1 | planned | 需上下文 |
| 数据库连接串（MySQL/PostgreSQL/MongoDB/Redis/SQLServer） | 通用 | db-connection-url | 阶段1 | unsupported（无法保证仅认证） | URL 语义解析+占位符过滤 |
| SMTP/邮件服务密钥（SendGrid/Mailgun/Resend/SMTP口令） | 多厂商 | email-provider-keys | 阶段1 | planned | 各自模式 |
| Twilio（SID+AuthToken 配对） | Twilio | twilio-pair | 阶段1 | planned | 配对规则 |
| OAuth 客户端密钥（含 Google GOCSPX- 等） | 多厂商 | oauth-client-secret | 阶段1 | planned | 需 client_secret 上下文 |
| 钉钉机器人 Webhook | 钉钉 | dingtalk-webhook | 阶段1 | unsupported（webhook 即可用） | URL 内 access_token |
| 飞书/企业微信应用密钥 | 飞书/企业微信 | feishu-wecom-secret | 阶段1 | planned | 上下文+32位 |
| Stripe Live Secret Key | Stripe | stripe-live-key | 阶段1 | planned | sk_live_ |
| Telegram Bot Token | Telegram | telegram-bot-token | 阶段1 | planned（getMe） | 数字:AA… |
| npm/PyPI/HuggingFace/Docker Hub Token | 各平台 | package-registry-tokens | 阶段1 | planned | 前缀特征 |
| .env/配置文件通用 KEY/TOKEN/SECRET/PASSWORD | 通用 | generic-env-assignment | 阶段1 | unsupported（弱特征） | 强上下文+熵+占位符过滤 |

> 阶段1完成后本表将更新为实际实现状态并附规则文件位置（backend/app/detection/rules/）。
> 阶段4 扩展：华为云 AK/SK、对象存储签名、更多 AI/短信服务等。
