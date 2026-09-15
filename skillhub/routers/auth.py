from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from skillhub.auth import (
    create_token,
    get_current_user,
    hash_password,
    new_api_token,
    verify_password,
)
from skillhub.db import get_db
from skillhub.models import User
from skillhub.schemas import AuthIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{2,64}$")


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_admin=user.is_admin,
        has_api_token=bool(user.api_token),
    )


@router.post("/register", response_model=TokenOut)
def register(body: AuthIn, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="用户名仅允许字母、数字和下划线")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    is_first = db.query(User).count() == 0
    user = User(
        username=username,
        display_name=(body.display_name or username).strip(),
        password_hash=hash_password(body.password),
        is_admin=is_first,
        api_token=new_api_token() if is_first else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(token=create_token(user), user=_user_out(user))


@router.post("/login", response_model=TokenOut)
def login(body: AuthIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip()).one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenOut(token=create_token(user), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.post("/api-token")
def issue_api_token(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.api_token = new_api_token()
    db.commit()
    return {"api_token": user.api_token}
