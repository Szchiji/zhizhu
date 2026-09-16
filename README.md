# 知蛛 / VerifyHub

Telegram 官方身份核验平台：客户绑定自己的 Bot Token，克隆出核验机器人。  
支持 7 天试用、Stars 月费、网站 USDT 年付。可部署到 Railway。

仓库：https://github.com/Szchiji/zhizhu

## 功能

- 平台机器人：试用、绑定 Token、Stars 发票、USDT 收银台链接
- 租户机器人：官方身份卡、弹窗确认、私聊按钮、转发消息比 User ID、内联发卡
- 到期后租户机器人只提示续费
- 管理员 `/confirm VH-XXXX` 手动确认 USDT 到账
- 管理员 `/setprice` 改价，不用重新部署

## Railway 部署

1. Railway 新建项目，从本仓库 GitHub 连接
2. 添加 **Postgres** 插件，会自动注入 `DATABASE_URL`
3. 给 Web 服务生成域名（Settings → Networking → Generate Domain）
4. 配置变量：

```
PLATFORM_BOT_TOKEN=平台机器人Token
WEBHOOK_BASE_URL=https://你的域名
PUBLIC_BASE_URL=https://你的域名
WEBHOOK_SECRET=随机长字符串
ADMIN_TG_IDS=你的Telegram数字ID
STARS_MONTHLY=500
USDT_YEARLY=99
USDT_CHAIN=trc20
USDT_ADDRESS=你的TRC20地址
USDT_CONFIRM_SECRET=随机字符串
TRIAL_DAYS=7
```

`TOKEN_ENC_KEY` 建议再填一串随机字符，专门用来加密客户 Token。

5. 部署完成后打开 `https://你的域名/healthz` 应返回 `{"ok":true}`
6. 在 Telegram 打开平台机器人发 `/start`

启动时会自动给平台机器人 `setWebhook` 到 `/wh/platform`。  
客户绑定 Token 后，平台会把客户机器人 webhook 设到 `/wh/t/{tenant_id}`。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，DATABASE_URL 可先用 sqlite:///./zhizhu.sqlite3
uvicorn app.main:app --reload --port 8080
```

本地 webhook 需要公网地址（cloudflared / ngrok）填进 `WEBHOOK_BASE_URL`。

## 客户怎么用

1. `/start` → 开始试用
2. `@BotFather /newbot`，把 Token 发给平台机器人
3. `/setid` `/setname` 校准官方身份（默认用绑定者当前账号）
4. 把 `@客户机器人` 发给朋友；或让朋友把可疑私聊转发给它
5. 试用结束选 Stars 月费或 USDT 年付

## USDT 确认

链上监听到账后可：

```bash
curl -X POST https://你的域名/api/usdt/confirm \
  -H 'content-type: application/json' \
  -d '{"secret":"USDT_CONFIRM_SECRET","code":"VH-XXXXXX","txid":"链上哈希"}'
```

或管理员对平台机器人发送：`/confirm VH-XXXXXX txid`

## 命令

平台机器人：

- `/start` `/status`
- `/setid <数字ID>`
- `/setname <显示名>`
- `/confirm <订单号> [txid]`（管理员）
- `/prices` 查看当前价格
- `/setprice stars 500`（管理员，改 Stars 月费）
- `/setprice usdt 99`（管理员，改 USDT 年付）
- `/setaddr <TRC20地址>`（管理员）
