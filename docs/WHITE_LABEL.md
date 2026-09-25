# 白标 / 克隆机器人（White-label）

本文说明智蛛平台的 **会员租户 + 可选克隆机器人** 模型。这不是多租户组织 SaaS（无独立组织账号、经销商账单或自定义域名）。

## 概念

| 概念 | 含义 |
|------|------|
| **Tenant** | 以 Telegram 用户为 owner 的付费会员记录（套餐 / 到期 / 登记卡） |
| **克隆机器人** | 会员在 BotFather 创建的 Bot，把 Token 发给平台机器人后，平台加密存储并 `setWebhook` |
| **平台机器人** | 主站收款、管理、查询；克隆机走独立 Webhook |

## 环境变量

见 `.env.example`：

- `WEBHOOK_BASE_URL` — 公网 HTTPS 根地址
- `WEBHOOK_SECRET` — Telegram `secret_token`
- `TOKEN_ENC_KEY` — 加密 `Tenant.bot_token_enc`（缺省会回退平台 Token，生产务必单独配置）

Webhook 路径：`POST {WEBHOOK_BASE_URL}/wh/t/{tenant_id}`。

## 开通流程（用户侧）

1. 管理员在后台打开「克隆」开关（`clone_enabled`）。
2. 用户开通会员后，向**平台机器人**私聊粘贴 BotFather Token。
3. 平台 `getMe` → 写入 `bot_id` / `bot_username` / `bot_token_enc` → `setWebhook`。

## 管理后台（Wave 10）

小程序管理 → **克隆实例**：

- 列出已绑定 Token 的实例（机器人、主人 TG、套餐、到期、Webhook URL）
- **启用 / 停用**：停用写入 `clone_disabled_ids` 并尝试 `deleteWebhook`；启用反向 `setWebhook`
- **Webhook 状态**：只读调用 Telegram `getWebhookInfo`（非行情 API）

停用切断白标流量，**不**删除会员登记；会员到期仍由 `tenant_usable` 控制。

## 明确不做（本 MVP）

- 经销商 / 二级分销计费、Stripe 市场
- 自定义域名、独立组织 RBAC
- 把 Tenant 重写成「公司/工作区」实体

## 相关代码

- 绑定：`app/_pb_c10.txt` / `app/_pb_c11.txt`（`on_token`）
- 处理：`app/tenant_bot.py`、`POST /wh/t/{tenant_id}`
- 管理 API：`app/saas_clones.py` → `/api/mini/admin/clones`
