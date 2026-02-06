#!/usr/bin/env python3
"""
Проверка публикации на YouTube через OAuth.

1. Проверяет OAuth (канал пользователя)
2. Загружает тестовое видео как public

Запуск:
  python scripts/test_youtube_upload.py              # только проверка OAuth
  python scripts/test_youtube_upload.py --upload     # + загрузка тестового видео
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings


def get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    client_id = settings.YOUTUBE_CLIENT_ID
    client_secret = settings.YOUTUBE_CLIENT_SECRET
    refresh_token = settings.YOUTUBE_REFRESH_TOKEN
    if not all([client_id, client_secret, refresh_token]):
        print("Нужны YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN в .env")
        return None

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube",
        ],
    )
    creds.refresh(Request())
    return creds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true", help="Загрузить тестовое видео (private)")
    args = ap.parse_args()

    print("1. Проверка OAuth...")
    creds = get_credentials()
    if not creds:
        return 1

    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=creds)

    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items") or []
    if not items:
        print("   Канал не найден. У аккаунта должен быть YouTube-канал.")
        return 1

    ch = items[0]
    title = ch.get("snippet", {}).get("title", "?")
    print(f"   OK. Канал: {title}")

    if not args.upload:
        print("\nOAuth работает. Для тестовой загрузки: python scripts/test_youtube_upload.py --upload")
        return 0

    print("\n2. Загрузка тестового видео (public)...")
    candidates = list((ROOT / "processed").rglob("*.mp4"))[:5]
    if not candidates:
        print("   Нет обработанных видео в processed/")
        return 1

    video_path = min(candidates, key=lambda p: p.stat().st_size)
    print(f"   Файл: {video_path.name} ({video_path.stat().st_size // 1024} KB)")

    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": "Test upload from content-zavod",
            "description": "Тест публикации через API",
        },
        "status": {"privacyStatus": "public"},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)

    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = req.execute()

    vid = resp.get("id")
    print(f"   OK. Видео загружено (public): https://www.youtube.com/watch?v={vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
