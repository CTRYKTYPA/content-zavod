#!/usr/bin/env python3
"""
Получить YouTube refresh_token для загрузки видео.

Запуск:
  python scripts/get_youtube_refresh_token.py
  python scripts/get_youtube_refresh_token.py path/to/client_secret_xxx.json

Откроется браузер — войди в Google-аккаунт (с YouTube каналом).
Скопируй refresh_token в .env как YOUTUBE_REFRESH_TOKEN.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not json_path:
        candidates = [
            ROOT / "client_secret.json",
            ROOT / "client_secrets.json",
        ]
        downloads = Path.home() / "Downloads"
        if downloads.exists():
            candidates.extend(downloads.glob("client_secret*.json"))
        for p in candidates:
            if p.exists():
                json_path = p
                break
    if not json_path or not json_path.exists():
        print("Файл client_secrets не найден.")
        print("Укажи путь: python scripts/get_youtube_refresh_token.py C:\\path\\to\\client_secret_xxx.json")
        print("Или положи client_secret_xxx.json в корень проекта как client_secret.json")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("pip install google-auth-oauthlib")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(json_path), SCOPES)
    creds = flow.run_local_server(port=8090)

    if not creds.refresh_token:
        print("refresh_token не выдан. Попробуй снова, согласись на все запрашиваемые права.")
        return 1

    print()
    print("=" * 60)
    print("YOUTUBE_REFRESH_TOKEN=" + creds.refresh_token)
    print("=" * 60)
    print()
    print("Добавь эту строку в .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
