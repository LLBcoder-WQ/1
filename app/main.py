import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import (
    Base,
    engine,
    ensure_account_columns,
    ensure_merchant_fulfillments,
    ensure_order_shipping_columns,
    get_db,
)
from app.dependencies import (
    get_current_user,
    get_optional_current_user,
    require_admin,
    require_shop_manager,
)
from app.models import (
    CartItem,
    Category,
    Coupon,
    MerchantFulfillment,
    MerchantStore,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductFavorite,
    ProductReview,
    ProductReviewReport,
    User,
)
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
    AccountDelete,
    AdminMerchantRead,
    AdminMerchantStatus,
    AdminReviewReportRead,
    FavoriteStatus,
    LoginInput,
    PasswordChange,
    ProfileUpdate,
    OrderRead,
    PaymentRead,
    ProductCreate,
    ProductRead,
    ProductReviewCreate,
    ProductReviewRead,
    ProductReviewReportCreate,
    ProductReviewReportUpdate,
    ProductReviewSummary,
    ProductUpdate,
    ShipmentCreate,
    MerchantOrderRead,
    StoreRead,
    StoreUpdate,
    TokenRead,
    UserCreate,
    UserRead,
)
from app.security import create_access_token, hash_password, verify_password
from app.storage import delete_public_image, upload_public_image

CORS_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

Base.metadata.create_all(bind=engine)
ensure_account_columns()
ensure_order_shipping_columns()
ensure_merchant_fulfillments()
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
        allow_methods=CORS_ALLOWED_METHODS,
        allow_headers=["Authorization", "Content-Type"],
    )
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
ShopManagerUser = Annotated[User, Depends(require_shop_manager)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]
Money = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(Money, rounding=ROUND_HALF_UP)


def get_order_for_user(db: Session, order_id: int, user: User) -> Order:
    order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.fulfillments)
            .selectinload(MerchantFulfillment.seller)
            .selectinload(User.store),
        )
        .where(Order.id == order_id, Order.user_id == user.id)
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def get_public_product(db: Session, product_id: int) -> Product:
    product = db.scalar(
        select(Product)
        .options(selectinload(Product.seller).selectinload(User.store))
        .outerjoin(User, Product.seller_id == User.id)
        .where(
            Product.id == product_id,
            Product.is_active.is_(True),
            or_(Product.seller_id.is_(None), User.is_suspended.is_(False)),
        )
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


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


def merchant_order_data(fulfillment: MerchantFulfillment, customer_email: str) -> dict:
    order = fulfillment.order
    return {
        "fulfillment_id": fulfillment.id,
        "order_id": order.id,
        "status": fulfillment.status,
        "created_at": order.created_at,
        "customer_email": customer_email,
        "recipient_name": order.recipient_name,
        "recipient_phone": order.recipient_phone,
        "shipping_region": order.shipping_region,
        "shipping_address": order.shipping_address,
        "postal_code": order.postal_code,
        "subtotal": sum((item.unit_price * item.quantity for item in fulfillment.items), Decimal("0")),
        "items": fulfillment.items,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession):
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    if payload.role == "merchant":
        user.store = MerchantStore(name=payload.store_name or "")
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
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.role != "admin" and user.role != payload.role:
        raise HTTPException(status_code=403, detail="登录入口与账号身份不匹配")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="账号已暂停，请联系平台管理员")
    return TokenRead(access_token=create_access_token(user.id, user.role))


@app.get("/api/auth/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@app.patch("/api/account/profile", response_model=UserRead)
def update_account_profile(payload: ProfileUpdate, db: DbSession, user: CurrentUser):
    if "display_name" in payload.model_fields_set:
        user.display_name = payload.display_name
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/account/avatar", response_model=UserRead)
def upload_account_avatar(
    db: DbSession,
    user: CurrentUser,
    image: UploadFile = File(...),
):
    content = image.file.read(5 * 1024 * 1024 + 1)
    try:
        user.avatar_url = upload_public_image(content, image.content_type or "", f"avatars/{user.id}")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="头像存储服务未配置或暂时不可用") from None
    db.commit()
    db.refresh(user)
    return user


@app.patch("/api/account/password", status_code=204)
def change_account_password(payload: PasswordChange, db: DbSession, user: CurrentUser):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    user.password_hash = hash_password(payload.new_password)
    db.commit()


@app.delete("/api/account", status_code=204)
def delete_account(payload: AccountDelete, db: DbSession, user: CurrentUser):
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="管理员账户不能通过此入口注销")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="密码不正确")
    if user.avatar_url:
        try:
            delete_public_image(user.avatar_url)
        except (RuntimeError, ValueError):
            raise HTTPException(status_code=502, detail="头像删除失败，请稍后重试") from None

    db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    db.execute(delete(ProductFavorite).where(ProductFavorite.user_id == user.id))
    db.execute(
        update(Product)
        .where(Product.seller_id == user.id)
        .values(seller_id=None, is_active=False)
    )
    if user.store is not None:
        user.store.name = "已注销店铺"
        user.store.address = ""
        user.store.description = ""
    user.email = f"deleted-{user.id}-{secrets.token_hex(4)}@deleted.invalid"
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.role = "deleted"
    user.display_name = None
    user.avatar_url = None
    db.commit()


@app.get("/api/merchant/store", response_model=StoreRead)
def get_merchant_store(user: ShopManagerUser):
    if user.store is None:
        raise HTTPException(status_code=404, detail="Store profile not found")
    return user.store


@app.patch("/api/merchant/store", response_model=StoreRead)
def update_merchant_store(payload: StoreUpdate, db: DbSession, user: ShopManagerUser):
    if user.role == "admin":
        raise HTTPException(status_code=403, detail="管理员账号不能编辑商家店铺资料")
    if user.store is None:
        raise HTTPException(status_code=404, detail="Store profile not found")
    user.store.name = payload.name
    user.store.address = payload.address
    user.store.description = payload.description
    db.commit()
    db.refresh(user.store)
    return user.store


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
    query = (
        select(Product)
        .options(selectinload(Product.seller).selectinload(User.store))
        .where(Product.is_active.is_(True))
        .outerjoin(User, Product.seller_id == User.id)
        .where(or_(Product.seller_id.is_(None), User.is_suspended.is_(False)))
    )
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if search:
        term = f"%{search}%"
        query = query.where(or_(Product.name.ilike(term), Product.description.ilike(term), Product.sku.ilike(term)))
    return list(db.scalars(query.order_by(Product.id).offset(offset).limit(limit)))


@app.get("/api/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession):
    return get_public_product(db, product_id)


@app.get("/api/products/{product_id}/reviews", response_model=list[ProductReviewRead])
def list_product_reviews(
    product_id: int,
    db: DbSession,
    user: OptionalCurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    get_public_product(db, product_id)
    reviews = db.scalars(
        select(ProductReview)
        .options(selectinload(ProductReview.user))
        .where(ProductReview.product_id == product_id, ProductReview.is_visible.is_(True))
        .order_by(ProductReview.created_at.desc(), ProductReview.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        ProductReviewRead(
            id=review.id,
            product_id=review.product_id,
            rating=review.rating,
            content=review.content,
            author_name=(
                "已注销用户"
                if review.user.role == "deleted"
                else review.user.display_name or f"用户{review.user.id}"
            ),
            created_at=review.created_at,
            updated_at=review.updated_at,
            can_edit=user is not None and review.user_id == user.id,
        )
        for review in reviews
    ]


@app.get("/api/products/{product_id}/reviews/summary", response_model=ProductReviewSummary)
def get_product_review_summary(product_id: int, db: DbSession):
    get_public_product(db, product_id)
    total, average = db.execute(
        select(func.count(ProductReview.id), func.avg(ProductReview.rating)).where(
            ProductReview.product_id == product_id,
            ProductReview.is_visible.is_(True),
        )
    ).one()
    return ProductReviewSummary(total=total, average_rating=float(average) if average is not None else None)


@app.post("/api/products/{product_id}/reviews", response_model=ProductReviewRead)
def create_or_update_product_review(
    product_id: int,
    payload: ProductReviewCreate,
    db: DbSession,
    user: CurrentUser,
):
    get_public_product(db, product_id)
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can review products")
    purchased = db.scalar(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == user.id,
            Order.status.in_(("paid", "processing", "shipped", "delivered")),
            OrderItem.product_id == product_id,
        )
        .limit(1)
    )
    if purchased is None:
        raise HTTPException(status_code=403, detail="购买并完成演示付款后才能评价该商品")
    review = db.scalar(
        select(ProductReview).where(
            ProductReview.product_id == product_id,
            ProductReview.user_id == user.id,
        )
    )
    if review is None:
        review = ProductReview(product_id=product_id, user_id=user.id)
        db.add(review)
    review.rating = payload.rating
    review.content = payload.content
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        review = db.scalar(
            select(ProductReview).where(
                ProductReview.product_id == product_id,
                ProductReview.user_id == user.id,
            )
        )
        if review is None:
            raise HTTPException(status_code=409, detail="Unable to save review") from None
        review.rating = payload.rating
        review.content = payload.content
        db.commit()
    db.refresh(review)
    return ProductReviewRead(
        id=review.id,
        product_id=review.product_id,
        rating=review.rating,
        content=review.content,
        author_name=user.display_name or f"用户{user.id}",
        created_at=review.created_at,
        updated_at=review.updated_at,
        can_edit=True,
    )


@app.delete("/api/products/{product_id}/reviews/{review_id}", status_code=204)
def delete_product_review(product_id: int, review_id: int, db: DbSession, user: CurrentUser):
    review = db.get(ProductReview, review_id)
    if review is None or review.product_id != product_id:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the review author can delete it")
    db.delete(review)
    db.commit()


@app.post(
    "/api/products/{product_id}/reviews/{review_id}/reports",
    response_model=AdminReviewReportRead,
    status_code=201,
)
def report_product_review(
    product_id: int,
    review_id: int,
    payload: ProductReviewReportCreate,
    db: DbSession,
    user: CurrentUser,
):
    review = db.scalar(
        select(ProductReview)
        .options(selectinload(ProductReview.user))
        .where(
            ProductReview.id == review_id,
            ProductReview.product_id == product_id,
            ProductReview.is_visible.is_(True),
        )
    )
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot report your own review")
    report = ProductReviewReport(
        review_id=review_id,
        reporter_id=user.id,
        reason=payload.reason,
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already reported this review") from None
    db.refresh(report)
    return AdminReviewReportRead(
        id=report.id,
        review_id=review.id,
        product_id=review.product_id,
        product_name=db.scalar(select(Product.name).where(Product.id == review.product_id)) or "",
        reporter_name=user.display_name or user.email,
        reason=report.reason,
        status=report.status,
        review_content=review.content,
        created_at=report.created_at,
    )


@app.get("/api/favorites", response_model=list[ProductRead])
def list_favorite_products(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return list(
        db.scalars(
            select(Product)
            .join(ProductFavorite, ProductFavorite.product_id == Product.id)
            .options(selectinload(Product.seller).selectinload(User.store))
            .outerjoin(User, Product.seller_id == User.id)
            .where(
                ProductFavorite.user_id == user.id,
                Product.is_active.is_(True),
                or_(Product.seller_id.is_(None), User.is_suspended.is_(False)),
            )
            .order_by(ProductFavorite.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )


@app.put("/api/products/{product_id}/favorite", response_model=FavoriteStatus)
def add_product_favorite(product_id: int, db: DbSession, user: CurrentUser):
    get_public_product(db, product_id)
    favorite = db.scalar(
        select(ProductFavorite).where(
            ProductFavorite.product_id == product_id,
            ProductFavorite.user_id == user.id,
        )
    )
    if favorite is None:
        db.add(ProductFavorite(product_id=product_id, user_id=user.id))
        db.commit()
    return FavoriteStatus(is_favorited=True)


@app.delete("/api/products/{product_id}/favorite", response_model=FavoriteStatus)
def remove_product_favorite(product_id: int, db: DbSession, user: CurrentUser):
    db.execute(
        delete(ProductFavorite).where(
            ProductFavorite.product_id == product_id,
            ProductFavorite.user_id == user.id,
        )
    )
    db.commit()
    return FavoriteStatus(is_favorited=False)


@app.get("/api/admin/products", response_model=list[ProductRead])
def list_admin_products(db: DbSession, _: AdminUser):
    return list(
        db.scalars(
            select(Product)
            .options(selectinload(Product.seller).selectinload(User.store))
            .order_by(Product.id.desc())
        )
    )


@app.get("/api/admin/merchants", response_model=list[AdminMerchantRead])
def list_admin_merchants(db: DbSession, _: AdminUser):
    merchants = db.scalars(
        select(User)
        .options(selectinload(User.store))
        .where(User.role == "merchant")
        .order_by(User.id)
    )
    return [
        {
            "id": merchant.id,
            "email": merchant.email,
            "role": merchant.role,
            "display_name": merchant.display_name,
            "avatar_url": merchant.avatar_url,
            "is_suspended": merchant.is_suspended,
            "store_name": merchant.store.name if merchant.store else None,
            "store_address": merchant.store.address if merchant.store else None,
        }
        for merchant in merchants
    ]


@app.patch("/api/admin/merchants/{merchant_id}/status", response_model=AdminMerchantRead)
def set_merchant_status(
    merchant_id: int,
    payload: AdminMerchantStatus,
    db: DbSession,
    _: AdminUser,
):
    merchant = db.scalar(
        select(User).options(selectinload(User.store)).where(User.id == merchant_id, User.role == "merchant")
    )
    if merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")
    merchant.is_suspended = payload.is_suspended
    db.commit()
    return {
        "id": merchant.id,
        "email": merchant.email,
        "role": merchant.role,
        "display_name": merchant.display_name,
        "avatar_url": merchant.avatar_url,
        "is_suspended": merchant.is_suspended,
        "store_name": merchant.store.name if merchant.store else None,
        "store_address": merchant.store.address if merchant.store else None,
    }


@app.get("/api/admin/review-reports", response_model=list[AdminReviewReportRead])
def list_admin_review_reports(
    db: DbSession,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    reports = db.scalars(
        select(ProductReviewReport)
        .options(
            selectinload(ProductReviewReport.review).selectinload(ProductReview.user),
            selectinload(ProductReviewReport.reporter),
        )
        .order_by(ProductReviewReport.created_at.desc(), ProductReviewReport.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        AdminReviewReportRead(
            id=report.id,
            review_id=report.review_id,
            product_id=report.review.product_id,
            product_name=report.review.product.name,
            reporter_name=report.reporter.display_name or report.reporter.email,
            reason=report.reason,
            status=report.status,
            review_content=report.review.content,
            created_at=report.created_at,
        )
        for report in reports
    ]


@app.patch("/api/admin/review-reports/{report_id}", response_model=AdminReviewReportRead)
def update_admin_review_report(
    report_id: int,
    payload: ProductReviewReportUpdate,
    db: DbSession,
    _: AdminUser,
):
    report = db.scalar(
        select(ProductReviewReport)
        .options(
            selectinload(ProductReviewReport.review).selectinload(ProductReview.user),
            selectinload(ProductReviewReport.reporter),
        )
        .where(ProductReviewReport.id == report_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Review report not found")
    if report.status != "open":
        raise HTTPException(status_code=409, detail="Review report has already been processed")
    report.status = payload.status
    if payload.status == "resolved":
        report.review.is_visible = False
    db.commit()
    return AdminReviewReportRead(
        id=report.id,
        review_id=report.review_id,
        product_id=report.review.product_id,
        product_name=report.review.product.name,
        reporter_name=report.reporter.display_name or report.reporter.email,
        reason=report.reason,
        status=report.status,
        review_content=report.review.content,
        created_at=report.created_at,
    )


@app.get("/api/merchant/products", response_model=list[ProductRead])
def list_merchant_products(db: DbSession, user: ShopManagerUser):
    query = select(Product).options(selectinload(Product.seller).selectinload(User.store))
    if user.role != "admin":
        query = query.where(Product.seller_id == user.id)
    return list(db.scalars(query.order_by(Product.id.desc())))


@app.post("/api/products", response_model=ProductRead, status_code=201)
def create_product(payload: ProductCreate, db: DbSession, user: ShopManagerUser):
    if payload.category_id is not None and db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    product = Product(
        **payload.model_dump(),
        seller_id=user.id if user.role == "merchant" else None,
    )
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists") from None
    db.refresh(product)
    return product


@app.patch("/api/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, db: DbSession, user: ShopManagerUser):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if user.role != "admin" and product.seller_id != user.id:
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


@app.post("/api/products/{product_id}/image", response_model=ProductRead)
def upload_product_image(
    product_id: int,
    db: DbSession,
    user: ShopManagerUser,
    image: UploadFile = File(...),
):
    product = db.get(Product, product_id)
    if product is None or (user.role != "admin" and product.seller_id != user.id):
        raise HTTPException(status_code=404, detail="Product not found")
    content = image.file.read(5 * 1024 * 1024 + 1)
    try:
        product.image_url = upload_public_image(
            content,
            image.content_type or "",
            f"products/{product.seller_id or user.id}",
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RuntimeError:
        raise HTTPException(status_code=503, detail="商品图片存储未配置或暂时不可用") from None
    db.commit()
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
    product = get_public_product(db, payload.product_id)
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
    if any(
        not item.product.is_active
        or item.quantity > item.product.stock
        or (item.product.seller is not None and item.product.seller.is_suspended)
        for item in cart_items
    ):
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
                seller_id=item.product.seller_id,
            )
            for item in cart_items
        ],
    )
    seller_ids = {item.product.seller_id for item in cart_items}
    order.fulfillments = [
        MerchantFulfillment(
            seller_id=seller_id,
            status="pending_payment",
        )
        for seller_id in seller_ids
    ]
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
            .options(
                selectinload(Order.items),
                selectinload(Order.fulfillments).selectinload(MerchantFulfillment.seller).selectinload(User.store),
            )
            .where(Order.user_id == user.id)
            .order_by(Order.id.desc())
        )
    )


@app.post("/api/orders/{order_id}/demo-payment", response_model=OrderRead)
def confirm_demo_payment(order_id: int, db: DbSession, user: CurrentUser):
    order = get_order_for_user(db, order_id, user)
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail="Order is not awaiting payment")
    payment = db.scalar(
        select(Payment).where(Payment.order_id == order.id, Payment.status == "pending")
    )
    if payment is None:
        payment = Payment(
            order_id=order.id,
            provider="demo",
            provider_reference=f"demo-{order.id}-{secrets.token_hex(4)}",
            status="succeeded",
        )
        db.add(payment)
    else:
        payment.status = "succeeded"
    order.status = "processing"
    for fulfillment in order.fulfillments:
        fulfillment.status = "processing"
    db.commit()
    return get_order_for_user(db, order_id, user)


@app.post("/api/orders/{order_id}/fulfillments/{fulfillment_id}/delivery", response_model=OrderRead)
def confirm_merchant_delivery(
    order_id: int,
    fulfillment_id: int,
    db: DbSession,
    user: CurrentUser,
):
    order = get_order_for_user(db, order_id, user)
    fulfillment = db.scalar(
        select(MerchantFulfillment).where(
            MerchantFulfillment.id == fulfillment_id,
            MerchantFulfillment.order_id == order.id,
        )
    )
    if fulfillment is None:
        raise HTTPException(status_code=404, detail="Fulfillment not found")
    if fulfillment.status != "shipped":
        raise HTTPException(status_code=409, detail="Only shipped items can be confirmed as delivered")
    fulfillment.status = "delivered"
    fulfillment.delivered_at = datetime.now(timezone.utc)
    if all(item.status == "delivered" for item in order.fulfillments):
        order.status = "delivered"
        order.delivered_at = fulfillment.delivered_at
    db.commit()
    return get_order_for_user(db, order_id, user)


@app.get("/api/merchant/orders", response_model=list[MerchantOrderRead])
def list_merchant_orders(
    db: DbSession,
    user: ShopManagerUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if user.role != "merchant":
        raise HTTPException(status_code=403, detail="Merchant account required")
    rows = db.execute(
        select(MerchantFulfillment, User.email)
        .join(Order, Order.id == MerchantFulfillment.order_id)
        .join(User, User.id == Order.user_id)
        .options(
            selectinload(MerchantFulfillment.order).selectinload(Order.items),
            selectinload(MerchantFulfillment.seller).selectinload(User.store),
        )
        .where(MerchantFulfillment.seller_id == user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [merchant_order_data(fulfillment, email) for fulfillment, email in rows]


@app.post("/api/merchant/orders/{order_id}/shipment", response_model=MerchantOrderRead)
def create_merchant_shipment(
    order_id: int,
    payload: ShipmentCreate,
    db: DbSession,
    user: ShopManagerUser,
):
    if user.role != "merchant":
        raise HTTPException(status_code=403, detail="Merchant account required")
    row = db.execute(
        select(MerchantFulfillment, User.email)
        .join(Order, Order.id == MerchantFulfillment.order_id)
        .join(User, User.id == Order.user_id)
        .options(
            selectinload(MerchantFulfillment.order).selectinload(Order.items),
            selectinload(MerchantFulfillment.seller).selectinload(User.store),
        )
        .where(MerchantFulfillment.order_id == order_id, MerchantFulfillment.seller_id == user.id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Merchant order not found")
    fulfillment, email = row
    if fulfillment.status != "processing":
        raise HTTPException(status_code=409, detail="Only paid, unshipped merchant orders can be shipped")
    fulfillment.status = "shipped"
    fulfillment.shipping_carrier = payload.shipping_carrier
    fulfillment.tracking_number = payload.tracking_number
    fulfillment.shipped_at = datetime.now(timezone.utc)
    order = fulfillment.order
    if all(item.status in {"shipped", "delivered"} for item in order.fulfillments):
        order.status = "shipped"
    db.commit()
    return merchant_order_data(fulfillment, email)


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
        .options(
            selectinload(Order.items),
            selectinload(Order.fulfillments).selectinload(MerchantFulfillment.seller).selectinload(User.store),
        )
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
    for fulfillment in order.fulfillments:
        fulfillment.status = "shipped"
        fulfillment.shipping_carrier = payload.shipping_carrier
        fulfillment.tracking_number = payload.tracking_number
        fulfillment.shipped_at = order.shipped_at
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
    for fulfillment in order.fulfillments:
        fulfillment.status = "delivered"
        fulfillment.delivered_at = order.delivered_at
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
