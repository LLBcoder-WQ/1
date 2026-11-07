from app.database import (
    Base,
    SessionLocal,
    engine,
    ensure_account_columns,
    ensure_merchant_fulfillments,
    ensure_order_shipping_columns,
)
from app.order_expiration import expire_pending_orders


def main() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_account_columns()
    ensure_order_shipping_columns()
    ensure_merchant_fulfillments()
    with SessionLocal() as db:
        expired_count = expire_pending_orders(db)
    print(f"Expired {expired_count} unpaid order(s).")


if __name__ == "__main__":
    main()
