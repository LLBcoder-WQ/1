# FastAPI Shop

A small e-commerce application with a Vue storefront and FastAPI backend for authentication, catalog and inventory management, carts, orders, coupon discounts, and a replaceable payment gateway interface.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m app.seed_admin admin@example.com
uvicorn app.main:app --reload
```

The admin command prompts for a password without echoing it. Browse to `/docs` for the interactive API documentation. The default SQLite database is `shop.db`; configure `SHOP_DATABASE_URL` and `SHOP_SECRET_KEY` with environment variables when needed. The built-in secret is for local development only and is rejected in production mode.

## Main endpoints

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET /api/categories`, `POST /api/categories` (admin)
- `GET /api/products`, `GET /api/products/{id}`, `POST/PATCH /api/products` (admin)
- `GET /api/admin/products` (all inventory, admin)
- `GET /api/admin/orders` (latest 50 orders by default, maximum 100, with buyer email; admin)
- `POST /api/admin/orders/{id}/shipment` (record carrier and tracking number after payment; admin)
- `POST /api/admin/orders/{id}/delivery` (mark a shipped order delivered; admin)
- `GET /api/cart`, `POST /api/cart/items`, `DELETE /api/cart/items/{product_id}`
- `POST /api/coupons`, `GET /api/coupons`, `PATCH /api/coupons/{id}` (admin)
- `POST /api/orders` (checkout with delivery details), `GET /api/orders`, `GET /api/orders/{id}`, `POST /api/orders/{id}/cancel`
- `POST /api/orders/{id}/payment`

Checkout rechecks and atomically decrements product inventory, snapshots item names and prices, applies the coupon, and clears the cart in one database transaction. Customers may cancel unpaid orders to release inventory and coupon usage. Orders are retained for auditability.

Checkout requires a recipient name, phone number, region, and street address. An optional postal code is stored with the order snapshot. The application adds these columns to an existing `orders` table on startup; old orders remain intact and show no delivery details.

Administrators can record a carrier and tracking number for paid/processing orders, and mark shipped orders delivered. The API intentionally rejects shipment creation for unpaid or cancelled orders. The current demo payment never marks an order paid, so shipment workflows remain locked until a real payment integration is configured. Tracking is manual; courier events are not automatically synchronized.

The payment gateway is an intentionally non-settling demo adapter. It creates a pending payment reference only; it does not collect money, mark orders paid, or provide a payment confirmation endpoint. Replace `DemoPaymentGateway` with a verified provider integration before accepting real payments.

## Render + Vercel + Supabase deployment

The app supports a split deployment: Render runs the FastAPI API, Vercel hosts the Vue frontend, and Supabase provides PostgreSQL. The backend connects directly to PostgreSQL; do not put Supabase database credentials or service-role keys in Vercel or frontend code.

1. In Supabase, create a project and copy its PostgreSQL **Session pooler** connection string. Use the pooler for a persistent Render service, keep SSL enabled (`sslmode=require`), and URL-encode any special characters in the database password.
2. Deploy this repository to Render using the included `render.yaml` Blueprint. In the Render service environment, set `SHOP_DATABASE_URL` to that connection string. The Blueprint generates a production JWT secret automatically.
3. In Vercel, import the repository and set the project **Root Directory** to `frontend`. Use the Vite defaults (`npm run build`, output directory `dist`) and add this environment variable:

   ```text
   VITE_API_BASE_URL=https://<your-render-service>.onrender.com
   ```

   Redeploy the Vercel frontend after setting or changing the variable. For local development, copy `frontend/.env.example` to `frontend/.env.local` and leave it empty to use the Vite proxy to a locally running FastAPI server. To call the deployed Render API directly from localhost, also add `http://localhost:5173` to Render's `SHOP_CORS_ORIGINS`.
4. Copy the Vercel production origin (for example, `https://your-shop.vercel.app`) into the Render service's `SHOP_CORS_ORIGINS`. For multiple trusted frontend origins, separate them with commas. Include the exact origin, without a path; update this setting if your Vercel domain changes.
5. After the Render service is live, create the initial administrator from its Shell:

   ```sh
   python -m app.seed_admin admin@example.com
   ```

   The command prompts for the password without echoing it. Use `/health` to check API health. The first app startup creates missing tables and adds the shipping columns.

The included Render Blueprint uses the free plan, which may sleep when idle. Supabase manages the database independently from Render restarts. Back up the Supabase database and test restores; free-tier availability, connection limits, and backup retention depend on the providers' current plans. Keep the Supabase database password and Render secret private. The demo payment never collects or confirms money.

## Optional Docker deployment

Docker Compose builds the storefront and API into one image and stores the SQLite database in a named volume:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put the generated value in `.env` as `SHOP_SECRET_KEY`, then start the application:

```powershell
docker compose up --build -d
docker compose ps
```

The app is available at `http://127.0.0.1:8000` by default. `/health` is used for container health checks. Create the first administrator interactively with:

```powershell
docker compose exec shop python -m app.seed_admin admin@example.com
```

The database survives container recreation in the `shop_data` volume. Back up that volume regularly, restrict access to it, and test restoring backups. Set `SHOP_BIND_ADDRESS` only to an address appropriate for your reverse proxy; the default binds to localhost. For an internet-facing deployment, terminate HTTPS at a maintained reverse proxy or hosting platform, configure its firewall, and forward traffic to the app. Do not expose the app over plain HTTP on a public network.

The image runs as a non-root user and requires an explicit production secret. Keep `.env` private and rotate the secret deliberately (existing login tokens will stop working). The image serves the built Vue files from the same origin; the Vite proxy is only used for local development.

This is a learning project, not a fully compliant commercial storefront. The demo payment intentionally never collects or confirms money; email verification, password reset, automated shipping, production payment integration, and jurisdiction-specific privacy/tax obligations are out of scope.

## Tests

```powershell
python -m pytest
```

## Vue storefront

```powershell
cd frontend
npm install
npm run dev
```

Start the FastAPI server on `http://127.0.0.1:8000` first. The Vite development server proxies API requests to FastAPI; open the local URL printed by Vite. Create an administrator with `python -m app.seed_admin admin@example.com` from the project root.
