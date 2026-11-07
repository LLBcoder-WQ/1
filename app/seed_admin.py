import argparse
from getpass import getpass

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create or promote an administrator account.")
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass("Admin password (at least 8 characters): ")
    if len(password) < 8:
        parser.error("Password must contain at least 8 characters")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            user = User(email=args.email.lower(), password_hash=hash_password(password), role="admin")
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.role = "admin"
            user.is_suspended = False
            user.token_version += 1
        db.commit()
    print(f"Administrator account ready: {args.email.lower()}")


if __name__ == "__main__":
    main()
