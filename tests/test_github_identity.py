"""Проверка GitHub-логина: github_identity.

Логин обязателен для входа в проект, поэтому цена ошибки здесь несимметрична.
Принять несуществующий — человек остаётся «нет данных» и не понимает почему.
Не принять настоящий из-за упавшего GitHub — человек не может войти вообще,
а происходит это ровно тогда, когда сеть плохая, то есть на защите.

pytest-asyncio в проекте нет, поэтому корутины гоняются через asyncio.run():
одна зависимость ради четырёх тестов не окупается.
"""

import asyncio

import pytest

from backend.app.services import github_identity
from backend.app.services.github_identity import check_github_username, normalize_login


@pytest.fixture
def github(monkeypatch):
    """Подменяет обращение к GitHub. Значение: dict — пользователь есть,
    None — нет такого, str — проверить не удалось."""

    def _set(result):
        async def fake(login, token=None):
            return result

        monkeypatch.setattr(github_identity, "fetch_github_user", fake)

    return _set


def check(login):
    return asyncio.run(check_github_username(login))


@pytest.mark.parametrize(
    "raw, expected",
    [("  anna ", "anna"), ("@anna", "anna"), ("@ anna", "anna"), (None, ""), ("", "")],
)
def test_normalize_login(raw, expected):
    assert normalize_login(raw) == expected


@pytest.mark.parametrize(
    "login, case",
    [
        ("", "пусто"),
        ("-anna", "дефис в начале"),
        ("anna--volkova", "два дефиса подряд"),
        ("anna-", "дефис в конце"),
        ("анна", "кириллица"),
        ("anna volkova", "пробел"),
        ("a" * 40, "длиннее 39 символов"),
    ],
)
def test_impossible_logins_are_rejected_without_asking_github(login, case, github):
    """Заведомо невалидное отсекается до сетевого запроса."""

    async def explode(_login, token=None):
        raise AssertionError("не должно доходить до GitHub")

    github(None)
    github_identity.fetch_github_user = explode  # переопределяем поверх фикстуры

    result = check(login)

    assert result.ok is False, case
    assert result.error


def test_existing_user_is_accepted_with_profile(github):
    github({"login": "AnnaVolkova", "name": "Anna Volkova", "avatar_url": "https://x/a.png"})

    result = check("@annavolkova")

    assert result.ok is True
    # Логин берём из ответа GitHub: он знает настоящий регистр.
    assert result.login == "AnnaVolkova"
    assert result.name == "Anna Volkova"
    assert result.warning is None


def test_unknown_user_is_rejected(github):
    github(None)

    result = check("nosuchuser")

    assert result.ok is False
    assert "nosuchuser" in result.error


def test_unreachable_github_lets_the_person_through(github):
    """Главное правило: упавший GitHub не должен запирать людей на защите.
    Логин принимается, но об этом честно написано."""
    github("GitHub недоступен")

    result = check("anna")

    assert result.ok is True
    assert result.login == "anna"
    assert result.warning


# --- кеш ---------------------------------------------------------------------


def test_repeated_check_does_not_ask_github_again(monkeypatch):
    """Анонимный лимит GitHub — 60 запросов в час на IP, а через туннель он один
    на всю команду. Форма проверяет логин на каждую паузу в наборе, поэтому
    один и тот же логин обязан спрашиваться ровно однажды."""
    calls = []

    async def counting(login, token=None):
        calls.append(login)
        return {"login": login, "name": None, "avatar_url": None}

    monkeypatch.setattr(github_identity, "fetch_github_user", counting)

    assert check("anna").ok is True
    assert check("anna").ok is True
    assert check("ANNA").ok is True  # регистр не должен плодить запросы

    assert calls == ["anna"]


def test_failed_check_is_not_cached(monkeypatch):
    """Временный сбой кешировать нельзя: иначе он залипнет на четверть часа
    и человек будет видеть «сохранено без проверки» после того, как всё уже
    починилось."""
    outcomes = ["GitHub ограничил число проверок", {"login": "anna", "name": None, "avatar_url": None}]

    async def flaky(login, token=None):
        return outcomes.pop(0)

    monkeypatch.setattr(github_identity, "fetch_github_user", flaky)

    first = check("anna")
    assert first.ok is True and first.warning

    second = check("anna")
    assert second.ok is True and second.warning is None


def test_rate_limit_is_reported_in_human_words(github):
    """403 от GitHub на публичном профиле — это лимит, а не запрет доступа.
    Человеку показываем причину, а не код ответа."""
    github("GitHub ограничил число проверок")

    result = check("anna")

    assert result.ok is True
    assert "ограничил" in result.warning


# --- сам запрос к GitHub -----------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def json(self):
        return {"login": "anna", "name": None, "avatar_url": None}


@pytest.fixture
def github_http(monkeypatch):
    """Подменяет httpx на уровне запроса: так проверяется разбор ответа GitHub,
    который заглушка fetch_github_user перепрыгивает. Возвращает список
    заголовков всех сделанных запросов."""
    sent_headers = []

    def _set(status_code: int):
        class _FakeClient:
            def __init__(self, *_args, headers=None, **_kwargs):
                self._headers = headers or {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def get(self, _url):
                sent_headers.append(self._headers)
                return _FakeResponse(status_code)

        monkeypatch.setattr(github_client.httpx, "AsyncClient", _FakeClient)
        return sent_headers

    return _set


def test_rate_limited_response_is_not_mistaken_for_a_missing_user(github_http):
    """403 нельзя прочитать как «такого логина нет»: настоящий логин иначе
    отклоняется, и человек не может войти в проект."""
    github_http(403)

    result = asyncio.run(github_client.fetch_github_user("anna"))

    assert isinstance(result, str)
    assert "ограничил" in result


def test_team_token_is_sent_but_a_placeholder_one_is_not(github_http):
    """Токен команды поднимает лимит с 60 до 5000. А вот огрызок из
    .env.example отправлять нельзя: GitHub ответит 401 на запрос, который
    анонимно прошёл бы, и проверка логина молча станет «сохранили как есть»."""
    sent = github_http(200)

    asyncio.run(github_client.fetch_github_user("anna", "ghp_" + "x" * 36))
    asyncio.run(github_client.fetch_github_user("anna", "ghp_xxx"))

    assert sent[0]["Authorization"].startswith("Bearer ghp_")
    assert "Authorization" not in sent[1]
