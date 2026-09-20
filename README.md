# VerifyHub（仓库名 zhizhu）

产品名 **VerifyHub**；GitHub 仓库 https://github.com/Szchiji/zhizhu（历史/目录名 zhizhu，本 PR 不改仓名）。
对外文案以「平台登记」为准；`BRAND_*` / HeYanHQ 相关环境变量保持原样。

Telegram 平台身份登记与查询：小程序为主，机器人为辅。
充值后自动登记资料，群里 `@机器人 + 用户名` 出登记卡。
登记由本平台出具并可撤销，以机器人实时查询为准（非政府/第三方「官方」背书）。

仓库：https://github.com/Szchiji/zhizhu

## 现在能做什么

- 小程序：开通 / 查询 / 我的 / 管理
- Stars 发票 + USDT TRC20 轮询自动开通，提前续费叠加时效
- 开通后自动录入用户名 / ID / 姓名，可在「我的」里改
- 内联卡 + 私聊查询，品牌跟 BotFather 名字
- 后台可改价、收款地址、首页文案、续费提醒、强制订阅、补登记 / 拉黑

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
USDT_CONFIRM_SECRET=随机长串
TRONGRID_API_KEY=trongrid.io 免费 key
TOKEN_ENC_KEY=随机串
```

可选：`BRAND_NAME` `BRAND_TITLE` `不填则用机器人 getMe 名字`。

可选限流（进程内内存，重启清零；多副本各自计数）：

```
USDT_CONFIRM_IP_LIMIT=20
USDT_CONFIRM_IP_WINDOW=60
USDT_CONFIRM_CODE_LIMIT=10
USDT_CONFIRM_CODE_WINDOW=60
```

4. 启动命令（`Procfile` / `railway.toml`）会先跑迁移再起服务：

```
python -m app.migrate && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

5. `域名/healthz` 返回 `{"ok":true}`
6. BotFather：`/setinline` 、`/setjoingroups` 、`/setmenubutton` 可选
7. 发 `/start`，左下角「小程序」

## 数据库迁移（Alembic）

- 迁移目录：`alembic/versions/`；当前 head = 初始全量表结构（含 `admin_audits`）。
- **Railway**：每次进程启动执行 `python -m app.migrate` → 必要时对「已有表、无 alembic_version」的旧库自动 `stamp head`，再 `alembic upgrade head`。
- **本地 / 开发**：仍可用 lifespan 里的 `init_db()` / `create_all`（只增不改列）。也可用：

```
alembic upgrade head
# 或
python -m app.migrate
```

### 已有生产库如何 baseline（手动）

若自动 stamp 未跑、或你想手工对齐：

```
# 在已连上 DATABASE_URL 的环境里（Railway shell / 本地指向生产时务必谨慎）
alembic stamp head
```

含义：表已由历史 `create_all` 建好，只登记「当前 schema = head」，后续增量 migration 才会真正 `ALTER`/`CREATE`。
**不要**在空库上 stamp（空库应直接 `upgrade head`）。

## 测试

本地：

```
pip install -r requirements-dev.txt
pytest -q
```

CI：GitHub Actions（`.github/workflows/ci.yml`）在 push 到 `main` 以及所有 pull request 时自动跑 `pytest -q`（Python 3.12，与 `runtime.txt` 一致）。无需 secrets。

覆盖：`init_data` HMAC（合法通过 / 仅 user_id 拒绝）、`card_tpl` HTML 转义、USDT confirm 密钥未配置 fail-closed + 内存限流。不连真实 Telegram / 生产库。

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
- `POST /api/usdt/confirm` 必须配置 `USDT_CONFIRM_SECRET`；确认尝试写入应用日志，已知订单额外写入 `order_events`
- 管理端改价 / 确认订单 / 补登记 / 拉黑等写入 `admin_audits`（who / what / when / target）
