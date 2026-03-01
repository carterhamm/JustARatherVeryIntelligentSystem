"""Authentication business logic — registration, login, token refresh, user CRUD."""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserUpdate


class AuthService:
    """Stateless service — every method receives the DB session explicitly."""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
        """Fetch a user by primary key."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Fetch a user by e-mail address."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """Fetch a user by username."""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @staticmethod
    async def register(db: AsyncSession, payload: UserCreate) -> Token:
        """Create a new user and return a JWT token pair.

        Raises ``409 Conflict`` when the email or username is already taken.
        """
        user = User(
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
        )
        db.add(user)

        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            detail = "Email or username already registered"
            if "email" in str(exc.orig).lower():
                detail = "Email already registered"
            elif "username" in str(exc.orig).lower():
                detail = "Username already taken"
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc

        await db.commit()
        await db.refresh(user)

        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    @staticmethod
    async def login(db: AsyncSession, email: str, password: str) -> Token:
        """Verify credentials and return a JWT token pair.

        Raises ``401 Unauthorized`` on bad credentials.
        """
        user = await AuthService.get_user_by_email(db, email)

        if user is None or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    @staticmethod
    async def refresh_token(db: AsyncSession, refresh_token_str: str) -> Token:
        """Exchange a valid refresh token for a fresh token pair.

        Raises ``401 Unauthorized`` if the token is invalid or the user
        no longer exists.
        """
        payload = decode_token(refresh_token_str)

        if payload.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type — expected refresh token",
            )

        user = await AuthService.get_user_by_id(db, UUID(payload.sub))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        return Token(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    # ------------------------------------------------------------------
    # Profile update
    # ------------------------------------------------------------------

    @staticmethod
    async def update_user(db: AsyncSession, user_id: UUID, payload: UserUpdate) -> User:
        """Apply partial updates to the user's profile.

        Only fields that are explicitly set (not ``None``) are written.
        """
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        # Check username uniqueness if being updated
        if "username" in update_data:
            existing = await AuthService.get_user_by_username(db, update_data["username"])
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username already taken",
                )

        await db.execute(
            update(User).where(User.id == user_id).values(**update_data)
        )
        await db.commit()

        user = await AuthService.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found after update",
            )
        return user

    # ------------------------------------------------------------------
    # Deactivation
    # ------------------------------------------------------------------

    @staticmethod
    async def deactivate_user(db: AsyncSession, user_id: UUID) -> User:
        """Soft-delete a user by setting ``is_active = False``."""
        await db.execute(
            update(User).where(User.id == user_id).values(is_active=False)
        )
        await db.commit()

        user = await AuthService.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return user
