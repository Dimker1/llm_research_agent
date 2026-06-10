"""
主入口：运行一次完整的周报生成流程。

用法：
    python -m src.main                        # 周报模式，覆盖过去 7 天
    python -m src.main --week 2026-W23        # 指定 ISO 周次
    python -m src.main --no-telegram          # 跳过 Telegram 推送（调试用）
    python -m src.main --dry-run              # 只抓取和过滤，不调用 LLM
"""

import argparse
import logging
import time
from collections import defaultdict
from datetime import date as Date, timedelta

import yaml

from src.fetcher.arxiv_fetcher import ArxivFetcher
from src.fetcher.rss_fetcher import RSSFetcher
from src.processor.dedup import dedup
from src.processor.keyword_filter import KeywordFilter
from src.processor.llm_analyzer import LLMAnalyzer
from src.publisher.html_writer import write_weekly_html
from src.publisher.telegram_sender import send_daily_digest
from src.storage.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(path: str = "config/sources.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_fetchers(sources_cfg: dict, lookback_hours: int = None) -> list:
    fetchers = []

    ax = sources_cfg.get("arxiv", {})
    if ax.get("enabled", True):
        fetchers.append(ArxivFetcher(
            categories=ax.get("categories", ["cs.CL", "cs.AI", "cs.LG"]),
            max_results=ax.get("max_results", 500),
            # 周报：默认回溯 8 天（7天 + 1天缓冲）
            lookback_hours=lookback_hours or ax.get("lookback_hours", 192),
        ))

    for src in sources_cfg.get("rss", []):
        if src.get("enabled", False):
            fetchers.append(RSSFetcher(
                name=src["name"],
                url=src["url"],
                lang=src.get("lang", "en"),
            ))

    return fetchers


def _week_date_range(today: Date) -> tuple[str, str, str]:
    """
    返回 (week_label, start_date, end_date)
    week_label 形如 '2026-W23'
    start_date / end_date 为 YYYY-MM-DD，覆盖本周一到今天
    """
    # ISO 周一为一周开始
    monday = today - timedelta(days=today.weekday())
    week_label = f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"
    return week_label, monday.isoformat(), today.isoformat()


def run_weekly(
    week_label: str = None,
    no_telegram: bool = False,
    dry_run: bool = False,
) -> str:
    start_time = time.time()
    cfg = load_config()
    sources_cfg = load_sources()

    today = Date.today()
    if week_label:
        # 解析 2026-W23 → 找到该周一和周日
        year, w = week_label.split("-W")
        monday = Date.fromisocalendar(int(year), int(w), 1)
        sunday = monday + timedelta(days=6)
        end_date = min(sunday, today).isoformat()
        start_date = monday.isoformat()
        label = week_label
    else:
        label, start_date, end_date = _week_date_range(today)

    logger.info(f"=== LLM Weekly Digest | {label} ({start_date} → {end_date}) ===")

    db_path = cfg.get("storage", {}).get("db_path", "data/digest.db")
    db = Database(db_path)

    kw_filter = KeywordFilter("config/keywords.yaml")

    llm_cfg = cfg.get("llm", {})
    analyzer = LLMAnalyzer(
        model=llm_cfg.get("model", "Claude-Sonnet-4.6"),
        max_tokens=llm_cfg.get("max_tokens", 512),
        min_score=llm_cfg.get("min_relevance_score", 5),
        max_retries=llm_cfg.get("max_retries", 2),
        abstract_max_chars=cfg.get("pipeline", {}).get("abstract_max_chars", 2000),
    )

    output_cfg = cfg.get("output", {})
    weekly_dir = output_cfg.get("weekly_dir", "weekly")
    tg_cfg = cfg.get("telegram", {})

    # 周报回溯天数 = start→end 天数 + 1天缓冲
    days_span = (Date.fromisoformat(end_date) - Date.fromisoformat(start_date)).days + 2
    lookback_hours = days_span * 24

    # ── Step 1: 采集 ──
    fetchers = build_fetchers(sources_cfg, lookback_hours=lookback_hours)
    all_raw = []
    source_stats = {}

    for fetcher in fetchers:
        try:
            items = fetcher.fetch()
            source_stats[fetcher.source_name] = len(items)
            all_raw.extend(items)
        except Exception as e:
            logger.error(f"[main] fetcher {fetcher.source_name} failed: {e}")
            source_stats[fetcher.source_name] = 0

    logger.info(f"[main] total fetched: {len(all_raw)} items from {len(fetchers)} sources")

    # ── Step 2: 去重 ──
    new_items = dedup(all_raw, db)

    # ── Step 3: 关键词粗筛 ──
    candidates = kw_filter.filter(new_items)

    # ── Step 3.5: 候选裁剪（防止 LLM 调用量爆炸）──
    # 关键词命中越多 → 优先级越高；同优先级内 arXiv 优先
    llm_cap = cfg.get("pipeline", {}).get("max_llm_candidates", 120)
    if len(candidates) > llm_cap:
        original_count = len(candidates)
        def _priority(item):
            text = f"{item.title} {item.abstract}"
            hits = sum(1 for p in kw_filter._dir_patterns.values() if p.search(text))
            return (-hits, 0 if item.source == "arxiv" else 1)
        candidates.sort(key=_priority)
        candidates = candidates[:llm_cap]
        logger.info(f"[main] candidates capped to {llm_cap} for LLM (was {original_count})")

    if dry_run:
        logger.info(f"[main] --dry-run: {len(candidates)} candidates after filter")
        db.close()
        return ""

    # ── Step 4: 存储原始条目 ──
    for item in new_items:
        db.insert_item(item)

    # ── Step 5: LLM 分析 ──
    analyzed_items = analyzer.batch_analyze(candidates)

    # ── Step 6: 存储分析结果 ──
    for item in analyzed_items:
        db.insert_analysis(item)

    # ── Step 7: 查询整周高质量条目 ──
    min_score = llm_cfg.get("min_relevance_score", 5)
    final_items = db.get_analyzed_items_range(start_date, end_date, min_score=min_score)

    # 按相关性降序排，先取全局 Top-N，再对每个方向做上限保护
    target_total = cfg.get("pipeline", {}).get("target_total_items", 20)
    max_per_dir = cfg.get("pipeline", {}).get("max_items_per_direction", 10)

    # 全局按分数降序
    final_items.sort(key=lambda x: x.relevance_score, reverse=True)

    # 两轮选取：先保证每方向至少有机会，再补到 target_total
    dir_counts: dict[str, int] = defaultdict(int)
    trimmed: list = []
    for item in final_items:
        if len(trimmed) >= target_total:
            break
        if dir_counts[item.direction] < max_per_dir:
            trimmed.append(item)
            dir_counts[item.direction] += 1
    final_items = trimmed

    elapsed = time.time() - start_time

    # ── Step 8: 生成周报 HTML ──
    md_path = write_weekly_html(
        items=final_items,
        week_label=label,
        date_range=(start_date, end_date),
        output_dir=weekly_dir,
        source_stats=source_stats,
        elapsed_seconds=elapsed,
    )

    # ── Step 9: 记录元数据 ──
    db.record_digest(label, md_path, len(final_items))
    db.close()

    # ── Step 10: Telegram 推送 ──
    if not no_telegram:
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
        send_daily_digest(
            content,
            max_message_length=tg_cfg.get("max_message_length", 3800),
            send_interval=tg_cfg.get("send_interval_seconds", 1.0),
        )

    elapsed_total = time.time() - start_time
    logger.info(f"=== Done in {elapsed_total:.1f}s | {len(final_items)} items | {md_path} ===")
    return md_path


def main():
    parser = argparse.ArgumentParser(description="LLM Weekly Research Digest")
    parser.add_argument("--week", default=None, help="ISO week label, e.g. 2026-W23 (default: current week)")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram push")
    parser.add_argument("--dry-run", action="store_true", help="Fetch & filter only, no LLM")
    args = parser.parse_args()

    run_weekly(
        week_label=args.week,
        no_telegram=args.no_telegram,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
