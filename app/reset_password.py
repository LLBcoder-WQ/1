import argparse
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User
from app.security import hash_password


def reset_existing_account_password(db: Session, email: str, password: str) -> bool:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return False
    user.password_hash = hash_password(password)
    user.token_version += 1
    db.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset the password for an existing account without changing its role."
    )
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass("New password (at least 8 characters): ")
    confirmation = getpass("Confirm new password: ")
    if len(password) < 8:
        parser.error("Password must contain at least 8 characters")
    if password != confirmation:
        parser.error("Passwords do not match")

    email = args.email.strip().lower()
    with SessionLocal() as db:
        if not reset_existing_account_password(db, email, password):
            parser.error("Account not found")
    print(f"Password reset for account: {email}")


if __name__ == "__main__":
    main()
