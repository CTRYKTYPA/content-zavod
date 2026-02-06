"""Сборщик TikTok по пользователям и хэштегам (yt-dlp). Без API — только yt-dlp.

Чтобы собирать стабильно:
- Сбор по users (никанеймы) использует web API — работает без app_info.
- Сбор по hashtags использует mobile API — нужны куки и/или app_info.
- Куки: залогиньтесь на tiktok.com, экспортируйте (Netscape) → TIKTOK_COOKIES_FILE
  или укажите TIKTOK_COOKIES_FROM_BROWSER=chrome.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .base_collector import BaseCollector
from config import settings
from database.models import ContentSource


def _is_quick() -> bool:
    return os.environ.get("STAGE1_QUICK") == "1"


def _ydl_base_tiktok(proxy: Optional[str]) -> dict:
    if _is_quick():
        format_spec = "best[height<=720][ext=mp4]/best[ext=mp4]/best"
    else:
        format_spec = (
            "bestvideo[height>=1080]+bestaudio/bestvideo[height>=720]+bestaudio/"
            "best[height>=1080]/best[ext=mp4]/best"
        )
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 15 if _is_quick() else 30,
        "retries": 1 if _is_quick() else 3,
        "format": format_spec,
        "merge_output_format": "mp4",
        "ignoreerrors": True,
    }
    if proxy:
        opts["proxy"] = proxy

    cf = getattr(settings, "TIKTOK_COOKIES_FILE", None)
    cfb = getattr(settings, "TIKTOK_COOKIES_FROM_BROWSER", None)
    if cf and Path(cf).exists():
        opts["cookiefile"] = str(Path(cf).resolve())
    elif cfb:
        b = cfb.strip().lower()
        opts["cookiesfrombrowser"] = (b, None, None, None)

    app_info = getattr(settings, "TIKTOK_EXTRACTOR_APP_INFO", None) or ""
    device_id = getattr(settings, "TIKTOK_EXTRACTOR_DEVICE_ID", None) or ""
    if app_info or device_id:
        ea: dict[str, Any] = {}
        if app_info:
            ea["app_info"] = [s.strip() for s in app_info.split(";") if s.strip()]
        if device_id:
            ea["device_id"] = device_id.strip()
        if ea:
            opts["extractor_args"] = {"TikTok": ea}

    return opts


def _parse_source_value(source: ContentSource) -> dict:
    """source_value: JSON с ключами users и/или hashtags."""
    val = source.source_value or "{}"
    try:
        data = json.loads(val)
    except json.JSONDecodeError:
        data = {}
    users = data.get("users") or []
    tags = data.get("hashtags") or []
    if not users and not tags:
        s = (val or "").strip()
        if s.startswith("@"):
            users = [s.lstrip("@").strip()]
        elif s.startswith("#"):
            tags = [s.lstrip("#").strip()]
        elif s:
            users = [s.strip()]
    return {"users": [u.strip().lstrip("@") for u in users if u], "hashtags": [t.strip().lstrip("#") for t in tags if t]}


def _is_mostly_arabic(text: str) -> bool:
    if not (text or isinstance(text, str)):
        return False
    s = "".join(c for c in text if not c.isspace())
    if not s:
        return False
    arabic = sum(1 for c in s if "\u0600" <= c <= "\u06FF")
    return arabic / len(s) > 0.4


class TikTokCollector(BaseCollector):
    """Сбор TikTok по юзерам и хэштегам. 10–180 сек, фильтр по лайкам/просмотрам."""

    def __init__(self, source: ContentSource, proxy: Optional[str] = None):
        super().__init__(source)
        self.proxy = proxy
        self._parsed = _parse_source_value(source)
        self.users = self._parsed.get("users") or []
        self.hashtags = self._parsed.get("hashtags") or []
        self.min_duration = int(self._parsed.get("min_duration", 10))
        self.max_duration = int(self._parsed.get("max_duration", 180))

    def collect_videos(
        self,
        limit: Optional[int] = None,
        exclude_source_ids: Optional[set[str]] = None,
    ) -> list[dict[str, Any]]:
        """Собрать видео по users и/или hashtags. exclude_source_ids — уже в БД."""
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp не установлен. pip install yt-dlp")
            return []

        cap = limit or 100
        quick = _is_quick() and cap <= 12
        quick_demo = quick and cap <= 6

        min_likes = self.source.min_likes if self.source.min_likes is not None else 10000
        min_views = self.source.min_views
        if quick_demo:
            min_likes = 0
            min_views = 0

        seen_ids: set[str] = set()
        exclude = exclude_source_ids or set()
        results: list[dict[str, Any]] = []

        ydl_opts = {**_ydl_base_tiktok(self.proxy)}

        def process_entries(entries: list) -> bool:
            nonlocal results, seen_ids
            for e in entries:
                if e is None or not isinstance(e, dict):
                    continue
                vid = e.get("id")
                if not vid:
                    vid = e.get("webpage_url", "").split("/video/")[-1].split("?")[0]
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
                url = e.get("webpage_url") or f"https://www.tiktok.com/@{e.get('uploader','')}/video/{vid}"
                thumb = e.get("thumbnail") or ""
                if not thumb and isinstance(e.get("thumbnails"), list) and e["thumbnails"]:
                    thumb = (e["thumbnails"][0] or {}).get("url") or ""
                results.append({
                    "source_url": url,
                    "source_post_id": str(vid),
                    "source_author": e.get("uploader") or e.get("channel") or "tiktok",
                    "title": title,
                    "description": (e.get("description") or "")[:500],
                    "tags": [],
                    "duration": duration,
                    "video_url": url,
                    "thumbnail_url": thumb or "",
                    "metadata": {
                        "view_count": view_count,
                        "likes": like_count,
                        "like_count": like_count,
                    },
                })
                return True
            return False

        urls_to_fetch: list[tuple[str, str]] = []

        for u in self.users:
            if len(results) >= cap:
                break
            u = (u or "").strip().lstrip("@")
            if not u:
                continue
            urls_to_fetch.append((f"https://www.tiktok.com/@{u}", f"user:{u}"))

        for t in self.hashtags:
            if len(results) >= cap:
                break
            t = (t or "").strip().lstrip("#")
            if not t:
                continue
            urls_to_fetch.append((f"https://www.tiktok.com/tag/{t}", f"tag:{t}"))

        if quick_demo:
            urls_to_fetch = urls_to_fetch[:4]

        for url, label in urls_to_fetch:
            if len(results) >= cap:
                break
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                except Exception as e:
                    logger.warning(f"tiktok {label}: {e}")
                    continue
            if not info:
                continue
            entries = info.get("entries") or []
            process_entries(entries)
            if len(results) >= cap:
                break

        return results

    def download_video(self, video_url: str, output_path: str) -> bool:
        """Скачать видео по URL через yt-dlp (так же, как YouTube)."""
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp не установлен")
            return False

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(out.with_suffix("")) + ".%(ext)s"
        opts = {**_ydl_base_tiktok(self.proxy), "outtmpl": out_tmpl, "noplaylist": True}

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.download([video_url])
            except Exception as e:
                logger.error(f"tiktok download {video_url}: {e}")
                return False

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
