from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.db import get_db
from backend.app.models import Member, SystemRole
from backend.app.security.telegram_auth import verify_init_data

__all__ = ["get_db", "get_current_telegram_user", "get_current_member", "require_teamlead"]


class TelegramUser:
    def __init__(self, telegram_user_id: int, username: str | None, first_name: str | None):
        self.telegram_user_id = telegram_user_id
        self.username = username
        self.first_name = first_name


def get_current_telegram_user(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    x_debug_telegram_user_id: str | None = Header(default=None, alias="X-Debug-Telegram-User-Id"),
    x_debug_member_id: str | None = Header(default=None, alias="X-Debug-Member-Id"),
) -> TelegramUser:
    # Local-dev escape hatch: only active when no real bot token is configured.
    # get_current_member resolves its own debug member directly and ignores
    # this return value in that case — this just has to avoid raising so
    # FastAPI's eager dependency resolution doesn't 401 before that check runs.
    if not settings.BOT_TOKEN and (x_debug_telegram_user_id or x_debug_member_id):
        return TelegramUser(int(x_debug_telegram_user_id or 0), username=None, first_name="Debug")

    if not x_telegram_init_data:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Telegram init data")

    data = verify_init_data(x_telegram_init_data, settings.BOT_TOKEN)
    if not data or not data.get("user"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram init data")

    tg_user = data["user"]
    return TelegramUser(tg_user["id"], tg_user.get("username"), tg_user.get("first_name"))


def get_current_member(
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    x_debug_member_id: str | None = Header(default=None, alias="X-Debug-Member-Id"),
    tg_user: TelegramUser = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
) -> Member:
    # Local-dev escape hatch: only active when no real bot token is configured.
    if not settings.BOT_TOKEN and x_debug_member_id:
        member = db.get(Member, int(x_debug_member_id))
        if member and member.is_active:
            return member

    if not x_team_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing X-Team-Id header")

    member = (
        db.query(Member)
        .filter(
            Member.team_id == int(x_team_id),
            Member.telegram_user_id == tg_user.telegram_user_id,
            Member.is_active.is_(True),
        )
        .first()
    )
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this team")
    return member


def require_teamlead(member: Member = Depends(get_current_member)) -> Member:
    if member.system_role != SystemRole.teamlead:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Teamlead access required")
    return member
