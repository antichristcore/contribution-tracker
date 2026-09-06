"""Согласование слов с числами.

Уведомления читают живые люди, и «5 дн.» или «1 дней» в сообщении о том, что
у человека что-то не так, звучит небрежно ровно там, где нужна аккуратность.
"""


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (10 <= n % 100 < 20):
        return few
    return many


def days(n: int) -> str:
    return f"{n} {_plural(n, 'день', 'дня', 'дней')}"
