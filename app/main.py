from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import Base, engine, ensure_order_shipping_columns, get_db
from app.dependencies import get_current_user, require_admin
from app.models import CartItem, Category, Coupon, Order, OrderItem, Payment, Product, User
from app.payments import PaymentGateway, get_payment_gateway
from app.schemas import (
    CartItemInput,
    CartLineRead,
    CartRead,
    AdminOrderRead,
    CategoryCreate,
    CategoryRead,
    CheckoutInput,
    CouponCreate,
    CouponRead,
    CouponUpdate,
    LoginInput,
    OrderRead,
    PaymentRead,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ShipmentCreate,
    TokenRead,
    UserCreate,
    UserRead,
)
from app.security import create_access_token, hash_password, verify_password

Base.metadata.create_all(bind=engine)
ensure_order_shipping_columns()
app = FastAPI(title="FastAPI Shop", version="0.1.0")
cors_origins = [
    origin.strip().rstrip("/")
    for origin in get_settings().cors_origins.split(",")
    if origin.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
Money = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(Money, rounding=ROUND_HALF_UP)


def get_order_for_user(db: Session, order_id: int, user: User) -> Order:
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Order.user_id == user.id)
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def admin_order_data(order: Order, customer_email: str) -> dict:
    return {
        "id": order.id,
        "status": order.status,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "total": order.total,
        "coupon_code": order.coupon_code,
        "recipient_name": order.recipient_name,
        "recipient_phone": order.recipient_phone,
        "shipping_region": order.shipping_region,
        "shipping_address": order.shipping_address,
        "postal_code": order.postal_code,
        "shipping_carrier": order.shipping_carrier,
        "tracking_number": order.tracking_number,
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
        "created_at": order.created_at,
        "items": order.items,
        "customer_email": customer_email,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession):
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered") from None
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenRead)
def login(payload: LoginInput, db: DbSession):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenRead(access_token=create_access_token(user.id, user.role))


@app.get("/api/auth/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@app.get("/api/categories", response_model=list[CategoryRead])
def list_categories(db: DbSession):
    return list(db.scalars(select(Category).order_by(Category.name)))


@app.post("/api/categories", response_model=CategoryRead, status_code=201)
def create_category(payload: CategoryCreate, db: DbSession, _: AdminUser):
    category = Category(name=payload.name.strip())
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Category already exists") from None
    db.refresh(category)
    return category


@app.get("/api/products", response_model=list[ProductRead])
def list_products(
    db: DbSession,
    category_id: int | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = select(Product).where(Product.is_active.is_(True))
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
    return list(db.scalars(query.order_by(Product.id).offset(offset).limit(limit)))


@app.get("/api/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession):
    product = db.scalar(select(Product).where(Product.id == product_id, Product.is_active.is_(True)))
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.get("/api/admin/products", response_model=list[ProductRead])
def list_admin_products(db: DbSession, _: AdminUser):
    return list(db.scalars(select(Product).order_by(Product.id.desc())))


@app.post("/api/products", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, db: DbSession, _: AdminUser):
    if payload.category_id is not None and db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists") from None
    db.refresh(product)
    return product


@app.patch("/api/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, db: DbSession, _: AdminUser):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    changes = payload.model_dump(exclude_unset=True)
    if "category_id" in changes and changes["category_id"] is not None:
        if db.get(Category, changes["category_id"]) is None:
            raise HTTPException(status_code=404, detail="Category not found")
    for key, value in changes.items():
        setattr(product, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists") from None
    db.refresh(product)
    return product


@app.get("/api/cart", response_model=CartRead)
def get_cart(db: DbSession, user: CurrentUser):
    rows = list(
        db.scalars(
            select(CartItem)
            .options(selectinload(CartItem.product))
            .where(CartItem.user_id == user.id)
            .order_by(CartItem.id)
        )
    )
    lines = [
        CartLineRead(
            product_id=row.product_id,
            product_name=row.product.name,
            unit_price=row.product.price,
            quantity=row.quantity,
            line_total=money(row.product.price * row.quantity),
        )
        for row in rows
    ]
    return CartRead(items=lines, subtotal=money(sum((line.line_total for line in lines), Decimal("0"))))


@app.post("/api/cart/items", response_model=CartRead)
def add_cart_item(payload: CartItemInput, db: DbSession, user: CurrentUser):
    product = db.get(Product, payload.product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product.id)
    )
    if item is None:
        item = CartItem(user_id=user.id, product_id=product.id, quantity=payload.quantity)
        db.add(item)
    else:
        item.quantity = payload.quantity
    db.commit()
    return get_cart(db, user)


@app.delete("/api/cart/items/{product_id}", status_code=204)
def remove_cart_item(product_id: int, db: DbSession, user: CurrentUser):
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product_id)
    )
    if item is not None:
        db.delete(item)
        db.commit()


@app.post("/api/coupons", response_model=CouponRead, status_code=201)
def create_coupon(payload: CouponCreate, db: DbSession, _: AdminUser):
    coupon_data = payload.model_dump()
    coupon = Coupon(**coupon_data)
    db.add(coupon)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Coupon code already exists") from None
    db.refresh(coupon)
    return coupon


@app.get("/api/coupons", response_model=list[CouponRead])
def list_coupons(db: DbSession, _: AdminUser):
    return list(db.scalars(select(Coupon).order_by(Coupon.id)))


@app.patch("/api/coupons/{coupon_id}", response_model=CouponRead)
def update_coupon(coupon_id: int, payload: CouponUpdate, db: DbSession, _: AdminUser):
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status_code=404, detail="Coupon not found")
    changes = payload.model_dump(exclude_unset=True)
    if "value" in changes and coupon.discount_type == "percent" and changes["value"] > 100:
        raise HTTPException(status_code=422, detail="Percentage discount cannot exceed 100")
    if (
        changes.get("max_uses") is not None
        and changes["max_uses"] < coupon.uses_count
    ):
        raise HTTPException(status_code=422, detail="Maximum uses cannot be less than the current usage count")
    for key, value in changes.items():
        setattr(coupon, key, value)
    db.commit()
    db.refresh(coupon)
    return coupon


@app.post("/api/orders", response_model=OrderRead, status_code=201)
def checkout(payload: CheckoutInput, db: DbSession, user: CurrentUser):
    cart_items = list(
        db.scalars(
            select(CartItem)
            .options(selectinload(CartItem.product))
            .where(CartItem.user_id == user.id)
            .order_by(CartItem.id)
        )
    )
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    if any(not item.product.is_active or item.quantity > item.product.stock for item in cart_items):
        raise HTTPException(status_code=409, detail="One or more products are unavailable in the requested quantity")

    subtotal = money(sum((item.product.price * item.quantity for item in cart_items), Decimal("0")))
    coupon = None
    discount = Decimal("0")
    coupon_code = payload.coupon_code.strip().upper() if payload.coupon_code else None
    if coupon_code:
        coupon = db.scalar(select(Coupon).where(Coupon.code == coupon_code))
        if coupon is None or not coupon.is_active:
            raise HTTPException(status_code=400, detail="Coupon is invalid or inactive")
        if coupon.max_uses is not None and coupon.uses_count >= coupon.max_uses:
            raise HTTPException(status_code=400, detail="Coupon usage limit reached")
        if subtotal < coupon.min_subtotal:
            raise HTTPException(status_code=400, detail="Order does not meet the coupon minimum subtotal")
        discount = (
            subtotal * coupon.value / Decimal("100")
            if coupon.discount_type == "percent"
            else coupon.value
        )
        discount = min(subtotal, money(discount))

    order = Order(
        user_id=user.id,
        status="pending_payment",
        subtotal=subtotal,
        discount=discount,
        total=money(subtotal - discount),
        coupon_code=coupon_code,
        recipient_name=payload.recipient_name,
        recipient_phone=payload.recipient_phone,
        shipping_region=payload.shipping_region,
        shipping_address=payload.shipping_address,
        postal_code=payload.postal_code,
        items=[
            OrderItem(
                product_id=item.product.id,
                product_name=item.product.name,
                unit_price=item.product.price,
                quantity=item.quantity,
            )
            for item in cart_items
        ],
    )
    db.add(order)
    for item in cart_items:
        result = db.execute(
            update(Product)
            .where(Product.id == item.product_id, Product.stock >= item.quantity, Product.is_active.is_(True))
            .values(stock=Product.stock - item.quantity)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Product stock changed; refresh your cart and try again")
        db.delete(item)
    if coupon is not None:
        coupon_update = update(Coupon).where(Coupon.id == coupon.id)
        if coupon.max_uses is not None:
            coupon_update = coupon_update.where(Coupon.uses_count < coupon.max_uses)
        result = db.execute(coupon_update.values(uses_count=Coupon.uses_count + 1))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Coupon usage limit reached")
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return db.scalar(select(Order).options(selectinload(Order.items)).where(Order.id == order.id))


@app.get("/api/orders", response_model=list[OrderRead])
def list_orders(db: DbSession, user: CurrentUser):
    return list(
        db.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.user_id == user.id)
            .order_by(Order.id.desc())
        )
    )


@app.get("/api/admin/orders", response_model=list[AdminOrderRead])
def list_admin_orders(
    db: DbSession,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = db.execute(
        select(Order, User.email)
        .join(User, Order.user_id == User.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [admin_order_data(order, email) for order, email in rows]


@app.post("/api/admin/orders/{order_id}/shipment", response_model=AdminOrderRead)
def create_order_shipment(
    order_id: int,
    payload: ShipmentCreate,
    db: DbSession,
    _: AdminUser,
):
    row = db.execute(
        select(Order, User.email)
        .join(User, Order.user_id == User.id)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order, customer_email = row
    if order.status not in {"paid", "processing"}:
        raise HTTPException(
            status_code=409,
            detail="Only paid, unfulfilled orders can be shipped; payment confirmation is not available yet",
        )
    order.shipping_carrier = payload.shipping_carrier
    order.tracking_number = payload.tracking_number
    order.shipped_at = datetime.now(timezone.utc)
    order.delivered_at = None
    order.status = "shipped"
    db.commit()
    db.refresh(order)
    return admin_order_data(order, customer_email)


@app.post("/api/admin/orders/{order_id}/delivery", response_model=AdminOrderRead)
def mark_order_delivered(order_id: int, db: DbSession, _: AdminUser):
    row = db.execute(
        select(Order, User.email)
        .join(User, Order.user_id == User.id)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    order, customer_email = row
    if order.status != "shipped":
        raise HTTPException(status_code=409, detail="Only shipped orders can be marked delivered")
    order.status = "delivered"
    order.delivered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    return admin_order_data(order, customer_email)


@app.get("/api/orders/{order_id}", response_model=OrderRead)
def get_order(order_id: int, db: DbSession, user: CurrentUser):
    return get_order_for_user(db, order_id, user)


@app.post("/api/orders/{order_id}/cancel", response_model=OrderRead)
def cancel_order(order_id: int, db: DbSession, user: CurrentUser):
    order = get_order_for_user(db, order_id, user)
    if order.status == "cancelled":
        return order
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail="Only unpaid orders can be cancelled")
    for item in order.items:
        db.execute(
            update(Product)
            .where(Product.id == item.product_id)
            .values(stock=Product.stock + item.quantity)
        )
    if order.coupon_code:
        db.execute(
            update(Coupon)
            .where(Coupon.code == order.coupon_code, Coupon.uses_count > 0)
            .values(uses_count=Coupon.uses_count - 1)
        )
    db.execute(
        update(Payment)
        .where(Payment.order_id == order.id, Payment.status == "pending")
        .values(status="cancelled")
    )
    order.status = "cancelled"
    db.commit()
    return get_order_for_user(db, order_id, user)


@app.post("/api/orders/{order_id}/payment", response_model=PaymentRead)
def start_payment(
    order_id: int,
    db: DbSession,
    user: CurrentUser,
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
):
    order = get_order_for_user(db, order_id, user)
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail="Order is not awaiting payment")
    existing = db.scalar(
        select(Payment).where(Payment.order_id == order.id, Payment.status == "pending")
    )
    if existing is not None:
        return existing
    result = gateway.create_payment(order.id, str(order.total))
    payment = Payment(
        order_id=order.id,
        provider=result.provider,
        provider_reference=result.reference,
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
