import pytest
from pydantic import ValidationError

from app.config import Settings
from app.database import normalize_database_url


def test_production_requires_a_non_default_strong_secret():
    with pytest.raises(ValidationError, match="SHOP_SECRET_KEY"):
        Settings(environment="production")

    with pytest.raises(ValidationError, match="SHOP_SECRET_KEY"):
        Settings(environment="production", secret_key="short-secret")

    settings = Settings(environment="production", secret_key="a" * 48)
    assert settings.environment == "production"


def test_access_token_lifetime_must_be_positive_and_bounded():
    with pytest.raises(ValidationError):
        Settings(access_token_minutes=0)

    with pytest.raises(ValidationError):
        Settings(access_token_minutes=1441)


@pytest.mark.parametrize(
    ("database_url", "expected"),
    [
        ("postgres://user:pass@host:5432/shop", "postgresql+psycopg://user:pass@host:5432/shop"),
        ("postgresql://user:pass@host:5432/shop", "postgresql+psycopg://user:pass@host:5432/shop"),
        ("postgresql+psycopg://user:pass@host:5432/shop", "postgresql+psycopg://user:pass@host:5432/shop"),
        ("sqlite:///./shop.db", "sqlite:///./shop.db"),
    ],
)
def test_database_url_uses_psycopg_for_postgres(database_url: str, expected: str):
    assert normalize_database_url(database_url) == expected
