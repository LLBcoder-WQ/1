from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Coupon, MerchantFulfillment, Order, OrderItem, Payment, Product


def expire_pending_orders(db: Session, now: datetime | None = None, batch_size: int = 200) -> int:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is not None:
        current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)
    cutoff = current_time - timedelta(minutes=get_settings().order_payment_expiry_minutes)
    expired_count = 0

    while True:
        order_ids = list(
            db.scalars(
                select(Order.id)
                .where(
                    Order.status == "pending_payment",
                    or_(
                        Order.expires_at <= current_time,
                        and_(Order.expires_at.is_(None), Order.created_at <= cutoff),
                    ),
                )
                .order_by(Order.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        if not order_ids:
            break

        for order_id in order_ids:
            result = db.execute(
                update(Order)
                .where(Order.id == order_id, Order.status == "pending_payment")
                .values(status="expired")
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                continue

            items = db.execute(
                select(OrderItem.product_id, OrderItem.quantity).where(OrderItem.order_id == order_id)
            )
            for product_id, quantity in items:
                db.execute(
                    update(Product)
                    .where(Product.id == product_id)
                    .values(stock=Product.stock + quantity)
                )

            coupon_code = db.scalar(select(Order.coupon_code).where(Order.id == order_id))
            if coupon_code:
                db.execute(
                    update(Coupon)
                    .where(Coupon.code == coupon_code, Coupon.uses_count > 0)
                    .values(uses_count=Coupon.uses_count - 1)
                )
            db.execute(
                update(Payment)
                .where(Payment.order_id == order_id, Payment.status == "pending")
                .values(status="cancelled")
            )
            db.execute(
                update(MerchantFulfillment)
                .where(MerchantFulfillment.order_id == order_id)
                .values(status="expired")
            )
            expired_count += 1

        db.commit()
        if len(order_ids) < batch_size:
            break

    return expired_count
