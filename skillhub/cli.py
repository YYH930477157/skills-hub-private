from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_DIR = Path.home() / ".skillhub"
CONFIG_PATH = CONFIG_DIR / "config.json"
INSTALLED_PATH = CONFIG_DIR / "installed.json"
MARKETPLACE_DIR = CONFIG_DIR / "marketplace"

TARGETS = {
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".agents" / "skills",
    "grok": Path.home() / ".grok" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skillhub", description="SkillHub CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="启动 SkillHub 服务")
    serve.add_argument("--host", default=os.environ.get("SKILLHUB_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("SKILLHUB_PORT", "8000")))
    serve.add_argument("--reload", action="store_true")

    login = sub.add_parser("login", help="登录服务器")
    login.add_argument("url")
    login.add_argument("--username")
    login.add_argument("--password")
    login.add_argument("--token", help="直接保存已有 JWT 或 API token")

    sub.add_parser("whoami", help="查看当前登录")

    ls = sub.add_parser("list", help="列出服务器上的技能")
    ls.add_argument("--q", default="")
    ls.add_argument("--category", default="")

    search = sub.add_parser("search", help="搜索技能")
    search.add_argument("query")

    inst = sub.add_parser("install", help="安装一个技能到本机 IDE 目录")
    inst.add_argument("slug")
    inst.add_argument("--targets", default="claude,codex,grok,cursor")

    upd = sub.add_parser("update", help="更新已安装技能")
    upd.add_argument("slug", nargs="?")
    upd.add_argument("--targets", default="claude,codex,grok,cursor")

    sync = sub.add_parser("sync", help="安装服务器上全部技能")
    sync.add_argument("--targets", default="claude,codex,grok,cursor")

    sub.add_parser("connect", help="登录后拉取市场快照并给出 IDE 接入命令")
    sub.add_parser("marketplace-pull", help="拉取可被 IDE 添加的本地 marketplace 快照")

    args = parser.parse_args(argv)
    handlers = {
        "serve": cmd_serve,
        "login": cmd_login,
        "whoami": cmd_whoami,
        "list": cmd_list,
        "search": cmd_search,
        "install": cmd_install,
        "update": cmd_update,
        "sync": cmd_sync,
        "connect": cmd_connect,
        "marketplace-pull": cmd_marketplace_pull,
    }
    try:
        return handlers[args.cmd](args)
    except CLIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


class CLIError(RuntimeError):
    pass


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("skillhub.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_login(args) -> int:
    url = args.url.rstrip("/")
    if args.token:
        cfg = {"url": url, "token": args.token}
        _save_config(cfg)
        print(f"已保存 {url}")
        return 0
    username = args.username or input("用户名: ").strip()
    password = args.password or getpass.getpass("密码: ")
    data = _request("POST", f"{url}/api/auth/login", json_body={"username": username, "password": password})
    token = data["token"]
    me_token = _request("POST", f"{url}/api/auth/api-token", token=token)
    cfg = {
        "url": url,
        "token": token,
        "api_token": me_token["api_token"],
        "username": data["user"]["username"],
    }
    _save_config(cfg)
    print(f"已登录 {data['user']['display_name']} @ {url}")
    print(f"API token: {me_token['api_token']}")
    return 0


def cmd_whoami(args) -> int:
    cfg = _load_config()
    me = _request("GET", f"{cfg['url']}/api/auth/me", token=_token(cfg))
    print(json.dumps(me, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args) -> int:
    cfg = _load_config()
    skills = _request(
        "GET",
        f"{cfg['url']}/api/skills",
        token=_token(cfg),
        query={"q": args.q, "category": args.category},
    )
    _print_skills(skills)
    return 0


def cmd_search(args) -> int:
    cfg = _load_config()
    skills = _request("GET", f"{cfg['url']}/api/skills", token=_token(cfg), query={"q": args.query})
    _print_skills(skills)
    return 0


def cmd_install(args) -> int:
    cfg = _load_config()
    _install_one(cfg, args.slug, _parse_targets(args.targets))
    return 0


def cmd_update(args) -> int:
    cfg = _load_config()
    installed = _load_installed()
    slugs = [args.slug] if args.slug else list(installed)
    if not slugs:
        print("还没有已安装的技能。先 skillhub install <slug> 或 skillhub sync")
        return 0
    targets = _parse_targets(args.targets)
    for slug in slugs:
        _install_one(cfg, slug, targets)
    cmd_marketplace_pull(args)
    return 0


def cmd_sync(args) -> int:
    cfg = _load_config()
    skills = _request("GET", f"{cfg['url']}/api/skills", token=_token(cfg))
    targets = _parse_targets(args.targets)
    for skill in skills:
        _install_one(cfg, skill["slug"], targets)
    cmd_marketplace_pull(args)
    return 0


def cmd_connect(args) -> int:
    cfg = _load_config()
    cmd_marketplace_pull(args)
    info = _request("GET", f"{cfg['url']}/api/connect", token=_token(cfg))
    local = str(MARKETPLACE_DIR)
    print()
    print(f"{info['org_name']} 已连接到 {cfg['url']}")
    print(f"本地市场快照: {local}")
    print()
    print("把这个目录加到各 IDE，之后用 skillhub update 更新：")
    print(f"  claude plugin marketplace add {local}")
    print(f"  codex plugin marketplace add {local}")
    print(f"  grok plugin marketplace add {local}")
    print()
    print("同步技能文件到本机 skills 目录（可选，适合不想走 plugin 的场景）：")
    print("  skillhub sync")
    print()
    print("Claude 在生产环境（HTTPS 非 localhost）还可以直接加远程源：")
    print(f"  {info['claude']['https_archive']}")
    return 0


def cmd_marketplace_pull(args) -> int:
    cfg = _load_config()
    raw = _request_bytes("GET", f"{cfg['url']}/api/marketplace/snapshot.zip", token=_token(cfg))
    if MARKETPLACE_DIR.exists():
        shutil.rmtree(MARKETPLACE_DIR)
    MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io_bytes(raw)) as zf:
        zf.extractall(MARKETPLACE_DIR)
    print(f"市场快照已更新: {MARKETPLACE_DIR}")
    return 0


def io_bytes(raw: bytes):
    import io

    return io.BytesIO(raw)


def _install_one(cfg: dict, slug: str, targets: list[str]) -> None:
    raw = _request_bytes("GET", f"{cfg['url']}/api/skills/{slug}/package", token=_token(cfg))
    detail = _request("GET", f"{cfg['url']}/api/skills/{slug}", token=_token(cfg))
    tmp = CONFIG_DIR / "tmp" / slug
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io_bytes(raw)) as zf:
        zf.extractall(tmp)
    skill_dir = tmp / slug
    if not skill_dir.exists():
        matches = [p for p in tmp.iterdir() if p.is_dir()]
        if not matches:
            raise CLIError("安装包结构无效")
        skill_dir = matches[0]
    for name in targets:
        dest_root = TARGETS[name]
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / slug
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        print(f"installed {slug}@{detail['latest_version']} -> {dest}")
    installed = _load_installed()
    installed[slug] = {"version": detail["latest_version"], "targets": targets}
    _save_installed(installed)
    shutil.rmtree(tmp, ignore_errors=True)


def _print_skills(skills: list[dict]) -> None:
    if not skills:
        print("(empty)")
        return
    print(f"{'SLUG':<24} {'VER':<8} {'★':<4} {'AUTHOR':<12} DESCRIPTION")
    for s in skills:
        desc = s["description"].replace("\n", " ")
        if len(desc) > 72:
            desc = desc[:69] + "..."
        print(
            f"{s['slug']:<24} {s['latest_version']:<8} {s['rating_avg']:<4} {s['author_name']:<12} {desc}"
        )


def _parse_targets(raw: str) -> list[str]:
    names = [t.strip() for t in raw.split(",") if t.strip()]
    unknown = [t for t in names if t not in TARGETS]
    if unknown:
        raise CLIError(f"未知目标: {', '.join(unknown)}")
    return names


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise CLIError("尚未登录，先运行: skillhub login http://your-server:8000")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _load_installed() -> dict:
    if not INSTALLED_PATH.exists():
        return {}
    return json.loads(INSTALLED_PATH.read_text(encoding="utf-8"))


def _save_installed(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    INSTALLED_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _token(cfg: dict) -> str:
    return cfg.get("api_token") or cfg.get("token") or ""


def _request(method: str, url: str, token: str = "", json_body=None, query=None):
    raw = _request_bytes(method, url, token=token, json_body=json_body, query=query)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _request_bytes(method: str, url: str, token: str = "", json_body=None, query=None) -> bytes:
    if query:
        from urllib.parse import urlencode

        filtered = {k: v for k, v in query.items() if v}
        if filtered:
            url = url + ("&" if "?" in url else "?") + urlencode(filtered)
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        if token.startswith("sh_"):
            headers["X-Api-Token"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return resp.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body or str(exc)
        raise CLIError(f"{exc.code} {detail}") from exc
    except URLError as exc:
        raise CLIError(f"无法连接服务器: {exc.reason}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
