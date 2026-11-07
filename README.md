# 拾集商城

这是一个用于学习的电商项目，包含 Vue 前端和 FastAPI 后端，提供顾客与商家账号、头像和商品图片上传、店铺资料、商品详情、评论与收藏、商品与库存管理、购物车、订单、优惠码和演示支付等功能。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m app.seed_admin admin@example.com
uvicorn app.main:app --reload
```

创建管理员时，命令会提示输入密码，输入内容不会显示。启动后可访问 `/docs` 查看交互式 API 文档。

默认数据库为 SQLite，文件名是 `shop.db`。需要时可通过环境变量配置 `SHOP_DATABASE_URL` 和 `SHOP_SECRET_KEY`。默认密钥仅用于本地开发，生产环境会拒绝使用默认密钥。

## 账号与店铺功能

注册时可以选择顾客或商家身份，使用邮箱和密码登录，不需要邮箱验证码。注册商家时需填写店铺名称；之后可以维护店铺名称、地址和介绍。

登录后点击右上角账户图标，可以修改显示名称、上传头像、修改密码或注销账号。注销需要再次输入密码；订单记录保留并匿名化账户资料，商家的商品会下架。商家只能管理自己创建的商品；管理员仍可通过 `python -m app.seed_admin admin@example.com` 创建，并拥有管理权限。

同一邮箱 15 分钟内登录失败 5 次后会收到临时 `429` 限流；等待响应 `Retry-After` 指定时间后重试。同一邮箱每小时最多提交 5 次注册请求。限制由后端数据库共享。生产环境还应在托管平台或边缘防火墙设置 IP/全局请求速率限制；本项目的邮箱维度限制不能替代边缘防护。

如果用户忘记密码，项目不提供邮件自助找回。由可信管理员在 Render Shell 中重置现有账号密码，角色不会改变，旧令牌会失效：

```sh
python -m app.reset_password user@example.com
```

命令会要求输入两次新密码，至少 8 位且不会回显。若要创建或重置管理员账号，使用 `python -m app.seed_admin admin@example.com`。这两个命令都需要拥有后端 Shell 权限；不要将 Shell 访问权交给普通用户。

头像和商品图片使用 Supabase Storage 保存。上传支持 JPG、PNG 和 WebP，单张最大 5 MB。

商品卡片可以打开详情，查看店铺、库存和用户评价；登录后可以收藏商品。只有购买并完成演示付款的顾客可以评价，每个账号对同一商品保留一条可更新的评价，作者可以编辑或删除自己的评价。访客可查看公开评论，登录用户可以举报评论，管理员可以隐藏违规评论或驳回举报。商品、收藏和评论列表均支持分页。注销账号后，收藏会清除，历史评论会匿名保留。

## 主要接口

- `POST /api/auth/register`、`POST /api/auth/login`：注册和邮箱密码登录
- `GET /api/auth/me`：获取当前登录用户
- `PATCH /api/account/profile`、`POST /api/account/avatar`：更新账户资料和头像
- `PATCH /api/account/password`、`DELETE /api/account`：修改密码和注销账户
- `GET /api/account/export`：下载账户数据 JSON；需登录，只包含当前账号可访问的数据（商家导出还含本店履约订单配送资料）
- `GET/PATCH /api/merchant/store`：查询和更新商家店铺信息
- `GET /api/merchant/products`：查询自己的商品
- `POST /api/products/{id}/image`：上传商品图片
- `GET /api/categories`、`POST /api/categories`：查询和创建商品分类（创建需要管理员权限）
- `GET /api/products`、`GET /api/products/{id}`：查询商品
- `GET /api/products/{id}/reviews`、`GET /api/products/{id}/reviews/summary`：分页查看评论和评价统计
- `POST /api/products/{id}/reviews`、`DELETE /api/products/{id}/reviews/{review_id}`：购买并演示付款后发布/更新评价；作者可删除自己的评论
- `POST /api/products/{id}/reviews/{review_id}/reports`：举报评论（需要登录）
- `GET /api/admin/review-reports?status=open&limit=20&offset=0`：管理员按处理状态分页查看举报
- `PATCH /api/admin/review-reports/{id}`：管理员隐藏违规评论或驳回举报
- `GET /api/favorites`、`PUT/DELETE /api/products/{id}/favorite`：分页查看和管理当前账号的收藏
- `POST /api/products`、`PATCH /api/products/{id}`：商家管理自己的商品，管理员可管理全部商品
- `GET /api/merchant/products`：商家查询自己的商品，管理员查询全部商品
- `GET /api/admin/products`：查询全部库存商品（需要管理员权限）
- `GET /api/admin/orders`：查询最近订单，默认最多 50 条、上限 100 条，并包含买家邮箱（需要管理员权限）
- `GET /api/admin/orders?status=processing&search=buyer@example.com&limit=20&offset=0`：按订单状态、订单编号或邮箱搜索并分页，响应包含 `items` 和 `total`
- `POST /api/admin/orders/{id}/shipment`：登记承运商和物流单号（需要管理员权限）
- `POST /api/admin/orders/{id}/delivery`：将已发货订单标记为已送达（需要管理员权限）
- `GET /api/merchant/orders`：分页查看仅属于当前商家的履约订单
- `POST /api/merchant/orders/{id}/shipment`：商家仅能为自己的商品登记发货
- `POST /api/orders/{id}/demo-payment`：顾客确认演示付款，不产生真实收款
- `POST /api/orders/{id}/fulfillments/{fulfillment_id}/delivery`：顾客确认对应店铺商品已收货
- `GET /api/admin/merchants`、`PATCH /api/admin/merchants/{merchant_id}/status`：管理员查看商家并暂停或恢复商家账号
- `GET /api/cart`、`POST /api/cart/items`、`DELETE /api/cart/items/{product_id}`：查看和修改购物车
- `POST /api/coupons`、`GET /api/coupons`、`PATCH /api/coupons/{id}`：管理优惠码（需要管理员权限）
- `POST /api/orders`：创建订单并填写配送信息
- `GET /api/orders`、`GET /api/orders/{id}`：查询自己的订单
- `POST /api/orders/{id}/cancel`：取消未付款订单
- `POST /api/orders/{id}/payment`：创建演示支付记录

创建订单时，系统会重新检查库存，并在同一个数据库事务中扣减库存、保存商品名称和价格快照、应用优惠码及清空购物车。未付款订单默认 30 分钟后过期，可通过 `SHOP_ORDER_PAYMENT_EXPIRY_MINUTES` 配置为 5 到 1440 分钟。过期会将订单标记为「已超时」、恢复库存和优惠码次数，并取消待处理的演示付款。顾客也可以手动取消未付款订单。订单记录会保留以供查询。

结账需要收件人姓名、电话、省市区和详细地址；邮政编码为可选项。应用启动时会为旧版 `orders` 表补上配送字段，不会删除旧订单；旧订单的配送信息为空。

下单时会按商品所属店铺拆分履约记录；商家只能查看和发出自己店铺的商品，不会因此修改其他店铺的物流状态。管理员仍可协助整笔订单的发货和签收管理。顾客通过「演示确认付款」将订单推进到待发货状态，付款状态只用于学习和流程演示，不会收款。顾客可以按店铺确认收货。物流信息需要手动维护，不会自动同步快递状态。

项目不接入真实支付、真实支付网关或真实收款；演示确认不能作为实际交易或收款凭据。

## 部署到 Render、Vercel 和 Supabase

项目支持分开部署：Render 运行 FastAPI 后端，Vercel 托管 Vue 前端，Supabase 提供 PostgreSQL 数据库。后端直接连接 PostgreSQL。不要把 Supabase 数据库凭据或 service-role key 放到 Vercel 或前端代码中。

1. 在 Supabase 创建项目，并复制 PostgreSQL **Session Pooler** 连接串。Render 后端建议使用连接池地址，并启用 SSL（`sslmode=require`）。如果数据库密码包含特殊字符，需要先进行 URL 编码。
2. 使用仓库中的 `render.yaml` Blueprint 在 Render 创建服务。在 Render 服务环境变量中设置 `SHOP_DATABASE_URL` 为 Supabase 连接串；`SHOP_ORDER_PAYMENT_EXPIRY_MINUTES` 默认为 30 分钟。Blueprint 会自动生成生产环境 JWT 密钥。
3. 在 Vercel 导入此仓库，并将项目 **Root Directory** 设置为 `frontend`。使用 Vite 设置：构建命令为 `npm run build`，输出目录为 `dist`。添加以下环境变量：

   ```text
   VITE_API_BASE_URL=https://<你的-render-服务>.onrender.com
   ```

   设置或修改此变量后，需要重新部署 Vercel 前端。本地开发时，可将 `frontend/.env.example` 复制为 `frontend/.env.local` 并保持变量为空，这样 Vite 会将 API 请求代理到本地运行的 FastAPI。如果本地前端要直接访问 Render API，还需要把 `http://localhost:5173` 加到 Render 的 `SHOP_CORS_ORIGINS`。
4. 将 Vercel 生产环境的完整站点来源填入 Render 服务的 `SHOP_CORS_ORIGINS`，例如 `https://your-shop.vercel.app`。多个允许的来源用逗号分隔。只填写来源，不要添加路径。如果 Vercel 域名有变化，也要更新此设置。
5. Render 服务启动成功后，在 Render Shell 中创建第一个管理员：

   ```sh
   python -m app.seed_admin admin@example.com
   ```

   命令会提示输入密码，输入内容不会显示。访问 `/health` 可检查 API 和数据库连接。应用启动时会自动创建缺失的表，并对旧数据库进行幂等升级：补充所需账户、订单过期时间、订单商品和评论字段，并为旧订单生成店铺履约记录。升级不会删除订单或评论。

仓库中的 Render Blueprint 使用免费方案，服务在闲置时可能休眠。Supabase 数据库和 Storage 独立于 Render 服务运行。妥善保管 Supabase 数据库密码和 Render 密钥。演示支付不会收款，也不会确认付款。

### 订单过期任务、监控与备份

应用会在结账、查看订单和管理员查看订单时顺便处理过期订单。为确保长时间没有访问时也能及时释放库存，建议在 Render 控制台另建一个 Cron Job，使用相同代码仓库和 Python 环境，命令设置为：

```sh
python -m app.expire_orders
```

建议每 5 分钟运行一次，并配置与后端相同的 `SHOP_DATABASE_URL` 和 `SHOP_ORDER_PAYMENT_EXPIRY_MINUTES`。Cron Job 和运行频率可能涉及 Render 费用；部署前请查看 Render 当前定价。该命令可重复安全运行。

Render 的健康检查路径为 `/health`；成功响应同时确认 API 已启动且数据库可连接。Render Logs 会记录请求方法、路径、状态码和耗时，不记录请求正文、邮箱、地址或密码。可再配置外部可用性监控定期请求此地址，并在连续失败时通知你。应用不会收集真实支付或物流事件。

PostgreSQL 备份示例（需要安装 PostgreSQL 客户端工具 `pg_dump`；不要把连接串写入仓库或命令历史）：

```powershell
# 先从密码管理器安全设置 SHOP_DATABASE_URL；不要把真实连接串写进命令或脚本
pg_dump --format=custom --no-owner --file "shop-backup.dump" "$env:SHOP_DATABASE_URL"
Remove-Item Env:SHOP_DATABASE_URL
```

将备份保存在受访问控制的位置，并定期将其恢复到**独立的测试数据库**验证。Supabase 的自动备份与时间点恢复能力取决于当前套餐和服务政策；不要仅依赖免费套餐的默认保留。数据库备份不包含 Storage bucket 中的图片对象，图片需要单独导出或复制；也要检查并保存 Supabase Storage 配置。任何恢复操作前先确认目标数据库，切勿直接用测试恢复覆盖线上库。

修改密码会立即使该账号此前签发的登录令牌失效；重新登录后继续使用。

### 配置 Supabase Storage 图片上传

在 Supabase Storage 创建名为 `shop-images` 的 **Public bucket**（公开桶），用于头像和商品图片展示。然后在 Render 环境变量中设置：

- `SHOP_SUPABASE_URL`：Supabase 项目 URL。
- `SHOP_SUPABASE_SERVICE_ROLE_KEY`：Supabase 服务端密钥（仅保存在 Render，绝不放入 Vercel 或前端）。
- `SHOP_SUPABASE_STORAGE_BUCKET`：Storage bucket 名称，默认为 `shop-images`。

图片上传由后端校验格式和大小（单张不超过 5 MB）后写入 Supabase Storage。更换头像或商品图后会尝试清理旧对象；若清理失败，应用日志会提示，需检查 Storage bucket。设置变量并创建公开桶后，重新部署 Render。

## 可选：使用 Docker 部署

Docker Compose 会将前端和 API 构建到同一个镜像中，并将 SQLite 数据库保存在具名卷中：

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

将生成的随机字符串填入 `.env` 中的 `SHOP_SECRET_KEY`，然后启动应用：

```powershell
docker compose up --build -d
docker compose ps
```

默认访问地址为 `http://127.0.0.1:8000`。容器健康检查使用 `/health`。通过以下命令交互式创建第一个管理员：

```powershell
docker compose exec shop python -m app.seed_admin admin@example.com
```

容器重建后，数据库仍保存在 `shop_data` 卷中。请定期备份该卷、限制访问，并验证备份可以恢复。`SHOP_BIND_ADDRESS` 应设置为适合反向代理的地址；默认只监听本机地址。面向互联网部署时，请通过受维护的反向代理或托管平台终止 HTTPS，并配置防火墙。不要在公网直接暴露未加密的 HTTP 服务。

镜像使用非 root 用户运行，并要求提供明确的生产密钥。妥善保管 `.env` 文件；轮换密钥会导致现有登录令牌失效。镜像会在同一来源下提供构建后的 Vue 页面，Vite 代理仅供本地开发使用。

这是一个学习项目，不是已完成商业合规审查的电商服务。项目不接入邮件密码找回；管理员可通过 Render Shell 重置密码。自动物流、真实支付接入及各司法辖区的隐私和税务义务均未覆盖。部署后若允许填写真实姓名、电话或地址，请先制定并发布适用于实际运营地区的隐私说明；下文仅为学习项目的说明模板，不构成法律意见。

### 隐私说明模板（上线前请按实际情况修改）

> 本站为学习用途的商城演示。账号资料、头像、商品与评论，以及下单时提交的收件人姓名、电话和地址，会存储在项目配置的数据库和图片存储服务中，用于账号、店铺和订单演示。系统会为限制重复登录/注册尝试保存经密钥散列的邮箱标识，不保存该限流记录中的明文邮箱。管理员及处理订单的对应商家可能查看履约所需的收件信息。演示支付不会收款，也不会发送真实付款凭证。请勿提交非必要的真实敏感信息。
>
> 用户可在账户管理中导出当前账号可访问的 JSON 数据、修改资料/密码或申请注销。商家导出内容可能含本店订单收件信息，应按履约和隐私要求保护。注销后，订单记录为审计与订单历史保留并匿名化账户资料，商家商品下架；因此注销不代表所有交易记录立即物理删除。数据可能由托管服务商按其备份周期保留。隐私请求或疑问请联系：**[填写实际运营者的联系邮箱]**。

此模板必须替换为与你实际收集的数据、托管商、访问权限、保存期限、删除流程和联系方式一致的说明。若你不具备适用隐私义务的判断能力，不要在公开环境中收集真实用户数据。

### Render/Vercel/Supabase 部署后检查清单

使用**测试账号、虚构联系方式和测试商品**完成以下检查；不要在生产站点用真实付款信息或他人个人资料测试。无法从本地代码确认 Render、Vercel 与 Supabase 的线上环境是否已正确连接，因此每次部署后都要在平台上验证：

1. Render `/health` 返回 HTTP 200 且 `database` 为 `ok`；Render 日志没有启动、数据库迁移或密钥错误。
2. Vercel 页面可以加载商品/API；浏览器控制台无 CORS 错误，上传头像/商品图后可正常显示。
3. 使用测试顾客与商家账号分别登录；验证不同身份访问权限正确。在测试账号上输错密码 5 次后再尝试第 6 次，确认收到 429；等 `Retry-After` 指定时间后确认可正常登录。
4. 测试账号创建商品并设置库存；验证售罄与低库存提示、收藏、评论/举报筛选和管理员审核。
5. 用测试顾客创建订单并走完整演示流程：确认配送信息、演示付款、商家登记物流、顾客确认收货。演示支付不会收款。
6. 用独立测试订单确认未付款超时后库存和优惠码次数恢复；确认 Render Cron Job `python -m app.expire_orders` 成功运行并检查日志。
7. 验证账户 JSON 导出内容及注销行为。导出文件含个人与配送信息，应妥善保管并在测试后删除。
8. 按备份章节执行数据库备份，并只恢复到独立测试数据库验证；不要将测试恢复覆盖线上数据库。
9. 发生密码找回需求时，在 Render Shell 使用 `python -m app.reset_password user@example.com`；确认重置后旧令牌失效。不要将密码或数据库密钥写入工单、聊天、截图或仓库。
10. 顾客或商家重新打开订单页面时，若已有订单状态发生变化，页面会显示站内提示；没有邮件或实时推送，刷新/重新进入页面才会获取最新状态。

### 常见部署故障排查

- **API 健康检查失败**：先查看 Render Logs 中的启动异常；确认 `SHOP_DATABASE_URL` 使用正确的 Supabase PostgreSQL 连接串、密码已 URL 编码且 TLS 参数正确。
- **页面显示请求失败或浏览器报告 CORS**：确认 Vercel 环境变量 `VITE_API_BASE_URL` 指向 Render 服务根 URL，Render `SHOP_CORS_ORIGINS` 填写 Vercel 的完整来源（协议和域名，不含路径），修改后分别重新部署对应服务。
- **头像/商品图片上传失败**：确认 Supabase `shop-images` bucket 已创建，Render 上的 `SHOP_SUPABASE_URL` 与 service-role key 属于同一项目；service-role key 仅可放在 Render。
- **登录提示 429**：按响应头 `Retry-After` 等待；不要反复尝试。该限制按邮箱计数，不按 IP 计数；可额外在托管平台配置请求限流。
- **订单没有按时过期**：确认 Render Cron Job 使用同一数据库和 `SHOP_ORDER_PAYMENT_EXPIRY_MINUTES` 配置，并检查最近一次任务日志。
- **商家看不到订单/不能发货**：顾客需先完成演示付款；核对商品归属店铺以及订单履约状态。

## 运行测试

```powershell
python -m pytest
```

## 本地运行 Vue 前端

```powershell
cd frontend
npm install
npm run dev
```

请先在 `http://127.0.0.1:8000` 启动 FastAPI 后端。Vite 开发服务器会将 API 请求代理到 FastAPI；浏览器打开 Vite 输出的本地地址即可。管理员账号可在项目根目录执行 `python -m app.seed_admin admin@example.com` 创建。
