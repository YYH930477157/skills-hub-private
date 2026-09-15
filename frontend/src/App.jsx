import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, getToken, setToken } from "./api.js";

const CATEGORY_FALLBACK = [
  { id: "docs", label: "文档" },
  { id: "smartset", label: "SmartSet" },
  { id: "code", label: "代码" },
  { id: "test", label: "测试" },
  { id: "protocol", label: "协议" },
  { id: "debug", label: "调试" },
  { id: "toolchain", label: "工具链" },
  { id: "hardware", label: "硬件" },
];

export default function App() {
  const [user, setUser] = useState(null);
  const [meta, setMeta] = useState({ org_name: "SkillHub", categories: [] });

  async function refreshUser() {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api("/api/auth/me"));
    } catch {
      setToken("");
      setUser(null);
    }
  }

  useEffect(() => {
    api("/api/meta").then(setMeta).catch(() => {});
    refreshUser();
  }, []);

  return (
    <>
      <Header user={user} meta={meta} onLogout={() => { setToken(""); setUser(null); }} />
      <div className="shell">
        <Routes>
          <Route path="/" element={<Catalog meta={meta} />} />
          <Route path="/skills/:slug" element={<Detail user={user} meta={meta} />} />
          <Route path="/publish" element={<Publish user={user} meta={meta} />} />
          <Route path="/connect" element={<Connect />} />
          <Route path="/login" element={<Auth mode="login" onDone={refreshUser} />} />
          <Route path="/register" element={<Auth mode="register" onDone={refreshUser} />} />
        </Routes>
      </div>
    </>
  );
}

function Header({ user, meta, onLogout }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  return (
    <header className="topbar">
      <Link className="brand" to="/">
        <b>SkillHub</b>
        <span>{meta.org_name}</span>
      </Link>
      <form
        style={{ flex: 1 }}
        onSubmit={(e) => {
          e.preventDefault();
          navigate(`/?q=${encodeURIComponent(q)}`);
        }}
      >
        <input
          className="top-search"
          placeholder="搜索技能、作者、用途…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </form>
      <nav className="nav">
        <NavLink to="/" end>目录</NavLink>
        <NavLink to="/connect">接入 IDE</NavLink>
        <NavLink to="/publish">发布</NavLink>
        {user ? (
          <button className="link" onClick={onLogout}>{user.display_name} · 退出</button>
        ) : (
          <NavLink to="/login">登录</NavLink>
        )}
      </nav>
    </header>
  );
}

function StarPicker({ value, onPick }) {
  return (
    <span className="stars">
      {[1, 2, 3, 4, 5].map((n) => (
        <button type="button" key={n} onClick={() => onPick(n)} aria-label={`${n} 星`}>
          {n <= value ? "★" : "☆"}
        </button>
      ))}
    </span>
  );
}

function Catalog({ meta }) {
  const loc = useLocation();
  const q = new URLSearchParams(loc.search).get("q") || "";
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("updated");
  const [skills, setSkills] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (sort) params.set("sort", sort);
    api(`/api/skills?${params}`)
      .then(setSkills)
      .catch((e) => setError(e.message));
  }, [q, category, sort]);

  const cats = [{ id: "", label: "全部" }, ...(meta.categories?.length ? meta.categories : CATEGORY_FALLBACK)];
  const rated = skills.filter((s) => s.rating_count > 0);
  const avg = rated.length ? (rated.reduce((a, s) => a + s.rating_avg, 0) / rated.length).toFixed(1) : "—";

  return (
    <>
      <section className="hero">
        <div>
          <h1>嵌入式研发与测试的技能目录，给 Codex / Claude / Grok 当源用。</h1>
          <p>按文档、SmartSet、代码、测试等分类浏览。发布新版本后，同事用 update 就能拿到最新 SKILL.md。</p>
        </div>
        <div className="stats">
          <div className="stat"><b>{skills.length}</b><span>个技能</span></div>
          <div className="stat"><b>{avg}</b><span>平均评分</span></div>
          <div className="stat"><b>{skills.reduce((a, s) => a + s.install_count, 0)}</b><span>次安装</span></div>
        </div>
      </section>
      <div className="toolbar">
        {cats.map((c) => (
          <button key={c.id || "all"} className={`chip ${category === c.id ? "active" : ""}`} onClick={() => setCategory(c.id)}>
            {c.label}
          </button>
        ))}
        <select className="chip" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="updated">最近更新</option>
          <option value="rating">评分最高</option>
          <option value="installs">安装最多</option>
          <option value="name">名称</option>
        </select>
      </div>
      {error && <div className="error">{error}</div>}
      {skills.length === 0 && !error && <div className="empty">还没有技能。登录后去发布第一个。</div>}
      <div className="grid">
        {skills.map((s) => (
          <Link className="card" key={s.slug} to={`/skills/${s.slug}`}>
            <div className="kicker">
              <span>{labelOf(meta, s.category)}</span>
              <span>v{s.latest_version}</span>
            </div>
            <h3>{s.slug}</h3>
            <p>{s.description}</p>
            <div className="meta">
              <span>{s.author_name}</span>
              <span className="stars">{"★".repeat(Math.round(s.rating_avg)) || "☆"} {s.rating_avg.toFixed(1)} · {s.rating_count}</span>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}

function labelOf(meta, id) {
  return (meta.categories || []).find((c) => c.id === id)?.label || id;
}

function bumpVersion(version) {
  const parts = String(version || "1.0.0").split(".").map((n) => parseInt(n, 10) || 0);
  while (parts.length < 3) parts.push(0);
  parts[2] += 1;
  return parts.join(".");
}

function Detail({ user, meta }) {
  const { slug } = useParams();
  const [skill, setSkill] = useState(null);
  const [error, setError] = useState("");
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState("");
  const [notice, setNotice] = useState("");
  const [nextVersion, setNextVersion] = useState("1.0.1");
  const [changelog, setChangelog] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [file, setFile] = useState(null);

  async function load() {
    const data = await api(`/api/skills/${slug}`);
    setSkill(data);
    setStars(data.my_rating?.stars || 0);
    setComment(data.my_rating?.comment || "");
    setNextVersion(bumpVersion(data.latest_version));
    setMarkdown(data.skill_md || "");
  }

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [slug]);

  if (error) return <div className="error">{error}</div>;
  if (!skill) return <div className="empty">加载中…</div>;

  async function rate(e) {
    e.preventDefault();
    await api(`/api/skills/${slug}/rate`, { method: "POST", body: { stars, comment } });
    setNotice("已记录你的评分");
    await load();
  }

  return (
    <div style={{ paddingTop: 28 }}>
      <div className="panel">
        <div className="detail-head">
          <div>
            <div className="kicker"><span>{labelOf(meta, skill.category)}</span><span>v{skill.latest_version}</span></div>
            <h1>{skill.slug}</h1>
            <p className="muted">{skill.description}</p>
            <div className="tags">
              {skill.tags.map((t) => <span className="tag" key={t}>{t}</span>)}
            </div>
            <div className="meta" style={{ marginTop: 0 }}>
              <span>作者 {skill.author_name}</span>
              <span className="stars">★ {skill.rating_avg.toFixed(1)} · {skill.rating_count} 人评价 · {skill.install_count} 次安装</span>
            </div>
          </div>
          <div>
            <a className="btn" href={`/api/skills/${slug}/package`}>下载 zip</a>
          </div>
        </div>
      </div>
      <div className="columns">
        <div className="panel">
          <h3>SKILL.md</h3>
          <pre>{skill.skill_md}</pre>
        </div>
        <div>
          <div className="panel">
            <h3>接入</h3>
            <p className="muted">CLI 安装到本机各 IDE 的 skills 目录：</p>
            <Copy text={`skillhub install ${skill.slug}`} />
            <p className="muted">或把整个市场加为源，见「接入 IDE」页。</p>
          </div>
          <div className="panel" style={{ marginTop: 16 }}>
            <h3>评价星级</h3>
            {user ? (
              <form onSubmit={rate}>
                <StarPicker value={stars} onPick={setStars} />
                <label>评论（可选）</label>
                <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="好用在哪，坑在哪" />
                <div style={{ marginTop: 12 }}><button className="btn copper" disabled={!stars}>提交评分</button></div>
                {notice && <p className="ok">{notice}</p>}
              </form>
            ) : (
              <p className="muted">登录后才能评分。</p>
            )}
            <ul className="list">
              {skill.ratings.map((r, i) => (
                <li key={i}>
                  <b>{r.display_name}</b> <span className="stars">{"★".repeat(r.stars)}</span>
                  <div className="muted">{r.comment || "未写评论"}</div>
                </li>
              ))}
            </ul>
          </div>
          <div className="panel" style={{ marginTop: 16 }}>
            <h3>版本</h3>
            <ul className="list">
              {skill.versions.map((v) => (
                <li key={v.version}>
                  <b>{v.version}</b> <span className="muted">{v.changelog || "无说明"}</span>
                </li>
              ))}
            </ul>
            {user && (user.is_admin || user.id === skill.author_id) && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const data = new FormData();
                  data.append("version", nextVersion);
                  data.append("changelog", changelog);
                  if (file) data.append("file", file);
                  else data.append("markdown", markdown);
                  try {
                    await api(`/api/skills/${slug}/versions`, { method: "POST", form: data });
                    setNotice("新版本已发布");
                    await load();
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                <label>发布新版本</label>
                <input value={nextVersion} onChange={(e) => setNextVersion(e.target.value)} />
                <label>说明</label>
                <input value={changelog} onChange={(e) => setChangelog(e.target.value)} />
                <label>zip（可选）</label>
                <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files[0] || null)} />
                <label>或编辑 SKILL.md</label>
                <textarea value={markdown} onChange={(e) => setMarkdown(e.target.value)} />
                <div style={{ marginTop: 12 }}><button className="btn secondary">发布新版本</button></div>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Publish({ user, meta }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ category: "docs", tags: "", version: "1.0.0", changelog: "初始版本", markdown: "" });
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  if (!user) {
    return <div className="empty">请先 <Link to="/login">登录</Link> 再发布技能。</div>;
  }
  async function submit(e) {
    e.preventDefault();
    setError("");
    const data = new FormData();
    Object.entries(form).forEach(([k, v]) => data.append(k, v));
    if (file) data.append("file", file);
    try {
      const res = await api("/api/skills", { method: "POST", form: data });
      navigate(`/skills/${res.slug}`);
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div className="panel" style={{ marginTop: 28 }}>
      <h1 style={{ fontFamily: "Fraunces, serif" }}>发布技能</h1>
      <p className="muted">上传包含 SKILL.md 的 zip，或直接粘贴 SKILL.md。标识和描述从 frontmatter 读取。</p>
      <form onSubmit={submit}>
        <div className="row">
          <div>
            <label>分类</label>
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {(meta.categories?.length ? meta.categories : CATEGORY_FALLBACK).map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label>版本</label>
            <input value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} />
          </div>
        </div>
        <label>标签（逗号分隔）</label>
        <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} placeholder="DLMS,规约,用例" />
        <label>更新说明</label>
        <input value={form.changelog} onChange={(e) => setForm({ ...form, changelog: e.target.value })} />
        <label>zip 包（可选）</label>
        <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files[0] || null)} />
        <label>或粘贴 SKILL.md</label>
        <textarea
          value={form.markdown}
          onChange={(e) => setForm({ ...form, markdown: e.target.value })}
          placeholder={"---\nname: my-skill\ndescription: 做什么、何时触发\n---\n\n# 步骤\n"}
        />
        {error && <div className="error">{error}</div>}
        <div style={{ marginTop: 16 }}><button className="btn">发布</button></div>
      </form>
    </div>
  );
}

function Connect() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/connect").then(setInfo).catch((e) => setError(e.message));
  }, []);
  if (error) return <div className="error">{error}</div>;
  if (!info) return <div className="empty">加载中…</div>;
  return (
    <div style={{ paddingTop: 28 }}>
      <h1 style={{ fontFamily: "Fraunces, serif" }}>把 SkillHub 当成 IDE 的技能源</h1>
      <p className="muted">各工具读的都是 SKILL.md，但接入协议不一样。推荐先用 CLI 拉本地快照，再让 Claude / Codex / Grok 添加这个目录。</p>
      <div className="columns">
        <div className="panel">
          <h3>1. CLI（推荐）</h3>
          {info.cli.map((line) => <Copy key={line} text={line} />)}
        </div>
        <div className="panel">
          <h3>2. 加到 IDE</h3>
          <p className="muted">Claude</p>
          <Copy text={info.claude.local_snapshot} />
          <p className="muted">{info.claude.note}</p>
          <p className="muted">Codex</p>
          <Copy text={info.codex.local_snapshot} />
          <p className="muted">{info.codex.note}</p>
          <p className="muted">Grok</p>
          <Copy text={info.grok.local_snapshot} />
          <p className="muted">{info.grok.skill_dirs}</p>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 18 }}>
        <h3>更新</h3>
        <Copy text="skillhub update" />
        <p className="muted">这会刷新本机技能文件和市场快照。Codex 再执行 marketplace upgrade，Grok 再执行 marketplace update。</p>
      </div>
    </div>
  );
}

function Copy({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <div className="copy">
      <pre>{text}</pre>
      <button
        className="btn secondary"
        onClick={async () => {
          await navigator.clipboard.writeText(text);
          setOk(true);
          setTimeout(() => setOk(false), 1200);
        }}
      >
        {ok ? "已复制" : "复制"}
      </button>
    </div>
  );
}

function Auth({ mode, onDone }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({ username: "", password: "", display_name: "" });
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const path = mode === "register" ? "/api/auth/register" : "/api/auth/login";
      const data = await api(path, { method: "POST", body: form });
      setToken(data.token);
      await onDone();
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div className="panel auth-box">
      <h1>{mode === "register" ? "注册" : "登录"}</h1>
      <p className="muted">{mode === "register" ? "创建账号后即可发布和评价技能。" : "使用公司账号登录技能中心。"}</p>
      <form onSubmit={submit}>
        <div className="field-group">
          <label htmlFor="auth-username">用户名</label>
          <input
            id="auth-username"
            className="field"
            type="text"
            autoComplete="username"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </div>
        {mode === "register" && (
          <div className="field-group">
            <label htmlFor="auth-display-name">显示名</label>
            <input
              id="auth-display-name"
              className="field"
              type="text"
              autoComplete="nickname"
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            />
          </div>
        )}
        <div className="field-group">
          <label htmlFor="auth-password">密码</label>
          <input
            id="auth-password"
            className="field"
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" type="submit">{mode === "register" ? "注册" : "登录"}</button>
      </form>
      <p className="muted" style={{ marginTop: 16 }}>
        {mode === "register" ? <Link to="/login">已有账号？登录</Link> : <Link to="/register">没有账号？注册</Link>}
      </p>
    </div>
  );
}
