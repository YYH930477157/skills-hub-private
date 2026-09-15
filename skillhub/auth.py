from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from skillhub.config import settings
from skillhub.db import get_db
from skillhub.models import User

PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, digest = stored.split("$", 3)
        if scheme != "pbkdf2":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iters)
        ).hex()
        return hmac.compare_digest(check, digest)
    except ValueError:
        return False


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_hours),
    }
    return jwt.encode(payload, settings.secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="登录已过期或无效") from exc


def new_api_token() -> str:
    return "sh_" + secrets.token_urlsafe(32)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return (
        request.headers.get("X-Api-Token")
        or request.query_params.get("token")
        or None
    )


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _extract_token(request)
    if not token:
        return None
    if token.startswith("sh_"):
        return db.query(User).filter(User.api_token == token).one_or_none()
    payload = decode_token(token)
    return db.get(User, int(payload["sub"]))


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_read(user: User | None = Depends(get_optional_user)) -> User | None:
    if settings.public_read:
        return user
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def can_edit_skill(user: User, author_id: int) -> bool:
    return user.is_admin or user.id == author_id



