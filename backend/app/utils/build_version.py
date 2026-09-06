"""Версия собранного фронтенда — для обхода кеша Telegram.

index.html отдаётся с `Cache-Control: no-cache, no-store`, но webview Telegram
это игнорирует и продолжает показывать старую сборку после деплоя. Надёжно
помогает только изменившийся URL, поэтому к адресу мини-аппы дописывается
хеш собранного бандла: пересобрали фронт — адрес другой — телега грузит заново.
"""

import re
from pathlib import Path

_DIST_INDEX = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"
_ASSET_RE = re.compile(r"assets/index-([A-Za-z0-9_-]+)\.js")

_cached: str | None = None


def build_version() -> str:
    """Хеш главного чанка. Читается один раз за жизнь процесса — сервер и так
    перезапускается после пересборки."""
    global _cached
    if _cached is None:
        try:
            match = _ASSET_RE.search(_DIST_INDEX.read_text(encoding="utf-8"))
            _cached = match.group(1) if match else "dev"
        except OSError:
            _cached = "dev"
    return _cached


def mini_app_url(base_url: str, team_id: int | None = None) -> str:
    """Адрес мини-аппы с версией сборки и, если нужно, номером проекта."""
    params = [f"v={build_version()}"]
    if team_id is not None:
        params.insert(0, f"team={team_id}")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{'&'.join(params)}"
