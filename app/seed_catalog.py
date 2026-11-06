from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Category, Product

CATALOG = {
    "茶器与香氛": [
        ("SJ-TEA-001", "山岚手作陶杯", "手工拉坯烧制，温润粗陶手感，300ml，适合一人慢慢喝茶。", "89.00", 24),
        ("SJ-TEA-002", "原木茶则", "天然胡桃木制作，纹理各不相同，为每一次取茶留一点仪式感。", "56.00", 18),
        ("SJ-TEA-003", "雨后白茶 · 轻焙小罐", "清甜花香与淡淡蜜韵，福建产区春茶，净含量 50g。", "128.00", 30),
    ],
    "家居器物": [
        ("SJ-HOME-001", "暖光陶瓷小夜灯", "奶油白陶瓷灯罩搭配柔和暖光，适合床头与阅读角。", "169.00", 12),
        ("SJ-HOME-002", "云朵亚麻抱枕套", "天然亚麻混纺，柔软透气，45 × 45cm，不含芯。", "79.00", 20),
        ("SJ-HOME-003", "山形香薰石", "手作石膏香氛摆件，滴入喜欢的精油，让房间留住自然气息。", "48.00", 16),
    ],
    "纸品与文具": [
        ("SJ-PAPER-001", "四时风物便笺本", "米白道林纸，圆角线装，记录灵感与日常，96页。", "39.00", 40),
        ("SJ-PAPER-002", "晨雾黄铜书签", "细砂纹哑光黄铜，轻薄耐用，随时间慢慢养出自己的光泽。", "62.00", 22),
        ("SJ-PAPER-003", "拾集日常贴纸册", "一套 6 张原创自然主题贴纸，适用于手账、信件与礼物包装。", "25.00", 35),
    ],
}


def main():
    added_categories = 0
    added_products = 0
    repaired_products = 0

    with SessionLocal() as db:
        for category_name, products in CATALOG.items():
            category = db.scalar(select(Category).where(Category.name == category_name))
            if category is None:
                seeded_product = db.scalar(
                    select(Product).where(Product.sku == products[0][0])
                )
                legacy_category = (
                    db.get(Category, seeded_product.category_id)
                    if seeded_product is not None
                    else None
                )
                if legacy_category is not None and legacy_category.name and set(legacy_category.name) == {"?"}:
                    legacy_category.name = category_name
                    category = legacy_category
                else:
                    category = Category(name=category_name)
                    db.add(category)
                    db.flush()
                    added_categories += 1

            for sku, name, description, price, stock in products:
                product = db.scalar(select(Product).where(Product.sku == sku))
                if product is None:
                    db.add(
                        Product(
                            sku=sku,
                            name=name,
                            description=description,
                            price=Decimal(price),
                            stock=stock,
                            category_id=category.id,
                            is_active=True,
                        )
                    )
                    added_products += 1
                    continue

                if product.name and "?" in product.name:
                    product.name = name
                    product.description = description
                    repaired_products += 1
                product.category_id = category.id

        db.commit()
        active_products = list(
            db.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.id))
        )

    print(f"Added {added_categories} categories and {added_products} products.")
    if repaired_products:
        print(f"Repaired {repaired_products} product names.")
    print(f"Active catalog: {len(active_products)} products")
    for product in active_products:
        print(f"{product.sku} | {product.price} | stock {product.stock}")


if __name__ == "__main__":
    main()
