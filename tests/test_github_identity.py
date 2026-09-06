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
        async def fake(login):
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

    async def explode(_login):
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
