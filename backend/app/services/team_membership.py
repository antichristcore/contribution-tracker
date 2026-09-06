from sqlalchemy.orm import Session

from backend.app.models import (
    Commit,
    GithubMapping,
    Member,
    NotificationLog,
    PrReview,
    ScoreHistory,
    SystemRole,
    Task,
    TaskStatusHistory,
    Team,
)
from backend.app.services.invite_codes import generate_unique_invite_code


class TeamNameTakenError(Exception):
    pass


def team_name_taken(db: Session, name: str) -> bool:
    return db.query(Team).filter(Team.name.ilike(name.strip())).first() is not None


def list_member_teams(db: Session, telegram_user_id: int) -> list[tuple[Member, Team]]:
    return (
        db.query(Member, Team)
        .join(Team, Team.id == Member.team_id)
        .filter(Member.telegram_user_id == telegram_user_id, Member.is_active.is_(True))
        .all()
    )


def create_team(
    db: Session,
    name: str,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    github_owner: str | None = None,
    github_repo: str | None = None,
    github_token: str | None = None,
) -> tuple[Team, Member]:
    if team_name_taken(db, name):
        raise TeamNameTakenError(name)

    team = Team(
        name=name,
        invite_code=generate_unique_invite_code(db),
        github_owner=github_owner,
        github_repo=github_repo,
        github_token=github_token,
    )
    db.add(team)
    db.flush()

    member = Member(
        team_id=team.id,
        display_name=first_name or username or f"user_{telegram_user_id}",
        role_in_team="teamlead",
        system_role=SystemRole.teamlead,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )
    db.add(member)
    db.commit()
    db.refresh(team)
    db.refresh(member)
    return team, member


def join_team_by_code(
    db: Session,
    invite_code: str,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    role_in_team: str = "member",
    github_username: str | None = None,
) -> tuple[Team, Member] | None:
    team = db.query(Team).filter(Team.invite_code == invite_code.strip().upper()).first()
    if not team:
        return None

    member = (
        db.query(Member)
        .filter(Member.team_id == team.id, Member.telegram_user_id == telegram_user_id)
        .first()
    )
    if member:
        if not member.is_active:
            member.is_active = True
            db.commit()
        return team, member

    member = Member(
        team_id=team.id,
        display_name=first_name or username or f"user_{telegram_user_id}",
        role_in_team=role_in_team,
        system_role=SystemRole.member,
        telegram_user_id=telegram_user_id,
        telegram_username=username,
    )
    db.add(member)
    db.flush()

    if github_username:
        db.add(GithubMapping(member_id=member.id, github_username=github_username))

    db.commit()
    db.refresh(member)
    return team, member


def set_github_username(db: Session, team_id: int, telegram_user_id: int, github_username: str) -> bool:
    member = (
        db.query(Member)
        .filter(Member.team_id == team_id, Member.telegram_user_id == telegram_user_id)
        .first()
    )
    if not member:
        return False

    mapping = member.github_mapping
    if not mapping:
        mapping = GithubMapping(member_id=member.id)
        db.add(mapping)
    mapping.github_username = github_username
    db.commit()
    return True


def delete_team(db: Session, team_id: int) -> None:
    member_ids = [row[0] for row in db.query(Member.id).filter(Member.team_id == team_id).all()]
    task_ids = [row[0] for row in db.query(Task.id).filter(Task.team_id == team_id).all()]

    if member_ids:
        db.query(NotificationLog).filter(NotificationLog.member_id.in_(member_ids)).delete(synchronize_session=False)
        db.query(GithubMapping).filter(GithubMapping.member_id.in_(member_ids)).delete(synchronize_session=False)
    if task_ids:
        db.query(TaskStatusHistory).filter(TaskStatusHistory.task_id.in_(task_ids)).delete(synchronize_session=False)

    db.query(Task).filter(Task.team_id == team_id).delete(synchronize_session=False)
    db.query(ScoreHistory).filter(ScoreHistory.team_id == team_id).delete(synchronize_session=False)
    db.query(PrReview).filter(PrReview.team_id == team_id).delete(synchronize_session=False)
    db.query(Commit).filter(Commit.team_id == team_id).delete(synchronize_session=False)
    db.query(Member).filter(Member.team_id == team_id).delete(synchronize_session=False)
    db.query(Team).filter(Team.id == team_id).delete(synchronize_session=False)
    db.commit()
