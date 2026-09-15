from __future__ import annotations

from sqlalchemy.orm import Session

CATEGORIES = [
    {"id": "docs", "label": "文档"},
    {"id": "smartset", "label": "SmartSet"},
    {"id": "code", "label": "代码"},
    {"id": "test", "label": "测试"},
    {"id": "protocol", "label": "协议"},
    {"id": "debug", "label": "调试"},
    {"id": "toolchain", "label": "工具链"},
    {"id": "hardware", "label": "硬件"},
]

CATEGORY_IDS = {item["id"] for item in CATEGORIES}
DEFAULT_CATEGORY = "docs"

LEGACY_CATEGORY = {
    "general": "docs",
    "finance": "docs",
    "legal": "docs",
    "ops": "docs",
    "sales": "docs",
    "hr": "docs",
    "engineering": "code",
}

CODEX_CATEGORY = {
    "docs": "Productivity",
    "smartset": "Development",
    "code": "Development",
    "test": "Development",
    "protocol": "Development",
    "debug": "Development",
    "toolchain": "Development",
    "hardware": "Development",
}


def normalize_category(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in CATEGORY_IDS:
        return raw
    return LEGACY_CATEGORY.get(raw, DEFAULT_CATEGORY)


def migrate_categories(db: Session) -> int:
    from skillhub.models import Skill

    changed = 0
    for skill in db.query(Skill).all():
        mapped = normalize_category(skill.category)
        if mapped != skill.category:
            skill.category = mapped
            changed += 1
    if changed:
        db.commit()
    return changed
