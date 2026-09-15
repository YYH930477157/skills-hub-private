from __future__ import annotations

import json
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from skillhub.categories import CODEX_CATEGORY
from skillhub.config import settings
from skillhub.models import Skill, SkillVersion
from skillhub.packages import files_dir, to_plugin_files, write_tree


MARKETPLACE_NAME = "skillhub"


def _latest_version(skill: Skill, db: Session) -> SkillVersion | None:
    return (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill.id, SkillVersion.version == skill.latest_version)
        .one_or_none()
    )


def claude_marketplace_payload(skills: list[Skill], db: Session, public_url: str) -> dict:
    plugins = []
    for skill in skills:
        ver = _latest_version(skill, db)
        if not ver:
            continue
        plugins.append(
            {
                "name": skill.slug,
                "description": skill.description,
                "version": skill.latest_version,
                "author": {"name": skill.author_name},
                "category": skill.category,
                "tags": skill.tag_list,
                "source": {
                    "source": "archive",
                    "url": f"{public_url}/api/skills/{skill.slug}/archive.zip",
                    "sha256": ver.archive_sha256,
                },
            }
        )
    return {
        "name": MARKETPLACE_NAME,
        "description": f"{settings.org_name} 内部 Agent Skills 市场",
        "owner": {"name": settings.org_name, "email": settings.owner_email},
        "metadata": {"description": "Published by SkillHub"},
        "plugins": plugins,
    }


def claude_local_marketplace(skills: list[Skill], db: Session) -> dict:
    plugins = []
    for skill in skills:
        if not _latest_version(skill, db):
            continue
        plugins.append(
            {
                "name": skill.slug,
                "source": f"./plugins/{skill.slug}",
                "description": skill.description,
                "version": skill.latest_version,
                "author": {"name": skill.author_name},
                "category": skill.category,
                "tags": skill.tag_list,
            }
        )
    return {
        "name": MARKETPLACE_NAME,
        "description": f"{settings.org_name} 内部 Agent Skills 市场",
        "owner": {"name": settings.org_name, "email": settings.owner_email},
        "plugins": plugins,
    }


def codex_marketplace(skills: list[Skill], db: Session) -> dict:
    plugins = []
    for skill in skills:
        if not _latest_version(skill, db):
            continue
        plugins.append(
            {
                "name": skill.slug,
                "source": {"source": "local", "path": f"./plugins/{skill.slug}"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": _codex_category(skill.category),
            }
        )
    return {
        "name": MARKETPLACE_NAME,
        "interface": {"displayName": settings.org_name},
        "plugins": plugins,
    }


def grok_marketplace(skills: list[Skill], db: Session) -> dict:
    plugins = []
    for skill in skills:
        if not _latest_version(skill, db):
            continue
        plugins.append(
            {
                "name": skill.slug,
                "description": skill.description,
                "version": skill.latest_version,
                "category": skill.category,
                "author": {"name": skill.author_name},
                "tags": skill.tag_list,
                "source": {"type": "local", "path": f"./plugins/{skill.slug}"},
            }
        )
    return {
        "name": settings.org_name,
        "description": f"{settings.org_name} 内部 Agent Skills 市场",
        "owner": {"name": settings.org_name, "email": settings.owner_email},
        "plugins": plugins,
    }


def grok_plugin_index(skills: list[Skill], db: Session) -> dict:
    plugins: dict = {}
    for skill in skills:
        if not _latest_version(skill, db):
            continue
        plugins[skill.slug] = {
            "components": {
                "skills": [{"name": skill.slug, "description": skill.description}]
            }
        }
    return {"version": 1, "plugins": plugins}


def _codex_category(category: str) -> str:
    return CODEX_CATEGORY.get(category, "Development")


def rebuild_marketplace(db: Session) -> Path:
    root = settings.marketplace_dir
    if root.exists():
        shutil.rmtree(root)
    plugins_dir = root / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    skills = db.query(Skill).order_by(Skill.slug.asc()).all()
    for skill in skills:
        ver = _latest_version(skill, db)
        if not ver:
            continue
        src = files_dir(skill.slug, ver.version)
        files: dict[str, bytes] = {}
        if src.exists():
            for path in src.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(src).as_posix()
                    files[rel] = path.read_bytes()
        if not files:
            continue
        plugin_files = to_plugin_files(
            files, skill.slug, ver.version, skill.description, skill.author_name
        )
        write_tree(plugins_dir / skill.slug, plugin_files)

    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".agents" / "plugins").mkdir(parents=True, exist_ok=True)
    (root / ".grok-plugin").mkdir(parents=True, exist_ok=True)

    _write_json(root / ".claude-plugin" / "marketplace.json", claude_local_marketplace(skills, db))
    _write_json(root / ".agents" / "plugins" / "marketplace.json", codex_marketplace(skills, db))
    _write_json(root / ".grok-plugin" / "marketplace.json", grok_marketplace(skills, db))
    _write_json(root / ".grok-plugin" / "plugin-index.json", grok_plugin_index(skills, db))
    (root / "README.md").write_text(
        f"# {settings.org_name}\n\nGenerated by SkillHub. Add this folder as a plugin marketplace.\n",
        encoding="utf-8",
    )
    return root


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
