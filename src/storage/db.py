import hashlib
import json
import sqlite3
from pathlib import Path

from src.models import RawItem, AnalyzedItem


DDL = """
CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    abstract    TEXT,
    url         TEXT,
    source      TEXT,
    lang        TEXT DEFAULT 'en',
    published   TEXT,
    authors     TEXT,          -- JSON array
    categories  TEXT,          -- JSON array
    pdf_url     TEXT DEFAULT '',
    fetched_at  TEXT DEFAULT (datetime('now')),
    is_analyzed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS analyses (
    item_id         TEXT PRIMARY KEY REFERENCES items(id),
    relevance_score INTEGER,
    direction       TEXT,
    summary_zh      TEXT,
    keywords        TEXT,      -- JSON array
    reason          TEXT,
    analyzed_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS digests (
    date        TEXT PRIMARY KEY,
    filepath    TEXT,
    item_count  INTEGER,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS weekly_memory (
    week_label   TEXT PRIMARY KEY,           -- 形如 2026-W23
    tldr         TEXT,                       -- 本周一段话总结
    top_picks    TEXT,                       -- JSON: [{"id","title","why"}, ...] 编辑精选
    themes       TEXT,                       -- JSON: [{"name","summary","item_ids":[...]}, ...]
    learned_kws  TEXT,                       -- JSON: ["kw1","kw2",...] 本周新学到的关键词
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_items_published ON items(published);
CREATE INDEX IF NOT EXISTS idx_items_source    ON items(source);
CREATE INDEX IF NOT EXISTS idx_analyses_dir    ON analyses(direction);
CREATE INDEX IF NOT EXISTS idx_analyses_score  ON analyses(relevance_score);
"""


def make_item_id(item: dict) -> str:
    """生成稳定的去重 ID"""
    if item.get("source") == "arxiv":
        raw_id = item.get("id", "")
        # arxiv entry_id 形如 http://arxiv.org/abs/2506.01234v1
        return raw_id.split("/")[-1].split("v")[0]
    url = item.get("url", item.get("id", ""))
    return hashlib.md5(url.encode()).hexdigest()[:16]


class Database:
    def __init__(self, db_path: str = "data/digest.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL 模式：允许并发读写，避免 ThreadPoolExecutor 写入时 database is locked
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(DDL)
        self.conn.commit()

    def is_duplicate(self, item_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,))
        return cur.fetchone() is not None

    def is_analyzed(self, item_id: str) -> bool:
        """返回该条目是否已完成分析（存在于 analyses 表）"""
        cur = self.conn.execute("SELECT 1 FROM analyses WHERE item_id = ?", (item_id,))
        return cur.fetchone() is not None

    def insert_item(self, item: RawItem) -> bool:
        """插入原始条目，已存在则跳过，返回是否成功插入"""
        if self.is_duplicate(item.id):
            return False
        self.conn.execute(
            """INSERT OR IGNORE INTO items
               (id, title, abstract, url, source, lang, published, authors, categories, pdf_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.title,
                item.abstract,
                item.url,
                item.source,
                item.lang,
                item.published,
                json.dumps(item.authors, ensure_ascii=False),
                json.dumps(item.categories, ensure_ascii=False),
                item.pdf_url,
            ),
        )
        self.conn.commit()
        return True

    def insert_analysis(self, item: AnalyzedItem) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO analyses
               (item_id, relevance_score, direction, summary_zh, keywords, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                item.id,
                item.relevance_score,
                item.direction,
                item.summary_zh,
                json.dumps(item.keywords, ensure_ascii=False),
                item.reason,
            ),
        )
        self.conn.execute(
            "UPDATE items SET is_analyzed = 1 WHERE id = ?", (item.id,)
        )
        self.conn.commit()

    def get_analyzed_items(self, date: str, min_score: int = 5) -> list[AnalyzedItem]:
        """查询指定日期、达到分数阈值的已分析条目"""
        return self.get_analyzed_items_range(date, date, min_score)

    def get_analyzed_items_range(
        self, start_date: str, end_date: str, min_score: int = 5
    ) -> list[AnalyzedItem]:
        """查询日期区间 [start_date, end_date] 内的已分析条目，按方向+分数排序。

        统一按 published 日期过滤，保证结果只包含目标周期内发布的内容。
        arXiv 跨天问题通过 lookback_hours 加缓冲（main.py 中 +2天）解决，不在查询层放宽。
        """
        cur = self.conn.execute(
            """SELECT i.*, a.relevance_score, a.direction, a.summary_zh, a.keywords, a.reason
               FROM items i
               JOIN analyses a ON i.id = a.item_id
               WHERE DATE(i.published) BETWEEN ? AND ?
                 AND a.relevance_score >= ?
                 AND a.direction != 'other'
               ORDER BY a.direction, a.relevance_score DESC""",
            (start_date, end_date, min_score),
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            results.append(AnalyzedItem(
                id=row["id"],
                title=row["title"],
                abstract=row["abstract"] or "",
                url=row["url"] or "",
                source=row["source"] or "",
                lang=row["lang"] or "en",
                published=row["published"] or "",
                authors=json.loads(row["authors"] or "[]"),
                categories=json.loads(row["categories"] or "[]"),
                pdf_url=row["pdf_url"] or "",
                relevance_score=row["relevance_score"],
                direction=row["direction"],
                summary_zh=row["summary_zh"] or "",
                keywords=json.loads(row["keywords"] or "[]"),
                reason=row["reason"] or "",
            ))
        return results

    def record_digest(self, date: str, filepath: str, item_count: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO digests (date, filepath, item_count) VALUES (?, ?, ?)",
            (date, filepath, item_count),
        )
        self.conn.commit()

    # ── weekly memory（Agent synthese 层） ──
    def save_weekly_memory(
        self,
        week_label: str,
        tldr: str,
        top_picks: list[dict],
        themes: list[dict],
        learned_kws: list[str],
    ) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO weekly_memory
               (week_label, tldr, top_picks, themes, learned_kws)
               VALUES (?, ?, ?, ?, ?)""",
            (
                week_label,
                tldr,
                json.dumps(top_picks, ensure_ascii=False),
                json.dumps(themes, ensure_ascii=False),
                json.dumps(learned_kws, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def get_weekly_memory(self, week_label: str) -> dict | None:
        cur = self.conn.execute(
            "SELECT * FROM weekly_memory WHERE week_label = ?", (week_label,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "week_label": row["week_label"],
            "tldr": row["tldr"] or "",
            "top_picks": json.loads(row["top_picks"] or "[]"),
            "themes": json.loads(row["themes"] or "[]"),
            "learned_kws": json.loads(row["learned_kws"] or "[]"),
        }

    def get_previous_weekly_memory(self, current_week_label: str) -> dict | None:
        """返回 week_label < current_week_label 的最近一周记忆。"""
        cur = self.conn.execute(
            """SELECT * FROM weekly_memory
               WHERE week_label < ?
               ORDER BY week_label DESC
               LIMIT 1""",
            (current_week_label,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "week_label": row["week_label"],
            "tldr": row["tldr"] or "",
            "top_picks": json.loads(row["top_picks"] or "[]"),
            "themes": json.loads(row["themes"] or "[]"),
            "learned_kws": json.loads(row["learned_kws"] or "[]"),
        }

    def close(self) -> None:
        self.conn.close()
