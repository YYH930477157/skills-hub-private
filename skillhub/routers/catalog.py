from __future__ import annotations

import io
import zipfile
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from skillhub.auth import require_read
from skillhub.categories import CATEGORIES
from skillhub.config import settings
from skillhub.db import get_db
from skillhub.marketplace import (
    claude_marketplace_payload,
    claude_local_marketplace,
    codex_marketplace,
    grok_marketplace,
    rebuild_marketplace,
)
from skillhub.models import Skill, User

router = APIRouter(tags=["catalog"])


def _skills(db: Session) -> list[Skill]:
    return db.query(Skill).order_by(Skill.slug.asc()).all()


@router.get("/api/meta")
def meta():
    return {
        "org_name": settings.org_name,
        "public_url": settings.public_url,
        "public_read": settings.public_read,
        "categories": CATEGORIES,
    }


@router.get("/api/claude/marketplace.json")
def claude_marketplace(
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    return claude_marketplace_payload(_skills(db), db, settings.public_url)


@router.get("/api/claude/local-marketplace.json")
def claude_local(
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    return claude_local_marketplace(_skills(db), db)


@router.get("/api/codex/marketplace.json")
def codex_market(
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    return codex_marketplace(_skills(db), db)


@router.get("/api/grok/marketplace.json")
def grok_market(
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    return grok_marketplace(_skills(db), db)


@router.get("/.well-known/agent-skills/index.json")
def agent_skills_index(
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    items = []
    for skill in _skills(db):
        items.append(
            {
                "name": skill.slug,
                "description": skill.description,
                "url": f"{settings.public_url}/api/skills/{skill.slug}/SKILL.md",
                "version": skill.latest_version,
                "author": skill.author_name,
            }
        )
    return {"version": "1.0", "skills": items}


@router.get("/api/marketplace/snapshot.zip")
def snapshot(
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    root = rebuild_marketplace(db)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="skillhub-marketplace.zip"'},
    )


@router.get("/api/connect")
def connect_info(_user: User | None = Depends(require_read)):
    base = settings.public_url
    local = "~/.skillhub/marketplace"
    return {
        "org_name": settings.org_name,
        "cli": [
            f"pip install -e .  # 或在服务器上: pip install skillhub",
            f"skillhub login {base} --username <你的用户名>",
            "skillhub connect",
            "skillhub update",
        ],
        "claude": {
            "https_archive": f"claude plugin marketplace add {base}/api/claude/marketplace.json",
            "local_snapshot": f"claude plugin marketplace add {local}",
            "update": "claude plugin marketplace update skillhub",
            "note": "archive 源要求 HTTPS 且非 localhost。内网演示请用 CLI 拉取本地快照。",
        },
        "codex": {
            "local_snapshot": f"codex plugin marketplace add {local}",
            "update": "skillhub marketplace-pull && codex plugin marketplace upgrade skillhub",
            "note": "Codex 目前只接受 git 仓库或本地目录作为 marketplace 源，不接受纯 JSON URL。",
        },
        "grok": {
            "local_snapshot": f"grok plugin marketplace add {local}",
            "update": "skillhub marketplace-pull && grok plugin marketplace update skillhub",
            "skill_dirs": "skillhub sync 会把技能同步到 ~/.grok/skills、~/.agents/skills、~/.claude/skills、~/.cursor/skills",
        },
    }
