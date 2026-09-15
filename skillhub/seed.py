from __future__ import annotations

from sqlalchemy.orm import Session

from skillhub.auth import hash_password, new_api_token
from skillhub.marketplace import rebuild_marketplace
from skillhub.models import Skill, SkillVersion, User, utcnow
from skillhub.packages import extract_skill_from_markdown, save_version, skill_root_name, validate_slug

SAMPLES = [
    {
        "category": "docs",
        "tags": "财务,发票,对账",
        "markdown": """---
name: invoice-check
description: 按公司财务规范核对应收应付发票、金额、税号与合同编号。用户提到发票核对、报销单、进项税或对账时使用。
---

# 发票核对

只处理财务核对，不改账套、不提交申报。

## 必查项

1. 购销双方名称、税号是否与主数据一致
2. 金额、税额、价税合计是否勾稽
3. 发票号码、开票日期、合同编号是否可追溯
4. 费用科目是否与业务类型匹配

## 输出

用表格列出：字段、发票值、系统值、是否一致、处理建议。
最后给出：通过 / 待补件 / 拒绝，以及一句原因。
""",
    },
    {
        "category": "docs",
        "tags": "法务,合同,条款",
        "markdown": """---
name: contract-clause
description: 按公司法务模板审查合同条款，标出偏差、风险和改写建议。用户提到合同审查、条款对比、NDA 或采购合同时使用。
---

# 合同条款审查

对照公司标准模板，而不是凭空给法律意见。

## 步骤

1. 先列出合同类型、相对方、标的和管辖
2. 逐条对照：责任上限、付款、验收、知识产权、保密、解约、违约金
3. 标出缺失条款和比模板更严/更松的表述
4. 给出可粘贴的改写句，不要只写“建议加强”

## 输出

| 条款 | 现状 | 风险 | 建议改写 |
|------|------|------|----------|
""",
    },
    {
        "category": "docs",
        "tags": "运营,周报,汇报",
        "markdown": """---
name: weekly-report
description: 按公司周报结构整理本周进展、阻塞和下周计划。用户说写周报、汇报进展或整理工时说明时使用。
---

# 周报

用事实和数字，不写空话。

## 结构

1. 本周目标与完成度
2. 关键进展（每条：做了什么、结果、影响）
3. 风险与阻塞（谁能解、需要什么）
4. 下周三件最重要的事
5. 需要主管拍板的问题（可空）

不要写成流水账。能量化的必须量化。
""",
    },
]


def seed_if_empty(db: Session) -> None:
    if db.query(User).count() > 0:
        return

    admin = User(
        username="admin",
        display_name="管理员",
        password_hash=hash_password("admin123"),
        is_admin=True,
        api_token=new_api_token(),
    )
    db.add(admin)
    db.flush()

    for sample in SAMPLES:
        files = extract_skill_from_markdown(sample["markdown"])
        slug = validate_slug(skill_root_name(files))
        saved = save_version(slug, "1.0.0", files, _description(sample["markdown"]), admin.display_name)
        skill = Skill(
            slug=slug,
            name=slug,
            description=_description(sample["markdown"]),
            category=sample["category"],
            tags=sample["tags"],
            author_id=admin.id,
            author_name=admin.display_name,
            latest_version="1.0.0",
            updated_at=utcnow(),
        )
        db.add(skill)
        db.flush()
        db.add(
            SkillVersion(
                skill_id=skill.id,
                version="1.0.0",
                changelog="初始版本",
                sha256=saved["sha256"],
                archive_sha256=saved["archive_sha256"],
                size_bytes=saved["size_bytes"],
                skill_md=saved["skill_md"],
            )
        )
    db.commit()
    rebuild_marketplace(db)


def _description(markdown: str) -> str:
    from skillhub.packages import parse_frontmatter

    meta, _ = parse_frontmatter(markdown)
    return str(meta.get("description") or "").strip()
