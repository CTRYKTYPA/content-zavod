"""Сборщик YouTube Shorts по хэштегам (yt-dlp + ytsearch)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .base_collector import BaseCollector
from database.models import ContentSource
from config import settings


def _is_quick() -> bool:
    return os.environ.get("STAGE1_QUICK") == "1"


def _ydl_base(proxy: Optional[str]) -> dict:
    # Quick: 720p mp4, без merge — быстрее скачивание. Иначе 1080p+.
    if _is_quick():
        format_spec = "best[height<=720][ext=mp4]/best[ext=mp4]/best"
    else:
        format_spec = (
            "bestvideo[height>=1080]+bestaudio/bestvideo[height>=720]+bestaudio/"
            "best[height>=1080]/best[ext=mp4]/best"
        )
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 15 if _is_quick() else 30,
        "retries": 1 if _is_quick() else 3,
        "format": format_spec,
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": {"player_client": ["android_sdkless"]}},
        "ignoreerrors": True,
    }
    if proxy:
        opts["proxy"] = proxy
    return opts


def _is_mostly_arabic(text: str) -> bool:
    """Пропускать ролики с заголовком в основном на арабском."""
    if not (text or isinstance(text, str)):
        return False
    s = "".join(c for c in text if not c.isspace())
    if not s:
        return False
    arabic = sum(1 for c in s if "\u0600" <= c <= "\u06FF")
    return arabic / len(s) > 0.4


def _parse_source_value(source: ContentSource) -> dict:
    """source_value: JSON с ключами hashtags, либо строка с одним хэштегом."""
    val = source.source_value or "{}"
    try:
        data = json.loads(val)
    except json.JSONDecodeError:
        data = {}
    if "hashtags" in data:
        return data
    tag = (val or "").strip()
    if not tag.startswith("#"):
        tag = f"#{tag}"
    return {"hashtags": [tag]} if tag else {"hashtags": []}


class YouTubeShortsCollector(BaseCollector):
    """Сбор YouTube Shorts по хэштегам. 10–120 сек, фильтр по лайкам (например 10k+)."""

    def __init__(self, source: ContentSource, proxy: Optional[str] = None):
        super().__init__(source)
        self.proxy = proxy
        self._parsed = _parse_source_value(source)
        self.hashtags = self._parsed.get("hashtags") or []
        self.min_duration = int(self._parsed.get("min_duration", 10))
        self.max_duration = int(self._parsed.get("max_duration", 120))

    def collect_videos(
        self,
        limit: Optional[int] = None,
        exclude_source_ids: Optional[set[str]] = None,
    ) -> list[dict[str, Any]]:
        """Собрать Shorts по хэштегам. Фильтр: 10–120 сек, min_likes из источника.
        exclude_source_ids: уже есть в БД — перебираем кандидатов по тегу, пока не найдём нового."""
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp не установлен. pip install yt-dlp")
            return []

        cap = limit or 100
        quick = _is_quick() and cap <= 12
        quick_demo = quick and cap <= 6
        tags_to_use = self.hashtags[:3] if quick_demo else self.hashtags

        min_likes = self.source.min_likes if self.source.min_likes is not None else 10000
        min_views = self.source.min_views
        if quick_demo:
            min_likes = 0
            min_views = 0
        seen_ids: set[str] = set()
        exclude = exclude_source_ids or set()
        results: list[dict[str, Any]] = []
        ydl_opts = {**_ydl_base(self.proxy), "extract_flat": quick}

        def process_entries(entries: list) -> bool:
            """Обработать entries, добавить первого подходящего. Возврат: добавили ли."""
            nonlocal results, seen_ids
            for e in entries:
                if e is None or not isinstance(e, dict):
                    continue
                vid = e.get("id")
                if not vid or vid in seen_ids:
                    continue
                if vid in exclude:
                    seen_ids.add(vid)
                    continue
                duration = e.get("duration")
                if duration is not None and not (self.min_duration <= duration <= self.max_duration):
                    continue
                if not quick and duration is None:
                    continue
                like_count = e.get("like_count")
                if like_count is not None and like_count < min_likes:
                    continue
                view_count = e.get("view_count")
                if min_views and view_count is not None and view_count < min_views:
                    continue
                if not quick and (like_count is None or (min_views and view_count is None)):
                    continue
                title = (e.get("title") or "")[:500]
                if _is_mostly_arabic(title):
                    continue
                seen_ids.add(vid)
                url = e.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
                results.append({
                    "source_url": url,
                    "source_post_id": vid,
                    "source_author": e.get("uploader") or e.get("channel") or "youtube",
                    "title": title,
                    "description": (e.get("description") or "")[:500],
                    "tags": [],
                    "duration": duration,
                    "video_url": url,
                    "thumbnail_url": e.get("thumbnail") or "",
                    "metadata": {
                        "view_count": view_count,
                        "likes": like_count,
                        "like_count": like_count,
                    },
                })
                return True
            return False

        for tag in tags_to_use:
            if len(results) >= cap:
                break
            t = tag.strip()
            if not t.startswith("#"):
                t = f"#{t}"
            lang = (getattr(settings, "YOUTUBE_SEARCH_LANG_HINT", None) or "").strip()
            base_limit = 3 if quick_demo else (5 if quick else min(15, max(6, cap - len(results) + 4)))
            page_size = 300
            max_pages = 3
            if exclude:
                search_limit = max(base_limit, page_size)
                queries = [
                    f"{t} shorts" + (f" {lang}" if lang else ""),
                    f"{t} shorts",
                    f"{t} shorts 2024",
                ]
            else:
                search_limit = base_limit
                queries = [f"{t} shorts" + (f" {lang}" if lang else "")]

            added_from_tag = False
            for qi, query in enumerate(queries):
                if added_from_tag or len(results) >= cap:
                    break
                for page in range(max_pages if exclude else 1):
                    if added_from_tag or len(results) >= cap:
                        break
                    start = page * page_size + 1
                    end = (page + 1) * page_size
                    req_opts = {**ydl_opts}
                    if exclude and page > 0:
                        req_opts["playlist_start"] = start
                        req_opts["playlist_end"] = end
                    ytsearch = f"ytsearch{end}:{query}"
                    with yt_dlp.YoutubeDL(req_opts) as ydl:
                        try:
                            info = ydl.extract_info(ytsearch, download=False)
                        except Exception as e:
                            logger.warning(f"yt-dlp поиск {query}: {e}")
                            continue
                    if not info:
                        continue
                    entries = info.get("entries") or []
                    added_from_tag = process_entries(entries)
                    if added_from_tag:
                        break
                    if not entries:
                        break
                    if exclude and page < max_pages - 1 and len(entries) >= page_size:
                        pass
                    elif exclude and page < max_pages - 1:
                        break
                if added_from_tag:
                    break

        return results

    def download_video(self, video_url: str, output_path: str) -> bool:
        """Скачать видео по URL через yt-dlp."""
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp не установлен")
            return False

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(out.with_suffix("")) + ".%(ext)s"
        opts = {**_ydl_base(self.proxy), "outtmpl": out_tmpl}

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.download([video_url])
            except Exception as e:
                logger.error(f"yt-dlp download {video_url}: {e}")
                return False

        # yt-dlp при bestvideo+bestaudio создаёт: id.mp4 (слитый), id.f251.webm (видео),
        # id.xxx.m4a (аудио) и т.д. Оставляем только итоговый .mp4, остальное удаляем.
        stem = out.stem
        candidates: list[Path] = []
        for c in out.parent.glob(f"{stem}*"):
            if c == out or ".part" in c.name:
                continue
            candidates.append(c)

        if out.exists():
            for p in candidates:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            return True

        mp4 = next((p for p in candidates if p.suffix.lower() == ".mp4"), None)
        if mp4:
            try:
                mp4.rename(out)
            except OSError:
                pass
        for p in candidates:
            if p.exists():
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
        return out.exists()
