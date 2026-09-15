from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from skillhub.auth import can_edit_skill, get_current_user, require_read
from skillhub.categories import CATEGORY_IDS, DEFAULT_CATEGORY, normalize_category
from skillhub.db import get_db
from skillhub.marketplace import rebuild_marketplace
from skillhub.models import Rating, Skill, SkillVersion, User, utcnow
from skillhub.packages import (
    PackageError,
    archive_zip_path,
    canonical_zip_path,
    extract_skill_from_markdown,
    extract_skill_from_zip,
    parse_frontmatter,
    skill_md_text,
    skill_root_name,
    validate_slug,
    validate_version,
    save_version,
)
from skillhub.schemas import RateIn, RatingOut, SkillDetail, SkillSummary, VersionOut

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _summary(skill: Skill) -> SkillSummary:
    return SkillSummary(
        slug=skill.slug,
        name=skill.name,
        description=skill.description,
        category=skill.category,
        tags=skill.tag_list,
        author_id=skill.author_id,
        author_name=skill.author_name,
        latest_version=skill.latest_version,
        install_count=skill.install_count,
        rating_avg=skill.rating_avg,
        rating_count=skill.rating_count,
        updated_at=skill.updated_at,
    )


def _rating_out(row: Rating) -> RatingOut:
    return RatingOut(
        username=row.user.username,
        display_name=row.user.display_name,
        stars=row.stars,
        comment=row.comment,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[SkillSummary])
def list_skills(
    q: str = "",
    category: str = "",
    sort: str = Query(default="updated"),
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    query = db.query(Skill)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Skill.slug.ilike(like),
                Skill.name.ilike(like),
                Skill.description.ilike(like),
                Skill.tags.ilike(like),
                Skill.author_name.ilike(like),
            )
        )
    if category.strip():
        query = query.filter(Skill.category == category.strip())
    if sort == "rating":
        query = query.order_by(Skill.rating_count.desc(), Skill.rating_sum.desc(), Skill.updated_at.desc())
    elif sort == "installs":
        query = query.order_by(Skill.install_count.desc(), Skill.updated_at.desc())
    elif sort == "name":
        query = query.order_by(Skill.slug.asc())
    else:
        query = query.order_by(Skill.updated_at.desc())
    return [_summary(s) for s in query.all()]


@router.get("/{slug}", response_model=SkillDetail)
def get_skill(
    slug: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(require_read),
):
    skill = db.query(Skill).filter(Skill.slug == slug).one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    versions = (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill.id)
        .order_by(SkillVersion.created_at.desc())
        .all()
    )
    latest = next((v for v in versions if v.version == skill.latest_version), versions[0] if versions else None)
    ratings = (
        db.query(Rating)
        .filter(Rating.skill_id == skill.id)
        .order_by(Rating.updated_at.desc())
        .all()
    )
    mine = None
    if user:
        mine = next((r for r in ratings if r.user_id == user.id), None)
    return SkillDetail(
        **_summary(skill).model_dump(),
        skill_md=latest.skill_md if latest else "",
        versions=[
            VersionOut(
                version=v.version,
                changelog=v.changelog,
                sha256=v.sha256,
                size_bytes=v.size_bytes,
                created_at=v.created_at,
            )
            for v in versions
        ],
        ratings=[_rating_out(r) for r in ratings],
        my_rating=_rating_out(mine) if mine else None,
    )


@router.post("")
async def publish_skill(
    category: str = Form(default=DEFAULT_CATEGORY),
    tags: str = Form(default=""),
    version: str = Form(default="1.0.0"),
    changelog: str = Form(default="初始版本"),
    slug: str = Form(default=""),
    markdown: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        files, meta_slug, description = await _load_upload(file, markdown, slug)
        version = validate_version(version or "1.0.0")
        category = normalize_category(category)
        if category not in CATEGORY_IDS:
            raise PackageError("不支持的分类")
        existing = db.query(Skill).filter(Skill.slug == meta_slug).one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="该技能已存在，请发布新版本")
        saved = save_version(meta_slug, version, files, description, user.display_name)
        skill = Skill(
            slug=meta_slug,
            name=str(meta_slug),
            description=description,
            category=category,
            tags=tags.strip(),
            author_id=user.id,
            author_name=user.display_name,
            latest_version=version,
            updated_at=utcnow(),
        )
        db.add(skill)
        db.flush()
        db.add(
            SkillVersion(
                skill_id=skill.id,
                version=version,
                changelog=changelog.strip() or "初始版本",
                sha256=saved["sha256"],
                archive_sha256=saved["archive_sha256"],
                size_bytes=saved["size_bytes"],
                skill_md=saved["skill_md"],
            )
        )
        db.commit()
        rebuild_marketplace(db)
        return {"slug": meta_slug, "version": version}
    except PackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{slug}/versions")
async def publish_version(
    slug: str,
    version: str = Form(...),
    changelog: str = Form(default=""),
    markdown: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    skill = db.query(Skill).filter(Skill.slug == slug).one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    if not can_edit_skill(user, skill.author_id):
        raise HTTPException(status_code=403, detail="只有作者或管理员可以发布新版本")
    try:
        files, meta_slug, description = await _load_upload(file, markdown, slug)
        if meta_slug != slug:
            raise PackageError(f"SKILL.md 中的 name 必须是 {slug}")
        version = validate_version(version)
        if db.query(SkillVersion).filter(SkillVersion.skill_id == skill.id, SkillVersion.version == version).first():
            raise HTTPException(status_code=409, detail="该版本已存在")
        saved = save_version(slug, version, files, description, skill.author_name)
        skill.description = description
        skill.latest_version = version
        skill.updated_at = utcnow()
        db.add(
            SkillVersion(
                skill_id=skill.id,
                version=version,
                changelog=changelog.strip(),
                sha256=saved["sha256"],
                archive_sha256=saved["archive_sha256"],
                size_bytes=saved["size_bytes"],
                skill_md=saved["skill_md"],
            )
        )
        db.commit()
        rebuild_marketplace(db)
        return {"slug": slug, "version": version}
    except PackageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{slug}/rate", response_model=SkillSummary)
def rate_skill(
    slug: str,
    body: RateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    skill = db.query(Skill).filter(Skill.slug == slug).one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    row = (
        db.query(Rating)
        .filter(Rating.skill_id == skill.id, Rating.user_id == user.id)
        .one_or_none()
    )
    now = utcnow()
    if row:
        skill.rating_sum -= row.stars
        skill.rating_count -= 1
        row.stars = body.stars
        row.comment = body.comment.strip()
        row.updated_at = now
    else:
        row = Rating(
            skill_id=skill.id,
            user_id=user.id,
            stars=body.stars,
            comment=body.comment.strip(),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    skill.rating_sum += body.stars
    skill.rating_count += 1
    db.commit()
    db.refresh(skill)
    return _summary(skill)


@router.get("/{slug}/package")
def download_package(
    slug: str,
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    skill, _ver = _latest(db, slug)
    path = canonical_zip_path(skill.slug, skill.latest_version)
    if not path.exists():
        raise HTTPException(status_code=404, detail="安装包不存在")
    skill.install_count += 1
    db.commit()
    return Response(
        path.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@router.get("/{slug}/archive.zip")
def download_archive(
    slug: str,
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    skill, _ver = _latest(db, slug)
    path = archive_zip_path(skill.slug, skill.latest_version)
    if not path.exists():
        raise HTTPException(status_code=404, detail="插件包不存在")
    skill.install_count += 1
    db.commit()
    return Response(
        path.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}-plugin.zip"'},
    )


@router.get("/{slug}/SKILL.md", response_class=PlainTextResponse)
def download_skill_md(
    slug: str,
    db: Session = Depends(get_db),
    _user: User | None = Depends(require_read),
):
    skill, ver = _latest(db, slug)
    return ver.skill_md or ""


def _latest(db: Session, slug: str) -> tuple[Skill, SkillVersion]:
    skill = db.query(Skill).filter(Skill.slug == slug).one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    ver = (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill.id, SkillVersion.version == skill.latest_version)
        .one_or_none()
    )
    if not ver:
        raise HTTPException(status_code=404, detail="版本不存在")
    return skill, ver


async def _load_upload(
    file: UploadFile | None, markdown: str, slug_hint: str
) -> tuple[dict[str, bytes], str, str]:
    if file and file.filename:
        raw = await file.read()
        files = extract_skill_from_zip(raw)
    elif markdown.strip():
        files = extract_skill_from_markdown(markdown)
    else:
        raise PackageError("请上传包含 SKILL.md 的 zip，或直接粘贴 SKILL.md 文本")
    text = skill_md_text(files)
    meta, _ = parse_frontmatter(text)
    name = str(meta.get("name") or slug_hint or skill_root_name(files)).strip()
    slug = validate_slug(name)
    description = str(meta.get("description") or "").strip()
    if not description:
        raise PackageError("SKILL.md 必须包含 description")
    return files, slug, description
