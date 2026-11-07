import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthAttempt

LOGIN_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
REGISTER_LIMIT = 5
REGISTER_WINDOW = timedelta(hours=1)


def _key_hash(scope: str, identifier: str) -> str:
    secret = get_settings().secret_key.encode()
    value = f"{scope}:{identifier}".encode()
    return hmac.new(secret, value, hashlib.sha256).hexdigest()


def check_auth_limit(db: Session, scope: str, identifier: str, limit: int, window: timedelta) -> str:
    key_hash = _key_hash(scope, identifier)
    now = datetime.now(timezone.utc)
    cutoff = now - window
    db.execute(
        delete(AuthAttempt).where(
            AuthAttempt.key_hash == key_hash,
            AuthAttempt.created_at < cutoff,
        )
    )
    attempts = db.scalar(
        select(func.count()).select_from(AuthAttempt).where(
            AuthAttempt.key_hash == key_hash,
            AuthAttempt.created_at >= cutoff,
        )
    ) or 0
    if attempts >= limit:
        oldest_attempt = db.scalar(
            select(func.min(AuthAttempt.created_at)).where(
                AuthAttempt.key_hash == key_hash,
                AuthAttempt.created_at >= cutoff,
            )
        )
        if oldest_attempt is not None and oldest_attempt.tzinfo is None:
            oldest_attempt = oldest_attempt.replace(tzinfo=timezone.utc)
        retry_after = max(
            1,
            int((oldest_attempt + window - now).total_seconds()) if oldest_attempt else 1,
        )
        db.rollback()
        raise HTTPException(
            status_code=429,
            detail="尝试次数过多，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    return key_hash


def record_auth_attempt(db: Session, key_hash: str) -> None:
    db.execute(
        delete(AuthAttempt).where(
            AuthAttempt.created_at < datetime.now(timezone.utc) - timedelta(days=1)
        )
    )
    db.add(AuthAttempt(key_hash=key_hash))
    db.commit()
