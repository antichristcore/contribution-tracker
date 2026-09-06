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
from dataclasses import dataclass

from backend.app.services.github_client import fetch_github_user

# Правила GitHub: латиница, цифры и дефисы, не в начале и не подряд, до 39 символов.
_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")


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


async def check_github_username(raw: str | None) -> GithubCheck:
    login = normalize_login(raw)
    if not login:
        return GithubCheck(ok=False, error="Укажи свой GitHub username")
    if not _LOGIN_RE.match(login):
        return GithubCheck(
            ok=False,
            login=login,
            error="Так выглядеть логин GitHub не может: только латиница, цифры и дефис",
        )

    result = await fetch_github_user(login)
    if result is None:
        return GithubCheck(ok=False, login=login, error=f"На GitHub нет пользователя {login}")
    if isinstance(result, str):
        # Сеть или лимит. Пропускаем с предупреждением: запирать человека на
        # защите из-за упавшего GitHub нельзя, это цена дороже ошибки в логине.
        return GithubCheck(ok=True, login=login, warning=f"{result} — логин сохранён без проверки")

    return GithubCheck(
        ok=True,
        login=result.get("login") or login,
        name=result.get("name"),
        avatar_url=result.get("avatar_url"),
    )
