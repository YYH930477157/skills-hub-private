from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import yaml

from skillhub.config import settings

SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_FILES = 400

SKIP_NAMES = {".ds_store", "thumbs.db", "__macosx"}


class PackageError(ValueError):
    pass


def validate_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise PackageError("技能标识必须是 2-64 位小写字母、数字和连字符，且不能以连字符开头或结尾")
    return slug


def validate_version(version: str) -> str:
    version = (version or "").strip()
    if not VERSION_RE.match(version):
        raise PackageError("版本号必须是 x.y.z 形式，例如 1.0.0")
    return version


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.lstrip().startswith("---"):
        raise PackageError("SKILL.md 必须以 YAML frontmatter（---）开头，并包含 name 和 description")
    stripped = text.lstrip()
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        raise PackageError("SKILL.md frontmatter 不完整")
    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise PackageError("SKILL.md frontmatter 必须是 YAML 对象")
    body = parts[2].lstrip("\n")
    return meta, body


def version_dir(slug: str, version: str) -> Path:
    return settings.packages_dir / slug / version


def files_dir(slug: str, version: str) -> Path:
    return version_dir(slug, version) / "files"


def canonical_zip_path(slug: str, version: str) -> Path:
    return version_dir(slug, version) / "skill.zip"


def archive_zip_path(slug: str, version: str) -> Path:
    return version_dir(slug, version) / "plugin.zip"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_join(root: Path, *parts: str) -> Path:
    dest = (root / Path(*parts)).resolve()
    if dest != root.resolve() and root.resolve() not in dest.parents:
        raise PackageError("压缩包包含非法路径")
    return dest


def _is_skipped(name: str) -> bool:
    lower = name.replace("\\", "/").lower()
    return any(part in SKIP_NAMES for part in lower.split("/"))


def extract_skill_from_zip(raw: bytes) -> dict[str, bytes]:
    if len(raw) > MAX_ZIP_BYTES:
        raise PackageError("压缩包不能超过 50MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise PackageError("不是有效的 zip 文件") from exc

    names = [n for n in zf.namelist() if not n.endswith("/") and not _is_skipped(n)]
    if len(names) > MAX_FILES:
        raise PackageError("压缩包文件过多")
    if not names:
        raise PackageError("压缩包是空的")

    files: dict[str, bytes] = {}
    for name in names:
        path = name.replace("\\", "/").lstrip("/")
        if ".." in path.split("/"):
            raise PackageError("压缩包包含非法路径")
        data = zf.read(name)
        files[path] = data
    return _normalize_skill_tree(files)


def extract_skill_from_markdown(text: str) -> dict[str, bytes]:
    meta, _ = parse_frontmatter(text)
    slug = validate_slug(str(meta.get("name") or "").strip())
    return {f"{slug}/SKILL.md": text.encode("utf-8")}


def _normalize_skill_tree(files: dict[str, bytes]) -> dict[str, bytes]:
    skill_md_paths = [p for p in files if p.replace("\\", "/").split("/")[-1] == "SKILL.md"]
    if not skill_md_paths:
        raise PackageError("压缩包中必须包含 SKILL.md")
    skill_md_paths.sort(key=lambda p: p.count("/"))
    skill_path = skill_md_paths[0]
    parent = str(Path(skill_path).parent).replace("\\", "/")
    if parent in {".", ""}:
        meta, _ = parse_frontmatter(files[skill_path].decode("utf-8"))
        slug = validate_slug(str(meta.get("name") or "skill"))
        return {f"{slug}/{Path(p).name if '/' not in p else p}": files[p] for p in files}

    prefix = parent.rstrip("/") + "/"
    out: dict[str, bytes] = {}
    for path, data in files.items():
        norm = path.replace("\\", "/")
        if norm.startswith(prefix):
            out[norm] = data
        elif "/" not in norm:
            out[prefix + norm] = data
    if not any(p.endswith("/SKILL.md") or p.endswith("SKILL.md") for p in out):
        raise PackageError("无法从压缩包中定位技能目录")
    return out


def skill_root_name(files: dict[str, bytes]) -> str:
    for path in files:
        if path.endswith("SKILL.md"):
            return path.split("/")[0]
    raise PackageError("找不到 SKILL.md")


def skill_md_text(files: dict[str, bytes]) -> str:
    for path, data in files.items():
        if path.endswith("SKILL.md"):
            return data.decode("utf-8")
    raise PackageError("找不到 SKILL.md")


def write_tree(dest: Path, files: dict[str, bytes]) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        target = _safe_join(dest, *rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def zip_tree(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not _is_skipped(path.name):
                zf.write(path, path.relative_to(root).as_posix())
    return buf.getvalue()


def zip_mapping(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files):
            zf.writestr(path, files[path])
    return buf.getvalue()


def plugin_manifests(slug: str, version: str, description: str, author: str) -> dict[str, bytes]:
    claude = {
        "name": slug,
        "version": version,
        "description": description,
        "author": {"name": author},
    }
    grok = {
        "name": slug,
        "version": version,
        "description": description,
        "author": {"name": author},
    }
    codex = {
        "name": slug,
        "version": version,
        "description": description,
        "author": {"name": author, "email": settings.owner_email},
        "keywords": ["skillhub", "skills"],
        "interface": {
            "displayName": slug,
            "shortDescription": description[:125],
        },
    }
    return {
        ".claude-plugin/plugin.json": json.dumps(claude, ensure_ascii=False, indent=2).encode("utf-8"),
        ".codex-plugin/plugin.json": json.dumps(codex, ensure_ascii=False, indent=2).encode("utf-8"),
        "plugin.json": json.dumps(grok, ensure_ascii=False, indent=2).encode("utf-8"),
    }


def to_plugin_files(
    files: dict[str, bytes], slug: str, version: str, description: str, author: str
) -> dict[str, bytes]:
    root = skill_root_name(files)
    plugin: dict[str, bytes] = {}
    for path, data in files.items():
        rel = path[len(root) :].lstrip("/")
        plugin[f"skills/{slug}/{rel}"] = data
    plugin.update(plugin_manifests(slug, version, description, author))
    return plugin


def save_version(
    slug: str,
    version: str,
    files: dict[str, bytes],
    description: str,
    author: str,
) -> dict:
    dest = files_dir(slug, version)
    write_tree(dest, files)
    canonical = zip_mapping(files)
    canonical_path = canonical_zip_path(slug, version)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(canonical)

    plugin_files = to_plugin_files(files, slug, version, description, author)
    wrapped = {f"{slug}/{k}": v for k, v in plugin_files.items()}
    archive = zip_mapping(wrapped)
    archive_path = archive_zip_path(slug, version)
    archive_path.write_bytes(archive)

    return {
        "sha256": sha256_bytes(canonical),
        "archive_sha256": sha256_bytes(archive),
        "size_bytes": len(canonical),
        "skill_md": skill_md_text(files),
        "files": files,
        "plugin_files": plugin_files,
    }
