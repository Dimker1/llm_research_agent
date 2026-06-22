import logging
from datetime import datetime
from pathlib import Path

from src.models import AnalyzedItem

logger = logging.getLogger(__name__)

DIRECTION_META = {
    "pretraining": ("🏗️", "预训练方向", "#6366f1"),
    "post_training": ("🎯", "后训练方向", "#10b981"),
    "agent": ("🤖", "LLM Agent 方向", "#f59e0b"),
}

CSS = """
:root {
  --bg: #0f172a;
  --surface: #1e293b;
  --surface2: #273349;
  --border: #334155;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --text-bright: #f8fafc;
  --primary: #6366f1;
  --primary-light: #818cf8;
  --green: #10b981;
  --amber: #f59e0b;
  --code-bg: #0d1117;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Noto Sans SC', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  font-size: 15px;
}
a { color: var(--primary-light); text-decoration: none; }
a:hover { text-decoration: underline; }

/* HERO */
.hero {
  background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 45%, #042f2e 100%);
  padding: 56px 24px 44px;
  text-align: center;
  border-bottom: 1px solid var(--border);
  position: relative;
  overflow: hidden;
}
.hero::before {
  content: '';
  position: absolute; inset: 0;
  background: radial-gradient(ellipse 80% 50% at 50% 0%, rgba(99,102,241,.18), transparent);
}
.hero-badge {
  display: inline-block;
  background: rgba(99,102,241,.2);
  border: 1px solid var(--primary);
  color: var(--primary-light);
  font-size: 12px; font-weight: 700;
  letter-spacing: .1em; text-transform: uppercase;
  padding: 4px 14px; border-radius: 999px;
  margin-bottom: 18px;
  position: relative;
}
.hero h1 {
  font-size: clamp(22px, 4vw, 38px);
  font-weight: 800; color: var(--text-bright);
  line-height: 1.2; margin-bottom: 10px;
  position: relative;
}
.hero h1 span { color: var(--primary-light); }
.hero-sub { color: var(--text-muted); font-size: 14px; margin-bottom: 28px; position: relative; }
.hero-meta {
  display: flex; justify-content: center; flex-wrap: wrap; gap: 20px;
  font-size: 13px; color: var(--text-muted); position: relative;
}
.hero-meta span { display: flex; align-items: center; gap: 6px; }

/* LAYOUT */
.container { max-width: 1080px; margin: 0 auto; padding: 0 20px; }
.content { padding: 44px 0 72px; }

/* STATS */
.stats-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px; margin-bottom: 40px;
}
.stat-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px; text-align: center;
}
.stat-value { font-size: 30px; font-weight: 800; color: var(--primary-light); line-height: 1; margin-bottom: 6px; }
.stat-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .07em; }

/* SECTION */
.section { margin-bottom: 48px; }
.section-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 20px; padding-bottom: 12px;
  border-bottom: 2px solid;
}
.section-header.pretraining { border-color: #6366f1; }
.section-header.post_training { border-color: #10b981; }
.section-header.agent { border-color: #f59e0b; }
.section-icon { font-size: 22px; }
.section-title { font-size: 18px; font-weight: 700; color: var(--text-bright); }
.section-count {
  margin-left: auto; font-size: 12px; font-weight: 600;
  padding: 2px 10px; border-radius: 999px;
  background: rgba(99,102,241,.15); color: var(--primary-light);
}
.section-header.post_training .section-count { background: rgba(16,185,129,.15); color: #6ee7b7; }
.section-header.agent .section-count { background: rgba(245,158,11,.15); color: #fcd34d; }

/* ITEM CARD */
.item-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px; margin-bottom: 14px;
  transition: border-color .2s;
}
.item-card:hover { border-color: var(--primary); }
.item-title {
  font-size: 15px; font-weight: 700; color: var(--text-bright);
  margin-bottom: 10px; line-height: 1.4;
}
.item-title a { color: var(--text-bright); }
.item-title a:hover { color: var(--primary-light); text-decoration: none; }
.item-meta {
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  margin-bottom: 12px; font-size: 12px; color: var(--text-muted);
}
.meta-badge {
  display: inline-flex; align-items: center; gap: 4px;
  background: rgba(148,163,184,.1); border-radius: 6px;
  padding: 3px 8px; white-space: nowrap;
}
.meta-badge strong { color: var(--text-bright); }
.score-badge {
  background: rgba(99,102,241,.2); color: #a5b4fc;
  border-radius: 6px; padding: 3px 8px; font-weight: 700;
}
.score-9, .score-10 { background: rgba(16,185,129,.2); color: #6ee7b7; }
.score-7, .score-8 { background: rgba(99,102,241,.2); color: #a5b4fc; }
.score-5, .score-6 { background: rgba(245,158,11,.15); color: #fcd34d; }
.keywords { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; }
.kw {
  font-size: 11px; font-family: 'SF Mono', Consolas, monospace;
  background: rgba(99,102,241,.15); color: #c4b5fd;
  border-radius: 4px; padding: 2px 7px;
}
.summary {
  font-size: 13px; color: var(--text-muted); line-height: 1.7;
  border-left: 3px solid var(--border);
  padding-left: 12px; margin-top: 8px;
}
.empty-section {
  color: var(--text-muted); font-size: 14px; font-style: italic;
  padding: 16px 0;
}

/* FOOTER */
footer {
  border-top: 1px solid var(--border); padding: 22px;
  text-align: center; font-size: 12px; color: var(--text-muted);
}

/* ── Agent synthesis 区域 ── */
.synth-block { margin-bottom: 36px; }
.synth-label {
  display: inline-block;
  font-size: 11px; font-weight: 700;
  letter-spacing: .12em; text-transform: uppercase;
  color: var(--primary-light);
  background: rgba(99,102,241,.12);
  border: 1px solid rgba(99,102,241,.35);
  border-radius: 999px;
  padding: 3px 12px;
  margin-bottom: 14px;
}
.tldr-card {
  background: linear-gradient(135deg, rgba(99,102,241,.08), rgba(16,185,129,.06));
  border: 1px solid var(--primary);
  border-radius: 14px;
  padding: 22px 24px;
  font-size: 15px; line-height: 1.85;
  color: var(--text-bright);
}
.toppick-list { display: grid; gap: 12px; }
.toppick-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid #f59e0b;
  border-radius: 10px;
  padding: 16px 18px;
}
.toppick-rank {
  display: inline-block;
  background: #f59e0b; color: #1a1a1a;
  font-weight: 800; font-size: 11px;
  padding: 2px 8px; border-radius: 4px;
  margin-right: 8px;
}
.toppick-title {
  font-weight: 700; color: var(--text-bright); font-size: 15px;
  margin-bottom: 6px;
}
.toppick-title a { color: var(--text-bright); }
.toppick-why { color: var(--text-muted); font-size: 13px; line-height: 1.7; }

.theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}
.theme-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 18px;
}
.theme-name {
  font-size: 14px; font-weight: 700; color: var(--text-bright);
  margin-bottom: 6px;
}
.theme-summary { color: var(--text-muted); font-size: 13px; margin-bottom: 8px; line-height: 1.65; }
.theme-count { font-size: 11px; color: var(--primary-light); }

.diff-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}
@media (max-width: 720px) { .diff-grid { grid-template-columns: 1fr; } }
.diff-col {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px;
}
.diff-col h4 {
  font-size: 13px; font-weight: 700;
  margin-bottom: 10px; color: var(--text-bright);
  letter-spacing: .04em;
}
.diff-col.continued h4::before { content: '↻ '; color: var(--primary-light); }
.diff-col.new h4::before { content: '✦ '; color: #6ee7b7; }
.diff-col ul { list-style: none; }
.diff-col li {
  font-size: 13px; line-height: 1.7;
  padding: 6px 0; border-bottom: 1px dashed rgba(148,163,184,.15);
  color: var(--text-muted);
}
.diff-col li:last-child { border-bottom: none; }
.diff-col li strong { color: var(--text-bright); }

.learned-kw-list { display: flex; flex-wrap: wrap; gap: 6px; }
.learned-kw {
  font-size: 12px;
  background: rgba(16,185,129,.15);
  color: #6ee7b7;
  border: 1px solid rgba(16,185,129,.3);
  padding: 3px 9px;
  border-radius: 999px;
  font-family: 'SF Mono', Consolas, monospace;
}
"""


def write_weekly_html(
    items: list[AnalyzedItem],
    week_label: str,
    date_range: tuple[str, str],
    output_dir: str = "weekly",
    source_stats: dict = None,
    elapsed_seconds: float = 0.0,
    synthesis: dict | None = None,
) -> str:
    """生成周报 HTML 文件，返回文件路径。

    synthesis 可选，结构：
      {
        "tldr": str,
        "top_picks": [{"id","title","url","why"}],
        "themes": [{"name","summary","item_ids":[...]}],
        "weekly_diff": {"continued":[{"theme","note"}], "new":[{"theme","note"}]},
        "learned_kws": [str, ...],
      }
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filepath = str(Path(output_dir) / f"{week_label}.html")

    groups: dict[str, list[AnalyzedItem]] = {k: [] for k in DIRECTION_META}
    for item in items:
        if item.direction in groups:
            groups[item.direction].append(item)

    total_count = sum(len(v) for v in groups.values())
    start_date, end_date = date_range
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M CST")
    elapsed_str = f"{int(elapsed_seconds)}s" if elapsed_seconds else "—"

    source_html = ""
    if source_stats:
        parts = " &nbsp;|&nbsp; ".join(
            f"<strong>{k}</strong>({v})" for k, v in source_stats.items()
        )
        source_html = f'<p class="hero-sub">来源：{parts}</p>'

    # ── Agent synthesis 块（可选） ──
    synth_html = _render_synthesis_block(synthesis or {}, items)

    # ── 统计卡片 ──
    stats_cards = _stats_cards(groups, total_count)

    # ── 三大方向内容 ──
    sections_html = ""
    for direction, (icon, label, _color) in DIRECTION_META.items():
        sections_html += _render_section(direction, icon, label, groups[direction])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>LLM 周报 | {week_label}</title>
  <style>{CSS}</style>
</head>
<body>

<div class="hero">
  <div class="hero-badge">LLM 前沿技术周报</div>
  <h1>📚 <span>{week_label}</span> 周报</h1>
  <p class="hero-sub">覆盖时间：{start_date} → {end_date}</p>
  {source_html}
  <div class="hero-meta">
    <span>📄 精选 {total_count} 条内容</span>
    <span>🏗️ 预训练 {len(groups["pretraining"])} 条</span>
    <span>🎯 后训练 {len(groups["post_training"])} 条</span>
    <span>🤖 Agent {len(groups["agent"])} 条</span>
  </div>
</div>

<div class="container content">
  {synth_html}
  {stats_cards}
  {sections_html}
</div>

<footer>
  <div>LLM 前沿技术周报 · {week_label} · 生成时间：{now_str} · 处理耗时：{elapsed_str}</div>
  <div style="margin-top:5px;color:#475569;">由 Claude AI 辅助生成，内容来源：arXiv · 量子位 · 机器之心</div>
</footer>

</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"[html_writer] wrote {total_count} items → {filepath}")

    _update_index(output_dir, week_label, date_range, total_count)

    return filepath


def _update_index(output_dir: str, latest_label: str, date_range: tuple, latest_count: int) -> None:
    """扫描 weekly/ 目录下所有 HTML，生成归档首页 index.html"""
    from pathlib import Path as P
    import re

    weekly_dir = P(output_dir)
    pattern = re.compile(r"^(\d{4}-W\d{2})\.html$")
    all_weeks = sorted(
      [m.group(1) for f in weekly_dir.iterdir() if (m := pattern.match(f.name))],
        reverse=True,
    )

    rows_html = ""
    for i, label in enumerate(all_weeks):
        is_latest = label == all_weeks[0]
        badge = ' <span style="background:#6366f1;color:#fff;font-size:11px;padding:2px 8px;border-radius:999px;margin-left:8px;">最新</span>' if is_latest else ""
        rows_html += f"""
    <a class="week-row" href="weekly/{label}.html">
      <span class="week-label">{label}{badge}</span>
      <span class="week-arrow">→</span>
    </a>"""

    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>LLM 前沿技术周报 · 归档</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif;
           background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
    .hero {{ background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 45%, #042f2e 100%);
             padding: 56px 24px 44px; text-align: center; border-bottom: 1px solid #334155; }}
    .hero h1 {{ font-size: clamp(22px, 4vw, 36px); font-weight: 800; color: #f8fafc; margin-bottom: 10px; }}
    .hero h1 span {{ color: #818cf8; }}
    .hero p {{ color: #94a3b8; font-size: 14px; }}
    .container {{ max-width: 680px; margin: 48px auto; padding: 0 20px 72px; }}
    .section-title {{ font-size: 13px; font-weight: 600; color: #64748b;
                      text-transform: uppercase; letter-spacing: .08em; margin-bottom: 16px; }}
    .week-row {{ display: flex; align-items: center; justify-content: space-between;
                 background: #1e293b; border: 1px solid #334155; border-radius: 12px;
                 padding: 18px 22px; margin-bottom: 10px; text-decoration: none;
                 color: #e2e8f0; transition: border-color .2s, background .2s; }}
    .week-row:hover {{ border-color: #6366f1; background: #1e1b4b; }}
    .week-label {{ font-size: 16px; font-weight: 600; }}
    .week-arrow {{ color: #475569; font-size: 18px; }}
    footer {{ text-align: center; color: #475569; font-size: 12px; padding: 24px; }}
  </style>
</head>
<body>
<div class="hero">
  <h1>📚 LLM 前沿技术<span>周报</span>归档</h1>
  <p>聚焦预训练 · 后训练 · LLM Agent，每周自动更新</p>
</div>
<div class="container">
  <div class="section-title">所有周报（共 {len(all_weeks)} 期）</div>
  {rows_html}
</div>
<footer>由 Claude AI 辅助生成 · 数据来源：arXiv · 量子位 · HuggingFace 等</footer>
</body>
</html>"""

    index_path = str(P(output_dir).parent / "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)


def _stats_cards(groups: dict, total: int) -> str:
    pre = len(groups["pretraining"])
    post = len(groups["post_training"])
    agent = len(groups["agent"])
    return f"""
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-value">{total}</div>
    <div class="stat-label">精选总条目</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" style="color:#818cf8">{pre}</div>
    <div class="stat-label">🏗️ 预训练</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" style="color:#6ee7b7">{post}</div>
    <div class="stat-label">🎯 后训练</div>
  </div>
  <div class="stat-card">
    <div class="stat-value" style="color:#fcd34d">{agent}</div>
    <div class="stat-label">🤖 LLM Agent</div>
  </div>
</div>"""


def _render_section(direction: str, icon: str, label: str, items: list[AnalyzedItem]) -> str:
    count = len(items)
    cards_html = ""
    if not items:
        cards_html = '<p class="empty-section">本周暂无相关内容</p>'
    else:
        for item in items:
            cards_html += _render_item_card(item)

    return f"""
<div class="section">
  <div class="section-header {direction}">
    <span class="section-icon">{icon}</span>
    <span class="section-title">{label}</span>
    <span class="section-count">{count} 条</span>
  </div>
  {cards_html}
</div>"""


def _render_item_card(item: AnalyzedItem) -> str:
    score = item.relevance_score
    score_class = f"score-{min(score, 10)}"

    # 来源 + 日期 + 作者
    meta_parts = [
        f'<span class="meta-badge"><strong>来源</strong>&nbsp;{_esc(item.source)}</span>',
        f'<span class="meta-badge"><strong>日期</strong>&nbsp;{item.published[:10]}</span>',
        f'<span class="score-badge {score_class}">{score}/10</span>',
    ]
    if item.authors:
        authors = ", ".join(item.authors[:3])
        if len(item.authors) > 3:
            authors += " 等"
        meta_parts.append(
            f'<span class="meta-badge"><strong>作者</strong>&nbsp;{_esc(authors)}</span>'
        )
    meta_html = "\n    ".join(meta_parts)

    # 关键词
    kw_html = ""
    if item.keywords:
        kws = "".join(f'<span class="kw">{_esc(k)}</span>' for k in item.keywords)
        kw_html = f'<div class="keywords">{kws}</div>'

    # 摘要
    summary_html = ""
    if item.summary_zh:
        summary_html = f'<div class="summary">{_esc(item.summary_zh)}</div>'

    return f"""
<div class="item-card">
  <div class="item-title"><a href="{_esc(item.url)}" target="_blank" rel="noopener">{_esc(item.title)}</a></div>
  <div class="item-meta">
    {meta_html}
  </div>
  {kw_html}
  {summary_html}
</div>"""


def _esc(s: str) -> str:
    return (s
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _render_synthesis_block(synthesis: dict, items: list[AnalyzedItem]) -> str:
    if not synthesis:
        return ""

    parts = []

    tldr = synthesis.get("tldr", "")
    if tldr:
        parts.append(f"""
<div class="synth-block">
  <div class="synth-label">⚡ 本周 TL;DR</div>
  <div class="tldr-card">{_esc(tldr)}</div>
</div>""")

    top_picks = synthesis.get("top_picks", [])
    if top_picks:
        picks_html = ""
        for i, pick in enumerate(top_picks, 1):
            title = _esc(pick.get("title", ""))
            url = _esc(pick.get("url", "#"))
            why = _esc(pick.get("why", ""))
            picks_html += f"""
  <div class="toppick-card">
    <div class="toppick-title"><span class="toppick-rank">#{i}</span><a href="{url}" target="_blank" rel="noopener">{title}</a></div>
    <div class="toppick-why">{why}</div>
  </div>"""
        parts.append(f"""
<div class="synth-block">
  <div class="synth-label">🏆 编辑精选</div>
  <div class="toppick-list">{picks_html}</div>
</div>""")

    themes = synthesis.get("themes", [])
    if themes:
        themes_html = ""
        for theme in themes:
            name = _esc(theme.get("name", ""))
            summary = _esc(theme.get("summary", ""))
            count = len(theme.get("item_ids", []))
            themes_html += f"""
  <div class="theme-card">
    <div class="theme-name">{name}</div>
    <div class="theme-summary">{summary}</div>
    <div class="theme-count">{count} 篇相关</div>
  </div>"""
        parts.append(f"""
<div class="synth-block">
  <div class="synth-label">🔍 本周热门主题</div>
  <div class="theme-grid">{themes_html}</div>
</div>""")

    weekly_diff = synthesis.get("weekly_diff", {})
    continued = weekly_diff.get("continued", [])
    new_topics = weekly_diff.get("new", [])
    if continued or new_topics:
        cont_items = "".join(
            f'<li><strong>{_esc(t.get("theme",""))}</strong>　{_esc(t.get("note",""))}</li>'
            for t in continued
        )
        new_items = "".join(
            f'<li><strong>{_esc(t.get("theme",""))}</strong>　{_esc(t.get("note",""))}</li>'
            for t in new_topics
        )
        parts.append(f"""
<div class="synth-block">
  <div class="synth-label">📅 周间动态</div>
  <div class="diff-grid">
    <div class="diff-col continued"><h4>持续热点</h4><ul>{cont_items}</ul></div>
    <div class="diff-col new"><h4>新兴方向</h4><ul>{new_items}</ul></div>
  </div>
</div>""")

    learned_kws = synthesis.get("learned_kws", [])
    if learned_kws:
        kws_html = "".join(f'<span class="learned-kw">{_esc(k)}</span>' for k in learned_kws)
        parts.append(f"""
<div class="synth-block">
  <div class="synth-label">🧠 本周新关键词</div>
  <div class="learned-kw-list">{kws_html}</div>
</div>""")

    return "\n".join(parts)
