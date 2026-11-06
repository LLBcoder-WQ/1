import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine, inspect, text

from app.database import Base, ensure_order_shipping_columns, get_db
from app.main import app
from app.models import Order, User
from app.security import hash_password


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


def auth(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
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
    assert admin_orders.json()[0]["recipient_phone"] == "+86 138 0000 0000"
    assert admin_orders.json()[0]["shipping_address"] == "文三路 100 号 2 幢 301 室"
    assert client.get("/api/products/1").json()["stock"] == 2
    assert client.get("/api/cart", headers=buyer).json()["items"] == []
    admin_orders = client.get("/api/admin/orders", headers=admin)
    assert admin_orders.status_code == 200
    assert len(admin_orders.json()) == 1
    assert admin_orders.json()[0]["customer_email"] == "buyer@example.com"
    assert admin_orders.json()[0]["items"][0]["product_name"] == "Example book"
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


def test_email_code_creates_customer_and_is_one_time(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.main.send_email_login_code",
        lambda email, code: sent.append((email, code)),
    )

    requested = client.post(
        "/api/auth/email-code",
        json={"email": "New.Customer@example.com"},
    )
    assert requested.status_code == 200
    assert requested.json()["detail"] == "验证码已发送"
    assert sent[0][0] == "new.customer@example.com"
    assert len(sent[0][1]) == 6
    assert sent[0][1].isdigit()

    verified = client.post(
        "/api/auth/email-code/verify",
        json={"email": sent[0][0], "code": sent[0][1]},
    )
    assert verified.status_code == 200
    profile = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {verified.json()['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json() == {
        "id": profile.json()["id"],
        "email": "new.customer@example.com",
        "role": "customer",
    }

    reused = client.post(
        "/api/auth/email-code/verify",
        json={"email": sent[0][0], "code": sent[0][1]},
    )
    assert reused.status_code == 401


def test_email_code_resend_cooldown_and_attempt_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    sent: list[str] = []
    monkeypatch.setattr(
        "app.main.send_email_login_code",
        lambda email, code: sent.append(code),
    )
    email = "code-test@example.com"
    assert client.post("/api/auth/email-code", json={"email": email}).status_code == 200
    limited = client.post("/api/auth/email-code", json={"email": email})
    assert limited.status_code == 429
    assert limited.headers["retry-after"]

    invalid_code = f"{(int(sent[0]) + 1) % 1_000_000:06d}"
    for _ in range(5):
        response = client.post(
            "/api/auth/email-code/verify",
            json={"email": email, "code": invalid_code},
        )
        assert response.status_code == 401

    locked_out = client.post(
        "/api/auth/email-code/verify",
        json={"email": email, "code": sent[0]},
    )
    assert locked_out.status_code == 401
    still_rate_limited = client.post("/api/auth/email-code", json={"email": email})
    assert still_rate_limited.status_code == 429


def test_email_code_can_sign_in_existing_admin(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    sent: list[str] = []
    monkeypatch.setattr(
        "app.main.send_email_login_code",
        lambda email, code: sent.append(code),
    )
    assert client.post(
        "/api/auth/email-code",
        json={"email": "admin@example.com"},
    ).status_code == 200
    verified = client.post(
        "/api/auth/email-code/verify",
        json={"email": "admin@example.com", "code": sent[0]},
    )
    profile = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {verified.json()['access_token']}"},
    )
    assert profile.json()["role"] == "admin"


def test_email_code_returns_configuration_error_when_resend_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    def missing_configuration(email: str, code: str) -> None:
        raise RuntimeError("Email login is not configured")

    monkeypatch.setattr("app.main.send_email_login_code", missing_configuration)
    response = client.post(
        "/api/auth/email-code",
        json={"email": "new-user@example.com"},
    )
    assert response.status_code == 503


def test_frontend_is_served_when_a_production_build_is_present(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>拾集" in response.text
