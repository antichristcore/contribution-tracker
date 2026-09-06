from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.bot.bot_instance import bot
from backend.app.deps import TelegramUser, get_current_telegram_user, get_db, require_teamlead
from backend.app.models import Member, SystemRole, Team
from backend.app.services.team_membership import (
    TeamNameTakenError,
    create_team,
    delete_team,
    join_team_by_code,
    list_member_teams,
    team_name_taken,
)

router = APIRouter(tags=["teams"])

_bot_username_cache: str | None = None


async def _get_bot_username() -> str | None:
    global _bot_username_cache
    if _bot_username_cache is None and bot is not None:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache


class MyTeamOut(BaseModel):
    team_id: int
    name: str
    role_in_team: str
    system_role: SystemRole


class TeamCreate(BaseModel):
    name: str
    github_owner: str | None = None
    github_repo: str | None = None


class TeamOut(BaseModel):
    team_id: int
    name: str
    member_id: int


class TeamJoin(BaseModel):
    invite_code: str
    role_in_team: str = "member"
    github_username: str | None = None


class InviteOut(BaseModel):
    invite_code: str
    bot_username: str | None
    deep_link: str | None


class TeamSettingsOut(BaseModel):
    team_id: int
    name: str
    github_owner: str | None
    github_repo: str | None
    has_github_token: bool


class TeamSettingsUpdate(BaseModel):
    name: str | None = None
    github_owner: str | None = None
    github_repo: str | None = None
    github_token: str | None = None


@router.get("/api/me/teams", response_model=list[MyTeamOut])
def get_my_teams(
    tg_user: TelegramUser = Depends(get_current_telegram_user), db: Session = Depends(get_db)
) -> list[MyTeamOut]:
    return [
        MyTeamOut(team_id=team.id, name=team.name, role_in_team=member.role_in_team, system_role=member.system_role)
        for member, team in list_member_teams(db, tg_user.telegram_user_id)
    ]


@router.post("/api/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def api_create_team(
    payload: TeamCreate,
    tg_user: TelegramUser = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
) -> TeamOut:
    try:
        team, member = create_team(
            db,
            payload.name,
            tg_user.telegram_user_id,
            tg_user.username,
            tg_user.first_name,
            github_owner=payload.github_owner,
            github_repo=payload.github_repo,
        )
    except TeamNameTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Проект с таким названием уже существует, выбери другое")
    return TeamOut(team_id=team.id, name=team.name, member_id=member.id)


@router.post("/api/teams/join", response_model=TeamOut)
def api_join_team(
    payload: TeamJoin,
    tg_user: TelegramUser = Depends(get_current_telegram_user),
    db: Session = Depends(get_db),
) -> TeamOut:
    result = join_team_by_code(
        db,
        payload.invite_code,
        tg_user.telegram_user_id,
        tg_user.username,
        tg_user.first_name,
        payload.role_in_team,
        github_username=payload.github_username,
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Неверный код приглашения")
    team, member = result
    return TeamOut(team_id=team.id, name=team.name, member_id=member.id)


@router.get("/api/teams/{team_id}/invite", response_model=InviteOut)
async def get_invite(team_id: int, db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)) -> InviteOut:
    if teamlead.team_id != team_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")

    username = await _get_bot_username()
    deep_link = f"https://t.me/{username}?start={team.invite_code}" if username else None
    return InviteOut(invite_code=team.invite_code, bot_username=username, deep_link=deep_link)


@router.get("/api/teams/{team_id}/settings", response_model=TeamSettingsOut)
def get_team_settings(
    team_id: int, db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)
) -> TeamSettingsOut:
    if teamlead.team_id != team_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return TeamSettingsOut(
        team_id=team.id,
        name=team.name,
        github_owner=team.github_owner,
        github_repo=team.github_repo,
        has_github_token=bool(team.github_token),
    )


@router.patch("/api/teams/{team_id}/settings", response_model=TeamSettingsOut)
def update_team_settings(
    team_id: int,
    payload: TeamSettingsUpdate,
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> TeamSettingsOut:
    if teamlead.team_id != team_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")

    if payload.name is not None and payload.name.strip():
        new_name = payload.name.strip()
        if new_name.lower() != team.name.lower() and team_name_taken(db, new_name):
            raise HTTPException(status.HTTP_409_CONFLICT, "Проект с таким названием уже существует, выбери другое")
        team.name = new_name
    if payload.github_owner is not None:
        team.github_owner = payload.github_owner.strip() or None
    if payload.github_repo is not None:
        team.github_repo = payload.github_repo.strip() or None
    if payload.github_token is not None:
        team.github_token = payload.github_token.strip() or None

    db.commit()
    db.refresh(team)
    return TeamSettingsOut(
        team_id=team.id,
        name=team.name,
        github_owner=team.github_owner,
        github_repo=team.github_repo,
        has_github_token=bool(team.github_token),
    )


@router.delete("/api/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_team(
    team_id: int, db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)
) -> None:
    if teamlead.team_id != team_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    delete_team(db, team_id)
