"""Проверка GitHub-логина участника.

Без привязки к GitHub участник для продукта не существует: его коммиты
остаются ничьими, вклад не считается, а на экране он висит как «нет данных».
Поэтому логин обязателен при входе в проект — и его мало спросить, надо
убедиться, что он настоящий: «асдф» проходит любую проверку формата, а
коммиты к нему всё равно никогда не привяжутся.

Отдельный модуль, а не метод GitHubClient: тот создаётся под конкретный
owner/repo, а проверять логин нужно раньше, чем у команды появится
репозиторий.
"""

import re
import time
from dataclasses import dataclass

from backend.app.services.github_client import fetch_github_user

# Правила GitHub: латиница, цифры и дефисы, не в начале и не подряд, до 39 символов.
_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

# Анонимно GitHub даёт 60 запросов в час на IP, а через туннель этот IP один
# на всю команду. Форма проверяет логин на каждую паузу в наборе, поэтому без
# кеша лимит выбивается за пару минут — и все начинают видеть «сохранено без
# проверки». Кешируем только определённые ответы: «есть такой» и «нет такого»
# со временем не меняются, а вот «проверить не удалось» кешировать нельзя,
# иначе временный сбой залипнет на четверть часа.
_CACHE_TTL_SECONDS = 15 * 60
# Форма спрашивает про каждый набранный префикс («a», «an», «ann»), так что
# ключей копится куда больше, чем людей в командах. Просрочка снимается только
# при повторном обращении к тому же ключу, поэтому раз в N записей чистим кеш
# целиком — иначе он растёт всё время, пока живёт процесс.
_CACHE_MAX_ENTRIES = 500
_cache: dict[str, tuple[float, dict | None]] = {}


def _cached(login: str) -> tuple[bool, dict | None]:
    """(есть ли ответ в кеше, сам ответ)."""
    hit = _cache.get(login.lower())
    if not hit:
        return False, None
    stored_at, value = hit
    if time.monotonic() - stored_at > _CACHE_TTL_SECONDS:
        _cache.pop(login.lower(), None)
        return False, None
    return True, value


def _remember(login: str, value: dict | None) -> None:
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        cutoff = time.monotonic() - _CACHE_TTL_SECONDS
        for key in [k for k, (stored_at, _) in _cache.items() if stored_at <= cutoff]:
            _cache.pop(key, None)
        # Все записи ещё свежие — значит, кеш и правда переполнен, а не зарос
        # просрочкой. Чистим целиком: потерять кеш дешевле, чем течь.
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            _cache.clear()
    _cache[login.lower()] = (time.monotonic(), value)


def forget_cached_logins() -> None:
    """Для тестов и ручной отладки."""
    _cache.clear()


@dataclass
class GithubCheck:
    ok: bool
    login: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    error: str | None = None
    # Приняли, но подтвердить не смогли — GitHub не ответил.
    warning: str | None = None


def normalize_login(raw: str | None) -> str:
    # strip после lstrip: люди вставляют «@ anna» из чужого сообщения.
    return (raw or "").strip().lstrip("@").strip()


async def check_github_username(raw: str | None, token: str | None = None) -> GithubCheck:
    login = normalize_login(raw)
    if not login:
        return GithubCheck(ok=False, error="Укажи свой GitHub username")
    if not _LOGIN_RE.match(login):
        return GithubCheck(
            ok=False,
            login=login,
            error="В логине GitHub бывают только латинские буквы, цифры и дефис",
        )

    hit, cached = _cached(login)
    if hit:
        result = cached
    else:
        result = await fetch_github_user(login, token)
        if not isinstance(result, str):
            _remember(login, result)

    if result is None:
        return GithubCheck(ok=False, login=login, error=f"На GitHub нет пользователя {login}")
    if isinstance(result, str):
        # Сеть или лимит. Пропускаем с предупреждением: запирать человека на
        # защите из-за упавшего GitHub нельзя, это цена дороже ошибки в логине.
        return GithubCheck(ok=True, login=login, warning=f"{result}. Логин сохранили как есть")

    return GithubCheck(
        ok=True,
        login=result.get("login") or login,
        name=result.get("name"),
        avatar_url=result.get("avatar_url"),
    )
