# SkillHub

公司内部的 Agent Skills 中心：网页目录、作者与星级评价、版本包仓库，以及给 Claude Code / Codex / Grok / Cursor 用的技能源。

技能本身仍是标准的 `SKILL.md` 目录。SkillHub 负责集中发布、发现和更新，避免每个人把业务技能散落在自己的机器上。

## 能做什么

- **目录界面**：搜索、分类、作者、简介、平均星级、安装次数
- **评价**：登录后 1–5 星 + 评论
- **发布**：上传 zip 或粘贴 `SKILL.md`，后续可发新版本
- **当 IDE 的源**：CLI 把市场快照拉到 `~/.skillhub/marketplace`，各 IDE 添加这个本地目录；`skillhub update` 更新
- **Claude 生产环境**：HTTPS 下可直接 `/plugin marketplace add https://your-hub/api/claude/marketplace.json`（zip archive 源）

## 为什么不是只丢一个 Git 仓库

Claude、Codex、Grok 都能把 **git 仓库或本地目录** 加成 plugin marketplace，但协议细节不同：

| 工具 | 原生源 | 更新 |
| --- | --- | --- |
| Claude Code | git / 本地目录 / `marketplace.json` URL（URL 时插件必须是 archive/github，相对路径无效） | `claude plugin marketplace update` |
| Codex | **仅** git 或本地目录，不接受纯 JSON URL | `codex plugin marketplace upgrade` |
| Grok | git 或本地目录（`.grok-plugin/marketplace.json`） | `grok plugin marketplace update` |
| Cursor 等 | 读本机 `~/.cursor/skills`、`~/.agents/skills` | 拷贝文件 |

SkillHub 同时提供：

1. **CLI 同步**到各工具的 skills 目录（最稳，适合全员）
2. **市场快照**（一份目录里同时带 Claude / Codex / Grok 的 `marketplace.json`）
3. **Claude archive 市场**（服务器有公网 HTTPS 时可用）

## 快速开始

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
skillhub serve
```

打开 http://localhost:8000

首次启动会写入示例技能，并创建管理员：

- 用户名 `admin`
- 密码 `admin123`

请立刻改密或新建管理员账号。

Docker：

```bash
docker compose up --build
```

环境变量见 `.env.example`。生产环境务必设置 `SKILLHUB_SECRET` 和 `SKILLHUB_PUBLIC_URL`。

## 同事怎么接到 IDE

```bash
pip install -e .
skillhub login http://技能中心地址 --username 你的用户名
skillhub connect
```

然后把本地快照加成源：

```bash
claude plugin marketplace add ~/.skillhub/marketplace
codex plugin marketplace add ~/.skillhub/marketplace
grok plugin marketplace add ~/.skillhub/marketplace
```

只想把技能文件拷进本机目录（不走 plugin）：

```bash
skillhub sync          # 安装目录里全部技能
skillhub install invoice-check
skillhub update        # 更新已安装的技能，并刷新市场快照
```

同步目标默认包括：

- `~/.claude/skills`
- `~/.agents/skills`（Codex）
- `~/.grok/skills`
- `~/.cursor/skills`

## 发布技能

每个技能是一个目录：

```text
my-skill/
  SKILL.md
  scripts/        # 可选
  references/     # 可选
```

`SKILL.md` 必须带 frontmatter：

```markdown
---
name: my-skill
description: 做什么，以及用户怎样描述时应该用它。
---

步骤写在这里。
```

网页上粘贴上述文本，或把目录打成 zip 上传。

## API 要点

- `GET /api/skills` 目录
- `GET /api/skills/{slug}` 详情
- `POST /api/skills` 发布
- `POST /api/skills/{slug}/rate` 评分
- `GET /api/claude/marketplace.json` Claude archive 市场
- `GET /api/marketplace/snapshot.zip` 全量市场快照
- `GET /.well-known/agent-skills/index.json` Agent Skills 发现索引

内网若关闭匿名读，设 `SKILLHUB_PUBLIC_READ=false`，并在 URL 上带 `?token=sh_...`（登录后在 CLI 会打印 API token）。

## 架构

```text
浏览器目录/评分 ──┐
CLI 安装/更新 ──┼── FastAPI + SQLite + 技能包文件
IDE marketplace ─┘         │
                           ├── data/packages/<slug>/<ver>/
                           └── data/marketplace/   生成的 Claude/Codex/Grok 清单
```
