from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, inspect, select, text

from app.config import Settings
from app.database import (
    Base,
    ensure_account_columns,
    ensure_merchant_fulfillments,
    ensure_order_shipping_columns,
    get_db,
)
from app.main import CORS_ALLOWED_METHODS, app
from app.models import Coupon, MerchantFulfillment, Order, OrderItem, Payment, Product, User
from app.order_expiration import expire_pending_orders
from app.security import hash_password, verify_password
from app.reset_password import reset_existing_account_password
from app.storage import MAX_IMAGE_SIZE, upload_public_image


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as session:
        session.add_all(
            [
                User(email="admin@example.com", password_hash=hash_password("admin-password"), role="admin"),
                User(email="buyer@example.com", password_hash=hash_password("buyer-password")),
            ]
        )
        session.commit()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def auth(
    client: TestClient,
    email: str,
    password: str,
    role: str = "customer",
) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password, "role": role},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def delivery_details() -> dict[str, str]:
    return {
        "recipient_name": "张三",
        "recipient_phone": "+86 138 0000 0000",
        "shipping_region": "浙江省 杭州市 西湖区",
        "shipping_address": "文三路 100 号 2 幢 301 室",
        "postal_code": "310012",
    }


def test_favorite_put_is_allowed_by_cross_origin_preflight():
    cors_app = CORSMiddleware(
        app,
        allow_origins=["https://shop.example"],
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=["Authorization", "Content-Type"],
    )
    with TestClient(cors_app) as cors_client:
        response = cors_client.options(
            "/api/products/1/favorite",
            headers={
                "Origin": "https://shop.example",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://shop.example"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_health_check_includes_database_readiness(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_login_is_throttled_after_repeated_failures(client: TestClient):
    payload = {"email": "buyer@example.com", "password": "incorrect-password"}
    for _ in range(5):
        assert client.post("/api/auth/login", json=payload).status_code == 401
    throttled = client.post("/api/auth/login", json={**payload, "password": "buyer-password"})
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) > 0


def test_successful_login_clears_recent_failed_attempts(client: TestClient):
    payload = {"email": "buyer@example.com", "password": "incorrect-password"}
    for _ in range(4):
        assert client.post("/api/auth/login", json=payload).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "buyer@example.com", "password": "buyer-password"},
    ).status_code == 200
    assert client.post("/api/auth/login", json=payload).status_code == 401


def test_registration_attempts_are_throttled_per_email(client: TestClient):
    payload = {"email": "limited@example.com", "password": "valid-password"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    for _ in range(4):
        assert client.post("/api/auth/register", json=payload).status_code == 409
    assert client.post("/api/auth/register", json=payload).status_code == 429


def test_account_data_export_contains_only_authenticated_users_data(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "EXPORT-1", "name": "Export item", "price": "12.00", "stock": 2},
        headers=admin,
    ).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=buyer)
    order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()

    exported = client.get("/api/account/export", headers=buyer)
    assert exported.status_code == 200
    data = exported.json()
    assert data["format"] == "shiji-account-export-v1"
    assert data["account"]["email"] == "buyer@example.com"
    assert data["orders"][0]["id"] == order["id"]
    assert data["orders"][0]["shipping_address"] == delivery_details()["shipping_address"]
    assert data["orders"][0]["items"][0]["product_name"] == "Export item"
    assert "buyer@example.com" not in str(client.get("/api/account/export", headers=admin).json()["orders"])


def test_admin_password_reset_preserves_role_and_invalidates_old_tokens():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    with TestingSession() as db:
        user = User(email="merchant@example.com", password_hash=hash_password("old-password"), role="merchant")
        db.add(user)
        db.commit()
        original_token_version = user.token_version

        assert reset_existing_account_password(db, user.email, "new-password")
        db.refresh(user)
        assert user.role == "merchant"
        assert user.token_version == original_token_version + 1
        assert verify_password("new-password", user.password_hash)
        assert not reset_existing_account_password(db, "missing@example.com", "new-password")
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_checkout_applies_coupon_deducts_stock_and_clears_cart(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    category = client.post("/api/categories", json={"name": "Books"}, headers=admin)
    assert category.status_code == 201
    product = client.post(
        "/api/products",
        json={
            "sku": "BOOK-1",
            "name": "Example book",
            "description": "",
            "price": "25.00",
            "stock": 4,
            "category_id": category.json()["id"],
        },
        headers=admin,
    )
    assert product.status_code == 201
    coupon = client.post(
        "/api/coupons",
        json={"code": "save10", "discount_type": "percent", "value": "10", "max_uses": 1},
        headers=admin,
    )
    assert coupon.status_code == 201
    assert client.post(
        "/api/cart/items",
        json={"product_id": product.json()["id"], "quantity": 2},
        headers=buyer,
    ).status_code == 200

    order = client.post(
        "/api/orders",
        json={"coupon_code": "save10", **delivery_details()},
        headers=buyer,
    )
    assert order.status_code == 201
    assert order.json()["subtotal"] == "50.00"
    assert order.json()["discount"] == "5.00"
    assert order.json()["total"] == "45.00"
    assert order.json()["recipient_name"] == "张三"
    assert order.json()["recipient_phone"] == "+86 138 0000 0000"
    assert order.json()["shipping_region"] == "浙江省 杭州市 西湖区"
    assert order.json()["shipping_address"] == "文三路 100 号 2 幢 301 室"
    assert order.json()["postal_code"] == "310012"
    admin_orders = client.get("/api/admin/orders", headers=admin)
    assert admin_orders.json()["items"][0]["recipient_phone"] == "+86 138 0000 0000"
    assert admin_orders.json()["items"][0]["shipping_address"] == "文三路 100 号 2 幢 301 室"
    assert client.get("/api/products/1").json()["stock"] == 2
    assert client.get("/api/cart", headers=buyer).json()["items"] == []
    admin_orders = client.get("/api/admin/orders", headers=admin)
    assert admin_orders.status_code == 200
    assert admin_orders.json()["total"] == 1
    assert len(admin_orders.json()["items"]) == 1
    assert admin_orders.json()["items"][0]["customer_email"] == "buyer@example.com"
    assert admin_orders.json()["items"][0]["items"][0]["product_name"] == "Example book"
    assert client.get("/api/admin/orders?limit=101", headers=admin).status_code == 422
    other_user = client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "other-password"},
    )
    assert other_user.status_code == 201
    other = auth(client, "other@example.com", "other-password")
    assert client.get(f"/api/orders/{order.json()['id']}", headers=other).status_code == 404


def test_checkout_rejects_invalid_recipient_phone(client: TestClient):
    buyer = auth(client, "buyer@example.com", "buyer-password")
    response = client.post(
        "/api/orders",
        json={
            **delivery_details(),
            "recipient_phone": "call me maybe",
        },
        headers=buyer,
    )
    assert response.status_code == 422


def test_admin_orders_are_filterable_and_paginated(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    order_ids = []
    for index in range(2):
        product = client.post(
            "/api/products",
            json={"sku": f"ADMIN-PAGE-{index}", "name": f"Paged order {index}", "price": "3.00", "stock": 1},
            headers=admin,
        ).json()
        client.post(
            "/api/cart/items",
            json={"product_id": product["id"], "quantity": 1},
            headers=buyer,
        )
        order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()
        order_ids.append(order["id"])
    assert client.post(f"/api/orders/{order_ids[1]}/cancel", headers=buyer).status_code == 200

    page = client.get("/api/admin/orders?limit=1&offset=0", headers=admin).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1
    assert page["offset"] == 0
    assert client.get(
        "/api/admin/orders?status=cancelled",
        headers=admin,
    ).json()["items"][0]["id"] == order_ids[1]
    assert client.get(
        "/api/admin/orders?status=not-a-status",
        headers=admin,
    ).status_code == 422
    assert client.get(
        "/api/admin/orders?search=buyer%40example.com",
        headers=admin,
    ).json()["total"] == 2
    search_result = client.get(
        f"/api/admin/orders?search={order_ids[0]}",
        headers=admin,
    ).json()
    assert search_result["total"] == 1
    assert search_result["items"][0]["id"] == order_ids[0]


def test_unpaid_order_expiry_restores_stock_and_coupon_once():
    test_engine = create_engine("sqlite://")
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=test_engine)
    try:
        now = datetime.now(timezone.utc)
        with TestingSession() as db:
            buyer = User(email="expiry@example.com", password_hash=hash_password("test-password"))
            product = Product(
                sku="EXPIRY-1",
                name="Expiring item",
                price="10.00",
                stock=0,
            )
            coupon = Coupon(
                code="EXPIRY10",
                discount_type="fixed",
                value="1.00",
                uses_count=1,
            )
            db.add_all([buyer, product, coupon])
            db.flush()
            order = Order(
                user_id=buyer.id,
                status="pending_payment",
                subtotal="10.00",
                discount="1.00",
                total="9.00",
                coupon_code="EXPIRY10",
                created_at=now - timedelta(hours=1),
                expires_at=now - timedelta(minutes=1),
                items=[],
                fulfillments=[],
            )
            db.add(order)
            db.flush()
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name="Expiring item",
                    unit_price="10.00",
                    quantity=2,
                )
            )
            fulfillment = MerchantFulfillment(
                order_id=order.id,
                seller_id=None,
                status="pending_payment",
            )
            payment = Payment(
                order_id=order.id,
                provider="demo",
                provider_reference="expiry-payment",
                status="pending",
            )
            db.add_all([fulfillment, payment])
            legacy_order = Order(
                user_id=buyer.id,
                status="pending_payment",
                subtotal="10.00",
                discount="0.00",
                total="10.00",
                created_at=now - timedelta(minutes=31),
                expires_at=None,
                items=[],
                fulfillments=[],
            )
            db.add(legacy_order)
            db.flush()
            db.add(
                OrderItem(
                    order_id=legacy_order.id,
                    product_id=product.id,
                    product_name="Legacy expiring item",
                    unit_price="10.00",
                    quantity=3,
                )
            )
            legacy_fulfillment = MerchantFulfillment(
                order_id=legacy_order.id,
                seller_id=None,
                status="pending_payment",
            )
            legacy_payment = Payment(
                order_id=legacy_order.id,
                provider="demo",
                provider_reference="legacy-expiry-payment",
                status="pending",
            )
            db.add_all([legacy_fulfillment, legacy_payment])
            db.commit()
            order_id = order.id
            legacy_order_id = legacy_order.id

            assert expire_pending_orders(db, now=now) == 2
            db.expire_all()
            assert db.get(Order, order_id).status == "expired"
            assert db.get(Order, legacy_order_id).status == "expired"
            assert db.get(Product, product.id).stock == 5
            assert db.get(Coupon, coupon.id).uses_count == 0
            assert db.scalar(select(Payment.status).where(Payment.order_id == order_id)) == "cancelled"
            assert db.scalar(
                select(MerchantFulfillment.status).where(MerchantFulfillment.order_id == order_id)
            ) == "expired"
            assert expire_pending_orders(db, now=now) == 0
            assert db.get(Product, product.id).stock == 5
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_customer_cannot_manage_products_and_order_is_private(client: TestClient):
    buyer = auth(client, "buyer@example.com", "buyer-password")
    assert client.post(
        "/api/products",
        json={"sku": "X", "name": "X", "price": "1.00", "stock": 1},
        headers=buyer,
    ).status_code == 403
    assert client.get("/api/orders/999", headers=buyer).status_code == 404
    assert client.get("/api/admin/products", headers=buyer).status_code == 403
    assert client.get("/api/admin/orders", headers=buyer).status_code == 403


def test_admin_inventory_includes_inactive_products(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    product = client.post(
        "/api/products",
        json={"sku": "HIDDEN", "name": "Hidden product", "price": "1.00", "stock": 1},
        headers=admin,
    ).json()
    assert client.patch(
        f"/api/products/{product['id']}",
        json={"is_active": False},
        headers=admin,
    ).status_code == 200
    inventory = client.get("/api/admin/products", headers=admin)
    assert inventory.status_code == 200
    assert inventory.json()[0]["is_active"] is False


def test_checkout_rejects_insufficient_stock_without_mutating_cart(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "LOW", "name": "Low stock", "price": "1.00", "stock": 1},
        headers=admin,
    ).json()
    client.post(
        "/api/cart/items",
        json={"product_id": product["id"], "quantity": 2},
        headers=buyer,
    )
    response = client.post("/api/orders", json=delivery_details(), headers=buyer)
    assert response.status_code == 409
    assert client.get("/api/cart", headers=buyer).json()["items"][0]["quantity"] == 2
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 1


def test_payment_creation_is_idempotent_for_pending_order(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "PAY", "name": "Payment test", "price": "2.50", "stock": 2},
        headers=admin,
    ).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=buyer)
    order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()
    first = client.post(f"/api/orders/{order['id']}/payment", headers=buyer)
    second = client.post(f"/api/orders/{order['id']}/payment", headers=buyer)
    assert first.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["provider"] == "demo"


def test_cancelling_unpaid_order_restores_stock_and_coupon_usage(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "CANCEL", "name": "Cancel test", "price": "10.00", "stock": 3},
        headers=admin,
    ).json()
    coupon = client.post(
        "/api/coupons",
        json={"code": "once", "discount_type": "fixed", "value": "2.00", "max_uses": 1},
        headers=admin,
    ).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 2}, headers=buyer)
    order = client.post(
        "/api/orders",
        json={"coupon_code": "once", **delivery_details()},
        headers=buyer,
    ).json()
    cancelled = client.post(f"/api/orders/{order['id']}/cancel", headers=buyer)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 3
    assert client.get("/api/coupons", headers=admin).json()[0]["uses_count"] == 0
    assert client.post(f"/api/orders/{order['id']}/cancel", headers=buyer).status_code == 200
    assert client.get("/api/coupons", headers=admin).json()[0]["uses_count"] == 0


def test_percent_coupon_cannot_be_updated_above_one_hundred(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    coupon = client.post(
        "/api/coupons",
        json={"code": "percent", "discount_type": "percent", "value": "20"},
        headers=admin,
    ).json()
    response = client.patch(
        f"/api/coupons/{coupon['id']}",
        json={"value": "101"},
        headers=admin,
    )
    assert response.status_code == 422


def test_legacy_orders_table_gets_shipping_columns_idempotently():
    legacy_engine = create_engine("sqlite://")
    try:
        with legacy_engine.begin() as connection:
            connection.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO orders (id) VALUES (7)"))

        ensure_order_shipping_columns(legacy_engine)
        ensure_order_shipping_columns(legacy_engine)

        columns = {column["name"] for column in inspect(legacy_engine).get_columns("orders")}
        assert {
            "recipient_name",
            "recipient_phone",
            "shipping_region",
            "shipping_address",
            "postal_code",
            "shipping_carrier",
            "tracking_number",
            "shipped_at",
            "delivered_at",
        }.issubset(columns)
        shipping_types = {
            column["name"]: column["type"]
            for column in inspect(legacy_engine).get_columns("orders")
        }
        assert "TIMESTAMP" in str(shipping_types["shipped_at"]).upper()
        with legacy_engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM orders WHERE id = 7")).one()
            assert row.id == 7
            assert row.recipient_name is None
            assert row.tracking_number is None
    finally:
        legacy_engine.dispose()


def test_legacy_account_columns_are_added_idempotently():
    legacy_engine = create_engine("sqlite://")
    try:
        with legacy_engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255))"))
            connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, sku VARCHAR(64))"))
            connection.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY)"))
        ensure_account_columns(legacy_engine)
        ensure_account_columns(legacy_engine)
        user_columns = {column["name"] for column in inspect(legacy_engine).get_columns("users")}
        product_columns = {column["name"] for column in inspect(legacy_engine).get_columns("products")}
        assert {"display_name", "avatar_url", "is_suspended"}.issubset(user_columns)
        assert "token_version" in user_columns
        assert {"image_url", "seller_id"}.issubset(product_columns)
        assert "expires_at" in {column["name"] for column in inspect(legacy_engine).get_columns("orders")}
    finally:
        legacy_engine.dispose()


def test_legacy_order_items_get_seller_snapshot_and_fulfillments_idempotently():
    legacy_engine = create_engine("sqlite://")
    try:
        with legacy_engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255))"))
            connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, seller_id INTEGER)"))
            connection.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, status VARCHAR(20))"))
            connection.execute(
                text("CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER)")
            )
            connection.execute(
                text(
                    "CREATE TABLE merchant_fulfillments ("
                    "id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, seller_id INTEGER, "
                    "status VARCHAR(20), shipping_carrier VARCHAR(80), tracking_number VARCHAR(100), "
                    "shipped_at TIMESTAMP, delivered_at TIMESTAMP, UNIQUE(order_id, seller_id))"
                )
            )
            connection.execute(text("INSERT INTO users (id, email) VALUES (9, 'seller@example.com')"))
            connection.execute(text("INSERT INTO products (id, seller_id) VALUES (3, 9)"))
            connection.execute(text("INSERT INTO orders (id, status) VALUES (5, 'pending_payment')"))
            connection.execute(text("INSERT INTO order_items (id, order_id, product_id) VALUES (7, 5, 3)"))

        ensure_account_columns(legacy_engine)
        ensure_order_shipping_columns(legacy_engine)
        ensure_merchant_fulfillments(legacy_engine)
        ensure_merchant_fulfillments(legacy_engine)

        with legacy_engine.connect() as connection:
            item_seller_id = connection.execute(
                text("SELECT seller_id FROM order_items WHERE id = 7")
            ).scalar_one()
            fulfillment_count = connection.execute(
                text("SELECT count(*) FROM merchant_fulfillments WHERE order_id = 5")
            ).scalar_one()
            assert item_seller_id == 9
            assert fulfillment_count == 1
    finally:
        legacy_engine.dispose()


def test_product_search_and_favorite_lists_are_paginated(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product_ids = []
    for index in range(3):
        response = client.post(
            "/api/products",
            json={
                "sku": f"PAGE-{index}",
                "name": f"Paged item {index}",
                "description": "special phrase" if index == 2 else "",
                "price": "4.00",
                "stock": 1,
            },
            headers=admin,
        )
        assert response.status_code == 201
        product_ids.append(response.json()["id"])
        assert client.put(
            f"/api/products/{response.json()['id']}/favorite",
            headers=buyer,
        ).status_code == 200

    first_page = client.get("/api/products?limit=2&offset=0")
    second_page = client.get("/api/products?limit=2&offset=2")
    assert len(first_page.json()) == 2
    assert [item["id"] for item in second_page.json()] == [product_ids[2]]
    assert [item["id"] for item in client.get("/api/products?search=special%20phrase").json()] == [product_ids[2]]
    assert len(client.get("/api/favorites?limit=2&offset=0", headers=buyer).json()) == 2
    assert [item["id"] for item in client.get("/api/favorites?limit=2&offset=2", headers=buyer).json()] == [product_ids[0]]


def test_shipping_is_blocked_until_payment_and_tracking_is_visible_to_customer(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "SHIP", "name": "Shipping test", "price": "9.90", "stock": 2},
        headers=admin,
    ).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=buyer)
    order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()

    shipment_payload = {"shipping_carrier": "  Example Express  ", "tracking_number": "  TRK-123  "}
    blocked = client.post(
        f"/api/admin/orders/{order['id']}/shipment",
        json=shipment_payload,
        headers=admin,
    )
    assert blocked.status_code == 409
    assert client.post(
        f"/api/admin/orders/{order['id']}/delivery",
        headers=admin,
    ).status_code == 409
    assert client.post(
        f"/api/admin/orders/{order['id']}/shipment",
        json=shipment_payload,
        headers=buyer,
    ).status_code == 403

    session_generator = app.dependency_overrides[get_db]()
    session = next(session_generator)
    try:
        db_order = session.get(Order, order["id"])
        assert db_order is not None
        db_order.status = "processing"
        session.commit()
    finally:
        session_generator.close()

    shipped = client.post(
        f"/api/admin/orders/{order['id']}/shipment",
        json=shipment_payload,
        headers=admin,
    )
    assert shipped.status_code == 200
    assert shipped.json()["status"] == "shipped"
    assert shipped.json()["shipping_carrier"] == "Example Express"
    assert shipped.json()["tracking_number"] == "TRK-123"
    assert shipped.json()["shipped_at"] is not None
    assert client.get("/api/orders", headers=buyer).json()[0]["tracking_number"] == "TRK-123"

    delivered = client.post(f"/api/admin/orders/{order['id']}/delivery", headers=admin)
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"
    assert delivered.json()["delivered_at"] is not None
    assert client.get("/api/orders", headers=buyer).json()[0]["status"] == "delivered"


def test_shipment_details_cannot_be_blank(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    response = client.post(
        "/api/admin/orders/1/shipment",
        json={"shipping_carrier": " ", "tracking_number": " "},
        headers=admin,
    )
    assert response.status_code == 422


def test_customer_and_merchant_registration_and_role_login(client: TestClient):
    customer = client.post(
        "/api/auth/register",
        json={"email": "new.customer@example.com", "password": "customer-password"},
    )
    assert customer.status_code == 201
    assert customer.json()["role"] == "customer"

    missing_store = client.post(
        "/api/auth/register",
        json={"email": "no-store@example.com", "password": "merchant-password", "role": "merchant"},
    )
    assert missing_store.status_code == 422
    merchant = client.post(
        "/api/auth/register",
        json={
            "email": "merchant@example.com",
            "password": "merchant-password",
            "role": "merchant",
            "store_name": "Sample",
        },
    )
    assert merchant.status_code == 201
    assert merchant.json()["role"] == "merchant"
    assert client.post(
        "/api/auth/login",
        json={"email": "merchant@example.com", "password": "merchant-password"},
    ).status_code == 403
    merchant_headers = auth(client, "merchant@example.com", "merchant-password", "merchant")
    assert client.get("/api/merchant/store", headers=merchant_headers).json()["name"] == "Sample"


def test_merchants_manage_only_their_own_products_and_store(client: TestClient):
    for email, store_name in (("first-merchant@example.com", "Sample"), ("second-merchant@example.com", "Sample")):
        response = client.post(
            "/api/auth/register",
            json={"email": email, "password": "merchant-password", "role": "merchant", "store_name": store_name},
        )
        assert response.status_code == 201
    first_headers = auth(client, "first-merchant@example.com", "merchant-password", "merchant")
    second_headers = auth(client, "second-merchant@example.com", "merchant-password", "merchant")
    product = client.post(
        "/api/products",
        json={"sku": "MERCHANT-1", "name": "Sample", "price": "12.00", "stock": 5},
        headers=first_headers,
    )
    assert product.status_code == 201
    assert product.json()["store_name"] == "Sample"
    assert [item["id"] for item in client.get("/api/merchant/products", headers=first_headers).json()] == [product.json()["id"]]
    assert client.get("/api/merchant/products", headers=second_headers).json() == []
    assert client.patch(
        f"/api/products/{product.json()['id']}", json={"stock": 20}, headers=second_headers
    ).status_code == 404
    own_update = client.patch(
        f"/api/products/{product.json()['id']}",
        json={"stock": 7},
        headers=first_headers,
    )
    assert own_update.status_code == 200
    assert own_update.json()["stock"] == 7
    store = client.patch(
        "/api/merchant/store",
        json={"name": "Sample", "address": "Sample", "description": "Sample"},
        headers=first_headers,
    )
    assert store.status_code == 200
    assert store.json()["address"] == "Sample"


def test_account_password_change_and_deletion_preserve_orders(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    assert client.request(
        "DELETE", "/api/account", json={"password": "admin-password"}, headers=admin
    ).status_code == 403
    product = client.post(
        "/api/products",
        json={"sku": "ACCOUNT-1", "name": "Sample", "price": "10.00", "stock": 2},
        headers=admin,
    ).json()
    client.post("/api/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=buyer)
    order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()
    assert client.patch(
        "/api/account/password",
        json={"current_password": "wrong-password", "new_password": "new-buyer-password"},
        headers=buyer,
    ).status_code == 400
    assert client.patch(
        "/api/account/password",
        json={"current_password": "buyer-password", "new_password": "new-buyer-password"},
        headers=buyer,
    ).status_code == 204
    assert client.post(
        "/api/auth/login", json={"email": "buyer@example.com", "password": "buyer-password"}
    ).status_code == 401
    assert client.get("/api/auth/me", headers=buyer).status_code == 401
    buyer = auth(client, "buyer@example.com", "new-buyer-password")
    assert client.request(
        "DELETE", "/api/account", json={"password": "new-buyer-password"}, headers=buyer
    ).status_code == 204
    assert client.get("/api/auth/me", headers=buyer).status_code == 401
    admin_orders = client.get("/api/admin/orders", headers=admin)
    assert admin_orders.status_code == 200
    assert admin_orders.json()["items"][0]["id"] == order["id"]
    assert admin_orders.json()["items"][0]["customer_email"].endswith("@deleted.invalid")


def test_merchant_account_deletion_unlists_products(client: TestClient):
    client.post(
        "/api/auth/register",
        json={"email": "delete-merchant@example.com", "password": "merchant-password", "role": "merchant", "store_name": "Sample"},
    )
    merchant = auth(client, "delete-merchant@example.com", "merchant-password", "merchant")
    product = client.post(
        "/api/products",
        json={"sku": "DELETE-1", "name": "Sample", "price": "5.00", "stock": 1},
        headers=merchant,
    ).json()
    assert client.request(
        "DELETE", "/api/account", json={"password": "merchant-password"}, headers=merchant
    ).status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404
    admin = auth(client, "admin@example.com", "admin-password")
    inventory = client.get("/api/admin/products", headers=admin).json()
    assert inventory[0]["seller_id"] is None
    assert inventory[0]["is_active"] is False


def test_image_upload_uses_storage_and_rejects_non_owner(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    client.post(
        "/api/auth/register",
        json={"email": "image-merchant@example.com", "password": "merchant-password", "role": "merchant", "store_name": "Sample"},
    )
    owner = auth(client, "image-merchant@example.com", "merchant-password", "merchant")
    other = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "IMAGE-1", "name": "Sample", "price": "5.00", "stock": 1},
        headers=owner,
    ).json()
    upload_urls = iter(
        [
            f"https://storage.example/products/{product['id']}/old.png",
            f"https://storage.example/products/{product['id']}/new.png",
        ]
    )
    monkeypatch.setattr("app.main.upload_public_image", lambda content, content_type, prefix: next(upload_urls))
    deleted_images: list[str] = []
    monkeypatch.setattr("app.main.delete_public_image", deleted_images.append)
    image = ("image.png", b"\x89PNG\r\n\x1a\nimage", "image/png")
    uploaded = client.post(f"/api/products/{product['id']}/image", files={"image": image}, headers=owner)
    assert uploaded.status_code == 200
    assert "/products/" in uploaded.json()["image_url"]
    replaced = client.post(f"/api/products/{product['id']}/image", files={"image": image}, headers=owner)
    assert replaced.status_code == 200
    assert replaced.json()["image_url"].endswith("new.png")
    assert deleted_images == [f"https://storage.example/products/{product['id']}/old.png"]
    assert client.post(
        f"/api/products/{product['id']}/image", files={"image": image}, headers=other
    ).status_code == 403


def test_account_avatar_upload_updates_profile(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    buyer = auth(client, "buyer@example.com", "buyer-password")
    profile = client.patch(
        "/api/account/profile",
        json={"display_name": "Sample User"},
        headers=buyer,
    )
    assert profile.status_code == 200
    assert profile.json()["display_name"] == "Sample User"
    upload_urls = iter(
        ["https://storage.example/avatars/2/old.png", "https://storage.example/avatars/2/new.png"]
    )
    monkeypatch.setattr("app.main.upload_public_image", lambda content, content_type, prefix: next(upload_urls))
    deleted_images: list[str] = []
    monkeypatch.setattr("app.main.delete_public_image", deleted_images.append)
    response = client.post(
        "/api/account/avatar",
        files={"image": ("avatar.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
        headers=buyer,
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"].endswith("/old.png")
    replacement = client.post(
        "/api/account/avatar",
        files={"image": ("avatar.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
        headers=buyer,
    )
    assert replacement.status_code == 200
    assert replacement.json()["avatar_url"].endswith("/new.png")
    assert deleted_images == ["https://storage.example/avatars/2/old.png"]


def test_product_reviews_are_public_and_upsert_per_customer(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "REVIEW-1", "name": "Review item", "price": "8.00", "stock": 2},
        headers=admin,
    ).json()
    product_id = product["id"]

    assert client.get(f"/api/products/{product_id}/reviews").json() == []
    assert client.post(
        f"/api/products/{product_id}/reviews",
        json={"rating": 6, "content": "Invalid rating"},
        headers=buyer,
    ).status_code == 422
    assert client.post(
        f"/api/products/{product_id}/reviews",
        json={"rating": 4, "content": "Not purchased yet"},
        headers=buyer,
    ).status_code == 403
    assert client.post(
        "/api/cart/items",
        json={"product_id": product_id, "quantity": 1},
        headers=buyer,
    ).status_code == 200
    order = client.post("/api/orders", json=delivery_details(), headers=buyer)
    assert order.status_code == 201
    assert client.post(
        f"/api/orders/{order.json()['id']}/demo-payment",
        headers=buyer,
    ).status_code == 200
    first = client.post(
        f"/api/products/{product_id}/reviews",
        json={"rating": 4, "content": "  Nice quality  "},
        headers=buyer,
    )
    assert first.status_code == 200
    assert first.json()["content"] == "Nice quality"
    updated = client.post(
        f"/api/products/{product_id}/reviews",
        json={"rating": 5, "content": "Even better than expected"},
        headers=buyer,
    )
    assert updated.status_code == 200
    reviews = client.get(f"/api/products/{product_id}/reviews")
    assert reviews.status_code == 200
    assert len(reviews.json()) == 1
    assert reviews.json()[0]["rating"] == 5
    assert reviews.json()[0]["author_name"] == "用户2"
    assert client.post(
        f"/api/products/{product_id}/reviews",
        json={"rating": 3, "content": "Guest review"},
    ).status_code == 401
    assert client.get(
        f"/api/products/{product_id}/reviews/summary"
    ).json() == {"total": 1, "average_rating": 5.0}
    assert client.delete(
        f"/api/products/{product_id}/reviews/{reviews.json()[0]['id']}",
        headers=admin,
    ).status_code == 403
    assert client.delete(
        f"/api/products/{product_id}/reviews/{reviews.json()[0]['id']}",
        headers=buyer,
    ).status_code == 204
    assert client.get(
        f"/api/products/{product_id}/reviews/summary"
    ).json() == {"total": 0, "average_rating": None}


def test_merchant_fulfillment_is_isolated_and_customer_can_confirm_delivery(client: TestClient):
    merchant_response = client.post(
        "/api/auth/register",
        json={
            "email": "merchant@example.com",
            "password": "merchant-password",
            "role": "merchant",
            "store_name": "Merchant Store",
        },
    )
    assert merchant_response.status_code == 201
    merchant_id = merchant_response.json()["id"]
    merchant = auth(client, "merchant@example.com", "merchant-password", role="merchant")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "MERCHANT-ORDER", "name": "Merchant item", "price": "12.00", "stock": 3},
        headers=merchant,
    ).json()
    assert client.post(
        "/api/cart/items",
        json={"product_id": product["id"], "quantity": 2},
        headers=buyer,
    ).status_code == 200
    order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()
    assert len(order["fulfillments"]) == 1
    assert order["fulfillments"][0]["seller_id"] == merchant_id
    assert client.post(
        f"/api/orders/{order['id']}/demo-payment",
        headers=buyer,
    ).json()["status"] == "processing"
    merchant_orders = client.get("/api/merchant/orders", headers=merchant)
    assert merchant_orders.status_code == 200
    assert merchant_orders.json()[0]["order_id"] == order["id"]
    assert merchant_orders.json()[0]["subtotal"] == "24.00"
    other_registration = client.post(
        "/api/auth/register",
        json={
            "email": "other-merchant@example.com",
            "password": "other-password",
            "role": "merchant",
            "store_name": "Other Store",
        },
    )
    assert other_registration.status_code == 201
    other_merchant = auth(client, "other-merchant@example.com", "other-password", role="merchant")
    assert client.get("/api/merchant/orders", headers=other_merchant).json() == []
    assert client.post(
        f"/api/merchant/orders/{order['id']}/shipment",
        json={"shipping_carrier": "顺丰", "tracking_number": "UNAUTHORIZED"},
        headers=other_merchant,
    ).status_code == 404

    shipment = client.post(
        f"/api/merchant/orders/{order['id']}/shipment",
        json={"shipping_carrier": "顺丰", "tracking_number": "TRACK-1"},
        headers=merchant,
    )
    assert shipment.status_code == 200
    assert shipment.json()["status"] == "shipped"
    updated_order = client.get(f"/api/orders/{order['id']}", headers=buyer).json()
    fulfillment = updated_order["fulfillments"][0]
    assert fulfillment["tracking_number"] == "TRACK-1"
    delivered = client.post(
        f"/api/orders/{order['id']}/fulfillments/{fulfillment['id']}/delivery",
        headers=buyer,
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "delivered"

    assert client.get("/api/merchant/orders", headers=auth(client, "admin@example.com", "admin-password")).status_code == 403


def test_review_report_moderation_and_merchant_suspension(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    registration = client.post(
        "/api/auth/register",
        json={
            "email": "moderated-merchant@example.com",
            "password": "merchant-password",
            "role": "merchant",
            "store_name": "Reviewable Store",
        },
    )
    merchant = auth(client, "moderated-merchant@example.com", "merchant-password", role="merchant")
    merchant_id = registration.json()["id"]
    product = client.post(
        "/api/products",
        json={"sku": "MODERATED", "name": "Moderated item", "price": "5.00", "stock": 2},
        headers=merchant,
    ).json()
    assert client.post(
        "/api/cart/items",
        json={"product_id": product["id"], "quantity": 1},
        headers=buyer,
    ).status_code == 200
    order = client.post("/api/orders", json=delivery_details(), headers=buyer).json()
    client.post(f"/api/orders/{order['id']}/demo-payment", headers=buyer)
    review = client.post(
        f"/api/products/{product['id']}/reviews",
        json={"rating": 1, "content": "Review to report"},
        headers=buyer,
    ).json()
    report = client.post(
        f"/api/products/{product['id']}/reviews/{review['id']}/reports",
        json={"reason": "Contains inappropriate content"},
        headers=admin,
    )
    assert report.status_code == 201
    reports = client.get("/api/admin/review-reports", headers=admin)
    assert reports.json()["total"] == 1
    assert reports.json()["items"][0]["status"] == "open"
    assert client.get("/api/admin/review-reports?status=resolved", headers=admin).json()["total"] == 0
    assert client.get("/api/admin/review-reports?status=invalid", headers=admin).status_code == 422
    resolved = client.patch(
        f"/api/admin/review-reports/{report.json()['id']}",
        json={"status": "resolved"},
        headers=admin,
    )
    assert resolved.status_code == 200
    assert client.get(f"/api/products/{product['id']}/reviews").json() == []

    suspended = client.patch(
        f"/api/admin/merchants/{merchant_id}/status",
        json={"is_suspended": True},
        headers=admin,
    )
    assert suspended.status_code == 200
    assert suspended.json()["is_suspended"] is True
    assert client.get("/api/auth/me", headers=merchant).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "moderated-merchant@example.com", "password": "merchant-password", "role": "merchant"},
    ).status_code == 403
    assert client.get("/api/products").json() == []
    restored = client.patch(
        f"/api/admin/merchants/{merchant_id}/status",
        json={"is_suspended": False},
        headers=admin,
    )
    assert restored.status_code == 200
    assert client.get("/api/products").json()[0]["id"] == product["id"]


def test_product_favorites_are_private_and_idempotent(client: TestClient):
    admin = auth(client, "admin@example.com", "admin-password")
    buyer = auth(client, "buyer@example.com", "buyer-password")
    product = client.post(
        "/api/products",
        json={"sku": "FAVORITE-1", "name": "Favorite item", "price": "9.00", "stock": 1},
        headers=admin,
    ).json()
    product_id = product["id"]

    assert client.put(f"/api/products/{product_id}/favorite").status_code == 401
    assert client.get("/api/favorites", headers=buyer).json() == []
    assert client.put(
        f"/api/products/{product_id}/favorite", headers=buyer
    ).json() == {"is_favorited": True}
    assert client.put(
        f"/api/products/{product_id}/favorite", headers=buyer
    ).json() == {"is_favorited": True}
    saved = client.get("/api/favorites", headers=buyer)
    assert [item["id"] for item in saved.json()] == [product_id]
    assert client.request("DELETE", "/api/account", json={"password": "buyer-password"}, headers=buyer).status_code == 204
    assert client.get("/api/favorites", headers=admin).json() == []
    assert client.delete(
        f"/api/products/{product_id}/favorite", headers=admin
    ).json() == {"is_favorited": False}


def test_storage_image_validation_and_upload(monkeypatch: pytest.MonkeyPatch):
    settings = Settings(
        supabase_url="https://project.supabase.co",
        supabase_service_role_key="server-secret",
        supabase_storage_bucket="shop-images",
    )
    monkeypatch.setattr("app.storage.get_settings", lambda: settings)
    calls: list[tuple[str, bytes]] = []

    class SuccessfulResponse:
        def raise_for_status(self):
            return None

    def fake_put(url: str, **kwargs):
        calls.append((url, kwargs["content"]))
        return SuccessfulResponse()

    monkeypatch.setattr("app.storage.httpx.put", fake_put)
    with pytest.raises(ValueError):
        upload_public_image(b"not an image", "image/png", "avatars/1")
    with pytest.raises(ValueError):
        upload_public_image(b"\xff\xd8\xff" + b"x" * MAX_IMAGE_SIZE, "image/jpeg", "avatars/1")

    url = upload_public_image(b"\x89PNG\r\n\x1a\nimage", "image/png", "avatars/1")
    assert url.startswith("https://project.supabase.co/storage/v1/object/public/shop-images/avatars/1/")
    assert len(calls) == 1
    assert calls[0][1] == b"\x89PNG\r\n\x1a\nimage"


def test_frontend_is_served_when_a_production_build_is_present(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>拾集" in response.text
