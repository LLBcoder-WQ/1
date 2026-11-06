# 拾集商城

这是一个用于学习的电商项目，包含 Vue 前端和 FastAPI 后端，提供邮箱验证码登录、商品与库存管理、购物车、订单、优惠码和演示支付等功能。

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

## 主要接口

- `POST /api/auth/email-code`：发送邮箱验证码
- `POST /api/auth/email-code/verify`：验证邮箱验证码并登录
- `GET /api/auth/me`：获取当前登录用户
- `POST /api/auth/register`、`POST /api/auth/login`：旧版密码注册和登录接口
- `GET /api/categories`、`POST /api/categories`：查询和创建商品分类（创建需要管理员权限）
- `GET /api/products`、`GET /api/products/{id}`：查询商品
- `POST /api/products`、`PATCH /api/products/{id}`：创建和更新商品（需要管理员权限）
- `GET /api/admin/products`：查询全部库存商品（需要管理员权限）
- `GET /api/admin/orders`：查询最近订单，默认最多 50 条、上限 100 条，并包含买家邮箱（需要管理员权限）
- `POST /api/admin/orders/{id}/shipment`：登记承运商和物流单号（需要管理员权限）
- `POST /api/admin/orders/{id}/delivery`：将已发货订单标记为已送达（需要管理员权限）
- `GET /api/cart`、`POST /api/cart/items`、`DELETE /api/cart/items/{product_id}`：查看和修改购物车
- `POST /api/coupons`、`GET /api/coupons`、`PATCH /api/coupons/{id}`：管理优惠码（需要管理员权限）
- `POST /api/orders`：创建订单并填写配送信息
- `GET /api/orders`、`GET /api/orders/{id}`：查询自己的订单
- `POST /api/orders/{id}/cancel`：取消未付款订单
- `POST /api/orders/{id}/payment`：创建演示支付记录

创建订单时，系统会重新检查库存，并在同一个数据库事务中扣减库存、保存商品名称和价格快照、应用优惠码及清空购物车。顾客可以取消未付款订单，取消后会恢复库存和优惠码次数。订单记录会保留以供查询。

结账需要收件人姓名、电话、省市区和详细地址；邮政编码为可选项。应用启动时会为旧版 `orders` 表补上配送字段，不会删除旧订单；旧订单的配送信息为空。

管理员可以为已付款或待发货订单登记物流，并将运输中的订单标记为已送达。未付款或已取消的订单不能登记发货。当前演示支付不会将订单标记为已付款，因此无法通过正常流程继续发货。物流信息需要手动维护，不会自动同步快递状态。

演示支付仅创建待处理的支付记录，不会收取款项、确认支付或提供支付确认接口。项目不接入真实支付。

## 部署到 Render、Vercel 和 Supabase

项目支持分开部署：Render 运行 FastAPI 后端，Vercel 托管 Vue 前端，Supabase 提供 PostgreSQL 数据库。后端直接连接 PostgreSQL。不要把 Supabase 数据库凭据或 service-role key 放到 Vercel 或前端代码中。

1. 在 Supabase 创建项目，并复制 PostgreSQL **Session Pooler** 连接串。Render 后端建议使用连接池地址，并启用 SSL（`sslmode=require`）。如果数据库密码包含特殊字符，需要先进行 URL 编码。
2. 使用仓库中的 `render.yaml` Blueprint 在 Render 创建服务。在 Render 服务环境变量中设置 `SHOP_DATABASE_URL` 为 Supabase 连接串。Blueprint 会自动生成生产环境 JWT 密钥。
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

   命令会提示输入密码，输入内容不会显示。访问 `/health` 可检查 API 是否正常。应用首次启动时会自动创建缺失的表，并为旧订单表添加配送字段。

仓库中的 Render Blueprint 使用免费方案，服务在闲置时可能休眠。Supabase 数据库独立于 Render 服务运行。请定期备份数据库并测试恢复流程；免费方案的可用性、连接数和备份保留规则以服务商当前政策为准。妥善保管 Supabase 数据库密码和 Render 密钥。演示支付不会收款，也不会确认付款。

### 使用 Resend 发送邮箱验证码

前端使用 6 位邮箱验证码登录。在 Resend 中创建 API Key，并验证一个你拥有的发件域名。然后在 Render 服务环境变量中设置以下变量（不要添加到 Vercel）：

- `SHOP_RESEND_API_KEY`：Resend API Key。
- `SHOP_EMAIL_FROM`：已验证域名下的发件地址，例如 `拾集 <login@mail.example.com>`。

同一个邮箱每 60 秒最多发送一次验证码。验证码 10 分钟后过期，最多可尝试 5 次；数据库只保存带密钥的验证码哈希。首次验证成功会创建顾客账户；已有管理员账号也可以通过邮箱验证码登录，并保留管理员权限。设置好变量后，重新部署 Render。

Resend 免费额度和发件人域名验证要求以 Resend 当前政策为准。

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

这是一个学习项目，不是已完成商业合规审查的电商服务。除演示支付外，密码重置、自动物流、真实支付接入及各司法辖区的隐私和税务义务均未覆盖。

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
