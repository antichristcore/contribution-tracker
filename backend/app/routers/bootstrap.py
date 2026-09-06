"""Everything the app needs to paint its first screen, in one request.

Opening the Mini App used to cost four sequential round trips
(index.html -> /me/teams -> /me -> /tasks). Over a tunnel that's ~1.7s of
pure latency before anything appears, which is most of the perceived
slowness. The data was never the problem — the number of trips was.
"""

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.deps import TelegramUser, get_current_telegram_user, get_db
from backend.app.models import Member, SystemRole, Task
from backend.app.schemas import MemberOut, TaskOut
from backend.app.services.task_utils import task_to_out
from backend.app.services.team_membership import known_github_username, list_member_teams

router = APIRouter(prefix="/api", tags=["bootstrap"])


class BootstrapTeam(BaseModel):
    team_id: int
    name: str
    role_in_team: str
    system_role: SystemRole


class BootstrapOut(BaseModel):
    teams: list[BootstrapTeam]
    # Set once a team is resolved; the client then skips /me and /tasks.
    team_id: int | None = None
    member: MemberOut | None = None
    tasks: list[TaskOut] | None = None
    # Участник уже в проекте, но без привязки к GitHub — доска ему бесполезна,
    # пока клиент не соберёт логин. Флаг отдаётся тем же запросом, чтобы
    # блокирующий экран не стоил лишнего round-trip.
    needs_github_username: bool = False
    # Логин, который человек уже вводил в другом проекте: форма создания
    # проекта подставляет его, чтобы не спрашивать одно и то же дважды.
    known_github_username: str | None = None


@router.get("/bootstrap", response_model=BootstrapOut)
def bootstrap(
    team_id: int | None = None,
    x_debug_member_id: str | None = Header(default=None, alias="X-Debug-Member-Id"),
    tg_user: TelegramUser = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
) -> BootstrapOut:
    pairs = _member_teams(db, tg_user, x_debug_member_id)
    known_login = (
        known_github_username(db, tg_user.telegram_user_id) if tg_user.telegram_user_id else None
    )

    teams = [
        BootstrapTeam(
            team_id=member.team_id,
            name=team.name,
            role_in_team=member.role_in_team,
            system_role=member.system_role,
        )
        for member, team in pairs
    ]

    # Resolve the requested team; fall back to the only one when there is no
    # ambiguity, so the common single-team case is also a single round trip.
    current = next((m for m, _ in pairs if m.team_id == team_id), None)
    if current is None and len(pairs) == 1:
        current = pairs[0][0]

    if current is None:
        return BootstrapOut(teams=teams, known_github_username=known_login)

    tasks = (
        db.query(Task)
        .filter(Task.team_id == current.team_id)
        .order_by(Task.created_at.desc())
        .all()
    )
    mapping = current.github_mapping
    return BootstrapOut(
        teams=teams,
        team_id=current.team_id,
        member=MemberOut.model_validate(current),
        tasks=[task_to_out(db, t) for t in tasks],
        needs_github_username=not (mapping and mapping.github_username),
        known_github_username=known_login,
    )


def _member_teams(db: Session, tg_user: TelegramUser, debug_member_id: str | None):
    # Same local-dev escape hatch as deps.get_current_member: only active when
    # no real bot token is configured, so it can never be reached in the
    # deployment the bot is actually running against.
    if not settings.BOT_TOKEN and debug_member_id:
        member = db.get(Member, int(debug_member_id))
        if member and member.is_active and member.team:
            return [(member, member.team)]
        return []
    return list_member_teams(db, tg_user.telegram_user_id)
