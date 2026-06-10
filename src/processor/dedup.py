import logging

from src.models import RawItem
from src.storage.db import Database

logger = logging.getLogger(__name__)


def dedup(items: list[RawItem], db: Database) -> list[RawItem]:
    """过滤掉数据库中已分析的条目，返回需要处理的条目列表（含新条目和已存但未分析的条目）"""
    new_items = []
    skipped = 0
    for item in items:
        if db.is_analyzed(item.id):
            skipped += 1
        else:
            new_items.append(item)

    logger.info(f"[dedup] {len(items)} total → {len(new_items)} unanalyzed, {skipped} skipped")
    return new_items
