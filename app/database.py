from collections.abc import Generator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def build_engine(database_url: str) -> Engine:
    database_url = normalize_database_url(database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = build_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def ensure_order_shipping_columns(target_engine: Engine = engine) -> None:
    shipping_columns = {
        "recipient_name": "VARCHAR(80)",
        "recipient_phone": "VARCHAR(30)",
        "shipping_region": "VARCHAR(120)",
        "shipping_address": "VARCHAR(300)",
        "postal_code": "VARCHAR(20)",
        "shipping_carrier": "VARCHAR(80)",
        "tracking_number": "VARCHAR(100)",
        "shipped_at": "TIMESTAMP",
        "delivered_at": "TIMESTAMP",
    }
    with target_engine.begin() as connection:
        existing = {
            column["name"] for column in inspect(connection).get_columns("orders")
        }
        for column_name, column_type in shipping_columns.items():
            if column_name not in existing:
                connection.execute(
                    text(f"ALTER TABLE orders ADD COLUMN {column_name} {column_type}")
                )


def ensure_account_columns(target_engine: Engine = engine) -> None:
    additions = {
        "users": {
            "display_name": "VARCHAR(100)",
            "avatar_url": "VARCHAR(1000)",
            "is_suspended": "BOOLEAN NOT NULL DEFAULT FALSE",
        },
        "products": {
            "image_url": "VARCHAR(1000)",
            "seller_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        },
        "order_items": {
            "seller_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
        },
        "product_reviews": {
            "is_visible": "BOOLEAN NOT NULL DEFAULT TRUE",
        },
    }
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        for table_name, columns in additions.items():
            if table_name not in tables:
                continue
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )
        if "order_items" in inspect(connection).get_table_names():
            connection.execute(
                text(
                    "UPDATE order_items SET seller_id = "
                    "(SELECT seller_id FROM products WHERE products.id = order_items.product_id) "
                    "WHERE seller_id IS NULL"
                )
            )


def ensure_merchant_fulfillments(target_engine: Engine = engine) -> None:
    with target_engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if not {"merchant_fulfillments", "order_items", "orders"} <= tables:
            return
        connection.execute(
            text(
                """
                INSERT INTO merchant_fulfillments (
                    order_id, seller_id, status, shipping_carrier, tracking_number,
                    shipped_at, delivered_at
                )
                SELECT DISTINCT
                    orders.id,
                    order_items.seller_id,
                    CASE
                        WHEN orders.status IN ('paid', 'processing') THEN 'processing'
                        ELSE orders.status
                    END,
                    orders.shipping_carrier,
                    orders.tracking_number,
                    orders.shipped_at,
                    orders.delivered_at
                FROM orders
                JOIN order_items ON order_items.order_id = orders.id
                WHERE NOT EXISTS (
                    SELECT 1 FROM merchant_fulfillments
                    WHERE merchant_fulfillments.order_id = orders.id
                      AND (
                        merchant_fulfillments.seller_id = order_items.seller_id
                        OR (merchant_fulfillments.seller_id IS NULL AND order_items.seller_id IS NULL)
                      )
                )
                """
            )
        )


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
