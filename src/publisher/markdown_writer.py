import logging
from datetime import datetime
from pathlib import Path

from src.models import AnalyzedItem

logger = logging.getLogger(__name__)

DIRECTION_META = {
    "pretraining": ("🏗️", "预训练方向"),
    "post_training": ("🎯", "后训练方向"),
    "agent": ("🤖", "LLM Agent 方向"),
}


def write_weekly_markdown(
    items: list[AnalyzedItem],
    week_label: str,
    date_range: tuple[str, str],
    output_dir: str = "weekly",
    source_stats: dict = None,
    elapsed_seconds: float = 0.0,
) -> str:
    """
    生成周报 Markdown，返回文件路径。
    week_label: '2026-W23'
    date_range: ('2026-06-02', '2026-06-08')
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filepath = str(Path(output_dir) / f"{week_label}.md")

    groups: dict[str, list[AnalyzedItem]] = {k: [] for k in DIRECTION_META}
    for item in items:
        if item.direction in groups:
            groups[item.direction].append(item)

    total_count = sum(len(v) for v in groups.values())
    start_date, end_date = date_range

    lines = []

    # ── 标题 ──
    lines.append(f"# 📚 LLM 前沿技术周报 | {week_label}")
    lines.append(f"> 覆盖时间：{start_date} → {end_date}\n")

    # ── 来源统计 ──
    if source_stats:
        stats_str = " | ".join(f"{k}({v})" for k, v in source_stats.items())
        lines.append(f"> 本周来源：{stats_str} | 精选高相关内容 **{total_count}** 条\n")
    else:
        lines.append(f"> 本周精选高相关内容 **{total_count}** 条\n")

    lines.append("---\n")

    # ── 各方向内容 ──
    for direction, (icon, label) in DIRECTION_META.items():
        direction_items = groups[direction]
        count = len(direction_items)
        lines.append(f"## {icon} {label} ({count} 条)\n")

        if not direction_items:
            lines.append("*本周暂无相关内容*\n")
        else:
            for idx, item in enumerate(direction_items, 1):
                lines.extend(_format_item(idx, item))

        lines.append("---\n")

    # ── 页脚 ──
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M CST")
    elapsed_str = f"{elapsed_seconds:.0f}s" if elapsed_seconds else "—"
    lines.append(f"*生成时间：{now_str} | 处理耗时：{elapsed_str}*\n")

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"[markdown_writer] wrote {total_count} items → {filepath}")
    return filepath


def _format_item(idx: int, item: AnalyzedItem) -> list[str]:
    lines = []
    lines.append(f"### {idx}. [{item.title}]({item.url})\n")

    meta_parts = [
        f"**来源**：{item.source}",
        f"**日期**：{item.published[:10]}",
        f"**相关度**：{item.relevance_score}/10",
    ]
    if item.authors:
        authors_str = ", ".join(item.authors[:3])
        if len(item.authors) > 3:
            authors_str += " 等"
        meta_parts.append(f"**作者**：{authors_str}")
    if item.keywords:
        kw_str = " ".join(f"`{k}`" for k in item.keywords)
        meta_parts.append(f"**关键词**：{kw_str}")

    lines.append(" | ".join(meta_parts) + "\n")

    if item.summary_zh:
        lines.append(f"> {item.summary_zh}\n")

    lines.append("")
    return lines
