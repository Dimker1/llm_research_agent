import logging
from datetime import datetime, timezone

import feedparser

from src.fetcher.base import BaseFetcher
from src.models import RawItem
from src.storage.db import make_item_id

logger = logging.getLogger(__name__)


class RSSFetcher(BaseFetcher):
    def __init__(self, name: str, url: str, lang: str = "en", max_entries: int = 30):
        self._name = name
        self.url = url
        self.lang = lang
        self.max_entries = max_entries

    @property
    def source_name(self) -> str:
        return self._name

    def fetch(self) -> list[RawItem]:
        results = []
        try:
            feed = feedparser.parse(self.url)
            if feed.bozo and not feed.entries:
                logger.warning(f"[RSSFetcher:{self._name}] parse error: {feed.bozo_exception}")
                return []

            for entry in feed.entries[: self.max_entries]:
                url = entry.get("link", "")
                if not url:
                    continue

                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", ""))
                # 去除 HTML 标签（简单处理）
                summary = _strip_html(summary)[:1000]

                published = _parse_published(entry)

                item_id = make_item_id({"source": self._name, "url": url})
                results.append(RawItem(
                    id=item_id,
                    title=title,
                    abstract=summary,
                    url=url,
                    source=self._name,
                    lang=self.lang,
                    published=published,
                ))

        except Exception as e:
            logger.error(f"[RSSFetcher:{self._name}] fetch failed: {e}")

        logger.info(f"[RSSFetcher:{self._name}] fetched {len(results)} entries")
        return results


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_published(entry) -> str:
    """将 feedparser 的 published_parsed 转为 ISO 8601 字符串"""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            import time
            ts = time.mktime(entry.published_parsed)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    return datetime.now(tz=timezone.utc).isoformat()
