from decimal import Decimal
from datetime import datetime
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["customer", "merchant"] = "customer"
    store_name: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_merchant_store_name(self):
        if self.store_name is not None:
            self.store_name = self.store_name.strip()
        if self.role == "merchant" and not self.store_name:
            raise ValueError("store_name is required for merchant accounts")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    display_name: str | None
    avatar_url: str | None
    is_suspended: bool = False


class AdminMerchantRead(UserRead):
    store_name: str | None
    store_address: str | None


class AdminMerchantStatus(BaseModel):
    is_suspended: bool


class AdminReviewReportRead(BaseModel):
    id: int
    review_id: int
    product_id: int
    product_name: str
    reporter_name: str
    reason: str
    status: str
    review_content: str
    created_at: datetime


class AdminReviewReportPageRead(BaseModel):
    items: list[AdminReviewReportRead]
    total: int
    limit: int
    offset: int


class ProductReviewReportCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("report reason cannot be blank")
        return reason


class ProductReviewReportUpdate(BaseModel):
    status: Literal["resolved", "dismissed"]


class LoginInput(BaseModel):
    email: EmailStr
    password: str
    role: Literal["customer", "merchant"] = "customer"


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def name_must_not_be_blank(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("category name cannot be blank")
        return self


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    stock: int = Field(ge=0)
    category_id: int | None = None


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    stock: int | None = Field(default=None, ge=0)
    category_id: int | None = None
    is_active: bool | None = None
    image_url: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def reject_null_non_nullable_fields(self):
        for field_name, value in self.model_dump(exclude_unset=True).items():
            if value is None and field_name not in {"category_id", "image_url"}:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str
    price: Decimal
    stock: int
    is_active: bool
    category_id: int | None
    image_url: str | None
    seller_id: int | None
    store_name: str | None
    store_address: str | None


class ProductReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=1000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("review content cannot be blank")
        return content


class ProductReviewRead(BaseModel):
    id: int
    product_id: int
    rating: int
    content: str
    author_name: str
    created_at: datetime
    updated_at: datetime
    can_edit: bool = False


class ProductReviewSummary(BaseModel):
    total: int
    average_rating: float | None


class FavoriteStatus(BaseModel):
    is_favorited: bool


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_profile(self):
        if not self.model_fields_set:
            raise ValueError("provide a profile field to update")
        if self.display_name is not None:
            self.display_name = self.display_name.strip() or None
        return self


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class StoreUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def normalize_store_fields(self):
        self.name = self.name.strip()
        self.address = self.address.strip()
        self.description = self.description.strip()
        if not self.name:
            raise ValueError("store name cannot be blank")
        return self


class StoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    description: str


class CartItemInput(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=99)


class CartLineRead(BaseModel):
    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class CartRead(BaseModel):
    items: list[CartLineRead]
    subtotal: Decimal


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    discount_type: Literal["percent", "fixed"]
    value: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    min_subtotal: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    max_uses: int | None = Field(default=None, gt=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not all(char.isalnum() or char in "_-" for char in normalized):
            raise ValueError("coupon code may contain only letters, numbers, underscores, and hyphens")
        return normalized

    @model_validator(mode="after")
    def percent_cannot_exceed_100(self):
        if self.discount_type == "percent" and self.value > 100:
            raise ValueError("percentage discount cannot exceed 100")
        return self


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    discount_type: str
    value: Decimal
    min_subtotal: Decimal
    max_uses: int | None
    uses_count: int
    is_active: bool


class CheckoutInput(BaseModel):
    coupon_code: str | None = Field(default=None, max_length=40)
    recipient_name: str = Field(min_length=1, max_length=80)
    recipient_phone: str = Field(min_length=7, max_length=30)
    shipping_region: str = Field(min_length=1, max_length=120)
    shipping_address: str = Field(min_length=5, max_length=300)
    postal_code: str | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_shipping_details(self):
        for field_name in ("recipient_name", "shipping_region", "shipping_address"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} cannot be blank")
            setattr(self, field_name, value)

        self.recipient_phone = re.sub(r"\s+", " ", self.recipient_phone.strip())
        if not re.fullmatch(r"\+?[0-9][0-9 -]{5,28}[0-9]", self.recipient_phone):
            raise ValueError("recipient_phone must be a valid phone number")

        if self.postal_code is not None:
            self.postal_code = self.postal_code.strip() or None
        return self


class ShipmentCreate(BaseModel):
    shipping_carrier: str = Field(min_length=1, max_length=80)
    tracking_number: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def normalize_shipment_details(self):
        self.shipping_carrier = self.shipping_carrier.strip()
        self.tracking_number = self.tracking_number.strip()
        if not self.shipping_carrier or not self.tracking_number:
            raise ValueError("shipping carrier and tracking number cannot be blank")
        return self


class CouponUpdate(BaseModel):
    value: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    min_subtotal: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    max_uses: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_update_values(self):
        if not self.model_fields_set:
            raise ValueError("provide at least one coupon field to update")
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None and field_name != "max_uses":
                raise ValueError(f"{field_name} cannot be null")
        return self


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    unit_price: Decimal
    quantity: int


class MerchantFulfillmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int | None
    store_name: str
    status: str
    shipping_carrier: str | None
    tracking_number: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    items: list[OrderItemRead]


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    coupon_code: str | None
    expires_at: datetime | None
    recipient_name: str | None
    recipient_phone: str | None
    shipping_region: str | None
    shipping_address: str | None
    postal_code: str | None
    shipping_carrier: str | None
    tracking_number: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    items: list[OrderItemRead]
    fulfillments: list[MerchantFulfillmentRead] = Field(default_factory=list)


class MerchantOrderRead(BaseModel):
    fulfillment_id: int
    order_id: int
    status: str
    created_at: datetime
    customer_email: str
    recipient_name: str | None
    recipient_phone: str | None
    shipping_region: str | None
    shipping_address: str | None
    postal_code: str | None
    subtotal: Decimal
    items: list[OrderItemRead]


class AdminOrderRead(OrderRead):
    customer_email: str


class AdminOrderPageRead(BaseModel):
    items: list[AdminOrderRead]
    total: int
    limit: int
    offset: int


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    provider: str
    provider_reference: str
    status: str
