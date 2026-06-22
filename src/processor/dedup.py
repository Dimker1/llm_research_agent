import logging
import re
from collections import defaultdict

from src.models import RawItem
from src.storage.db import Database

logger = logging.getLogger(__name__)


def _normalize_title(title: str) -> str:
    """归一化标题：去标点、压空格、转小写。"""
    t = title.lower()
    t = re.sub(r"[^\w\u4e00-\u9fff\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _title_tokens(title: str) -> set[str]:
    norm = _normalize_title(title)
    if not norm:
        return set()
    # 中文按字符切分；英文按词切分；只保留长度 >= 2 的 token
    tokens: set[str] = set()
    for word in norm.split():
        if re.fullmatch(r"[a-z0-9]+", word):
            if len(word) >= 2:
                tokens.add(word)
        else:
            # 含中文：每个 unicode 字符算一个 token
            for ch in word:
                if "\u4e00" <= ch <= "\u9fff":
                    tokens.add(ch)
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedup(
    items: list[RawItem],
    db: Database,
    title_sim_threshold: float = 0.82,
) -> list[RawItem]:
    """去重：
    1. 跳过数据库中已分析的条目（按 ID）
    2. 同批次内按标题归一化做近似去重（Jaccard >= threshold 视为重复）
       - 优先保留信息更丰富的：abstract 更长 > arXiv 来源 > 其它
    """
    # 第一步：DB 已分析的去掉
    new_items = [item for item in items if not db.is_analyzed(item.id)]
    db_skipped = len(items) - len(new_items)

    # 第二步：标题相似度去重
    # 用归一化首词分桶，避免 O(n^2)；桶内做 Jaccard
    buckets: dict[str, list[tuple[set[str], RawItem]]] = defaultdict(list)
    deduped: list[RawItem] = []
    sim_skipped = 0

    def _quality(item: RawItem) -> tuple[int, int]:
        # 先优 arXiv（有作者元数据），再优 abstract 长度
        is_arxiv = 1 if item.source == "arxiv" else 0
        return (is_arxiv, len(item.abstract or ""))

    for item in new_items:
        tokens = _title_tokens(item.title)
        if not tokens:
            deduped.append(item)
            continue

        # bucket key：取前 3 个词典序最小的 token，命中任一桶就检查相似度
        sorted_tokens = sorted(tokens)
        bucket_keys = sorted_tokens[: min(3, len(sorted_tokens))]

        merged_with_existing = False
        for key in bucket_keys:
            for existing_tokens, existing_item in buckets[key]:
                if _jaccard(tokens, existing_tokens) >= title_sim_threshold:
                    if _quality(item) > _quality(existing_item):
                        try:
                            deduped.remove(existing_item)
                        except ValueError:
                            pass
                        deduped.append(item)
                        # 更新所有桶里的指针
                        for k in bucket_keys:
                            buckets[k] = [
                                (tokens, item) if it is existing_item else (et, it)
                                for et, it in buckets[k]
                            ]
                    # 无论是否替换，都视为"已合并"，不重复加入
                    sim_skipped += 1
                    merged_with_existing = True
                    break
            if merged_with_existing:
                break

        if not merged_with_existing:
            deduped.append(item)
            for key in bucket_keys:
                buckets[key].append((tokens, item))

    logger.info(
        f"[dedup] {len(items)} total → {len(deduped)} kept "
        f"(db_skipped={db_skipped}, title_sim_skipped={sim_skipped})"
    )
    return deduped
