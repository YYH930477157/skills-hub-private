from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from skillhub.main import app

client = TestClient(app)


def test_categories_are_embedded_oriented():
    res = client.get("/api/meta")
    assert res.status_code == 200
    ids = [c["id"] for c in res.json()["categories"]]
    assert ids == ["docs", "smartset", "code", "test", "protocol", "debug", "toolchain", "hardware"]
    labels = {c["id"]: c["label"] for c in res.json()["categories"]}
    assert labels["docs"] == "文档"
    assert labels["smartset"] == "SmartSet"
    assert labels["code"] == "代码"
    assert labels["test"] == "测试"


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_seeded_catalog():
    res = client.get("/api/skills")
    assert res.status_code == 200
    slugs = {s["slug"] for s in res.json()}
    assert "invoice-check" in slugs
    assert "contract-clause" in slugs
    assert "weekly-report" in slugs
    cats = {s["slug"]: s["category"] for s in res.json()}
    assert set(cats.values()) <= {
        "docs",
        "smartset",
        "code",
        "test",
        "protocol",
        "debug",
        "toolchain",
        "hardware",
    }


def test_skill_detail_and_markdown():
    res = client.get("/api/skills/invoice-check")
    assert res.status_code == 200
    data = res.json()
    assert data["author_name"] == "管理员"
    assert "税号" in data["description"]
    md = client.get("/api/skills/invoice-check/SKILL.md")
    assert md.status_code == 200
    assert md.text.startswith("---")


def test_register_rate_and_publish():
    reg = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "secret1", "display_name": "Alice"},
    )
    assert reg.status_code == 200
    token = reg.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    rate = client.post(
        "/api/skills/weekly-report/rate",
        headers=headers,
        json={"stars": 5, "comment": "结构清楚"},
    )
    assert rate.status_code == 200
    assert rate.json()["rating_avg"] == 5
    assert rate.json()["rating_count"] == 1

    markdown = """---
name: expense-note
description: 按公司报销口径整理费用说明。用户说写报销说明或费用备注时使用。
---

# 报销说明

只写事实：谁、何时、为何、金额、票据号。
"""
    pub = client.post(
        "/api/skills",
        headers=headers,
        data={"category": "docs", "tags": "报销", "version": "1.0.0", "markdown": markdown},
    )
    assert pub.status_code == 200, pub.text
    assert pub.json()["slug"] == "expense-note"

    detail = client.get("/api/skills/expense-note")
    assert detail.json()["author_name"] == "Alice"


def test_claude_marketplace_uses_archive_source():
    res = client.get("/api/claude/marketplace.json")
    assert res.status_code == 200
    payload = res.json()
    assert payload["name"] == "skillhub"
    plugin = next(p for p in payload["plugins"] if p["name"] == "invoice-check")
    assert plugin["source"]["source"] == "archive"
    assert plugin["source"]["url"].endswith("/api/skills/invoice-check/archive.zip")
    assert len(plugin["source"]["sha256"]) == 64


def test_package_and_archive_zip():
    pkg = client.get("/api/skills/invoice-check/package")
    assert pkg.status_code == 200
    with zipfile.ZipFile(io.BytesIO(pkg.content)) as zf:
        names = zf.namelist()
        assert any(n.endswith("SKILL.md") for n in names)

    archive = client.get("/api/skills/invoice-check/archive.zip")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
        names = zf.namelist()
        assert any(n.endswith(".claude-plugin/plugin.json") for n in names)
        assert any("/skills/invoice-check/SKILL.md" in n for n in names)


def test_snapshot_contains_ide_manifests():
    res = client.get("/api/marketplace/snapshot.zip")
    assert res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = set(zf.namelist())
        assert ".claude-plugin/marketplace.json" in names
        assert ".agents/plugins/marketplace.json" in names
        assert ".grok-plugin/marketplace.json" in names
        claude = json.loads(zf.read(".claude-plugin/marketplace.json"))
        assert claude["plugins"]
        assert claude["plugins"][0]["source"].startswith("./plugins/")


def test_agent_skills_index():
    res = client.get("/.well-known/agent-skills/index.json")
    assert res.status_code == 200
    names = {s["name"] for s in res.json()["skills"]}
    assert "invoice-check" in names


def test_login_seed_admin():
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200
    assert res.json()["user"]["is_admin"] is True
