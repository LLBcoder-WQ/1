from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EmailLoginCode(Base):
    __tablename__ = "email_login_codes"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(String(2000), default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    category: Mapped[Category | None] = relationship(back_populates="products")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer)
    product: Mapped[Product] = relationship()


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    discount_type: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    min_subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_payment")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    coupon_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    shipping_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shipping_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipping_carrier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
