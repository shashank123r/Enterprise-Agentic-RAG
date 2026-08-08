"""Seed an initial admin user if none exists."""

import asyncio
import os


async def main() -> None:
    from app.core.constants import Role
    from app.core.security import hash_password
    from app.db.session import async_session_factory, init_db
    from app.repositories.user_repository import UserRepository

    email = os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("SEED_ADMIN_PASSWORD", "Admin1234!")
    username = "admin"

    await init_db()

    async with async_session_factory() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(email.lower().strip())
        if existing is not None:
            print(f"[seed] Admin already exists: {email}")
            return

        await repo.create(
            email=email.lower().strip(),
            username=username,
            hashed_password=hash_password(password),
            full_name="Admin",
            role=Role.ADMIN.value,
            is_active=True,
            is_verified=True,
        )
        await session.commit()
        print(f"[seed] Created admin: {email}")


if __name__ == "__main__":
    asyncio.run(main())
