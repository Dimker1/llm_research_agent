import logging
import re

import yaml

from src.models import RawItem

logger = logging.getLogger(__name__)


def load_keywords(keywords_path: str = "config/keywords.yaml") -> dict:
    with open(keywords_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_pattern(words: list[str]) -> re.Pattern:
    escaped = [re.escape(w) for w in words]
    return re.compile("|".join(escaped), re.IGNORECASE)


class KeywordFilter:
    def __init__(self, keywords_path: str = "config/keywords.yaml"):
        cfg = load_keywords(keywords_path)
        self.directions = cfg.get("directions", {})
        self.exclude_words = cfg.get("exclude", {}).get("en", [])

        # 预编译：每个方向合并中英文关键词
        self._dir_patterns: dict[str, re.Pattern] = {}
        for direction, langs in self.directions.items():
            all_words = langs.get("en", []) + langs.get("zh", [])
            self._dir_patterns[direction] = _build_pattern(all_words)

        # 排除词 pattern
        self._exclude_pattern = _build_pattern(self.exclude_words) if self.exclude_words else None

    def filter(self, items: list[RawItem]) -> list[RawItem]:
        """保留命中任一方向关键词且未触发排除词的条目"""
        passed = []
        filtered = 0

        for item in items:
            text = f"{item.title} {item.abstract}"

            # 排除词检查（只在命中排除词但不命中任何方向词时排除）
            if self._exclude_pattern and self._exclude_pattern.search(text):
                # 如果同时命中方向词则保留
                hits_direction = any(p.search(text) for p in self._dir_patterns.values())
                if not hits_direction:
                    filtered += 1
                    continue

            # 至少命中一个方向关键词
            if any(p.search(text) for p in self._dir_patterns.values()):
                passed.append(item)
            else:
                filtered += 1

        logger.info(f"[keyword_filter] {len(items)} in → {len(passed)} pass, {filtered} filtered")
        return passed
