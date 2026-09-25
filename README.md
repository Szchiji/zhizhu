# VerifyHub

Telegram 身份登记平台：小程序为主，机器人为辅。
充值后自动登记资料，群里 `@机器人 + 用户名` 出平台登记卡。

仓库：https://github.com/Szchiji/zhizhu

## 现在能做什么

- 小程序：开通 / 查询 / 我的 / 管理
- Stars 发票 + USDT TRC20 轮询自动开通，提前续费叠加时效
- 开通后自动录入用户名 / ID / 姓名，可在「我的」里改
- 内联卡 + 私聊查询，品牌跟 BotFather 名字
- 后台可改价、收款地址、首页文案、续费提醒、强制订阅、补登记 / 拉黑

说明：这里的「登记」是本平台记录与查询，不是政府或第三方权威背书；卡片效力以机器人实时查询为准，平台可撤销。

## Railway

1. 连接本仓库，加 Postgres
2. Generate Domain
3. 环境变量：

```
PLATFORM_BOT_TOKEN=
WEBHOOK_BASE_URL=https://你的域名
PUBLIC_BASE_URL=https://你的域名
WEBHOOK_SECRET=随机串
ADMIN_TG_IDS=你的电报数字ID
USDT_ADDRESS=TRC20地址
TRONGRID_API_KEY=trongrid.io 免费 key
TOKEN_ENC_KEY=随机串
USDT_CONFIRM_SECRET=随机串
```

`POST /api/usdt/confirm` is rate-limited (IP + order code). Limits are **in-memory per process** by default. Set `REDIS_URL` to share the same counters across replicas; if Redis is unreachable at startup the app falls back to in-memory and logs a warning.


可选：`BRAND_NAME` `BRAND_TITLE` `不填则用机器人 getMe 名字`。

4. `域名/healthz` 返回 `ok` + `db` / `redis` / `usdt_watch`（见下方）
5. BotFather：`/setinline` 、`/setjoingroups` 、`/setmenubutton` 可选
6. 发 `/start`，左下角「小程序」

启动命令会先跑 `python -m app.migrate`（Alembic），再起 uvicorn。已有库若还没有 `alembic_version`，会自动 stamp 再升级。

## 开发与测试

```bash
pip install -r requirements-dev.txt
pytest -q
```

推送到 `main` 或开 PR 时，GitHub Actions（`.github/workflows/ci.yml`）会自动跑同一套 `pytest`。

## 闭环

1. 用户小程序付 Stars / USDT
2. 到账后订单变 active，资料自动写入
3. `我的` 可改姓名和卡片正文
4. 群里 `@机器人 用户名` 出卡
5. 管理员在小程序「管理」改价、确认订单、补登记、改首页

## 注意

- 小程序改完后先关再开，避免旧缓存
- 用户列表 / 订单列表要搜才出
- 首页文案保存后重新 `/start`
- USDT 确认密钥未配置时确认接口会 503

## Wave 3 — Growth / white-label

- **Public plans**: `GET /api/mini/plans` (no admin) returns the membership plan list.
- **Coupons**: tables `coupons` / `coupon_redemptions` (Alembic `a1b2c3d4e5f6`).
  - Admin: `GET/POST /api/mini/admin/coupons`
  - User redeem: `POST /api/mini/coupon/redeem` with `{"code":"..."}`.
- **Clone bot**: paid users paste a BotFather token into the platform bot when clone is enabled.
  Server encrypts `Tenant.bot_token_enc`, then `setWebhook` to `{WEBHOOK_BASE_URL}/wh/t/{tenant_id}`.
  Requires `WEBHOOK_BASE_URL`, `WEBHOOK_SECRET`, `TOKEN_ENC_KEY`.


## Wave 4 — Permissions

- Settings key `admin_roles`: JSON `{ "tg_id": "owner|ops|support" }`.
- Env `ADMIN_TG_IDS` default to **owner**. Caps: support=confirm/view; ops=price/users/export/…; owner=all.
- Admin APIs: `GET/POST /api/mini/admin/roles` (owner-only write).
- Mini confirm dialogs via `/mini-confirm.js` before sensitive actions.

## Wave 5 — UX

- `app/static_ver.py` → `MINI_ASSET_VER` (cache-bust for mini JS).
- After activation: one-shot DM + 「我的」onboarding banner if display_name/username empty.

## Wave 6 — Eng debt

- Chunk note: `docs/CHUNKED_SOURCES.md`; assemble: `python scripts/assemble_chunks.py admin|platform_bot`
- `/healthz`: `{ok, db, redis, usdt_watch}` (Redis optional; USDT last-check age when watcher ran)
- Settings backup: `GET /api/mini/admin/settings/export` (secrets redacted)
- Coupons / clone / multi-plan / REDIS_URL: see `.env.example` and Wave 3 section above

## Wave 10 — SaaS MVP (clone instances)

- Admin mini：**克隆实例** — list bound clone bots, membership read-only, enable/disable Webhook.
- Setting `clone_disabled_ids` (JSON int list); docs: `docs/WHITE_LABEL.md`.
- Still: Tenant = membership + optional clone. No reseller / Stripe / custom domains.

