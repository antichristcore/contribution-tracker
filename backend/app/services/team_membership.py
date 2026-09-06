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


def known_github_username(db: Session, telegram_user_id: int) -> str | None:
    """GitHub-логин человека, взятый из любого его проекта.

    Логин принадлежит человеку, а не его участию в конкретном проекте: один
    и тот же телеграм — один и тот же GitHub. Без этого приложение спрашивает
    логин заново в каждом проекте, и со стороны это выглядит как «не
    сохранилось».
    """
    row = (
        db.query(GithubMapping.github_username)
        .join(Member, Member.id == GithubMapping.member_id)
        .filter(
            Member.telegram_user_id == telegram_user_id,
            GithubMapping.github_username.isnot(None),
            GithubMapping.github_username != "",
        )
        .order_by(GithubMapping.created_at.desc())
        .first()
    )
    return row[0] if row else None


def team_github_login(db: Session, team_id: int, telegram_user_id: int) -> str | None:
    """Логин участника в конкретном проекте — или None, если он не привязан."""
    member = (
        db.query(Member)
        .filter(Member.team_id == team_id, Member.telegram_user_id == telegram_user_id)
        .first()
    )
    mapping = member.github_mapping if member else None
    return mapping.github_username if mapping else None


def propagate_github_username(db: Session, telegram_user_id: int | None, github_username: str) -> list[int]:
    """Проставляет логин во всех проектах человека, где его ещё нет.

    Возвращает team_id затронутых проектов — по ним нужно пересопоставить
    коммиты. Уже заполненный чужим значением логин не трогаем: человек мог
    сознательно указать другой аккаунт в другом проекте.
    """
    if not telegram_user_id:
        return []

    members = (
        db.query(Member)
        .filter(Member.telegram_user_id == telegram_user_id, Member.is_active.is_(True))
        .all()
    )
    if not members:
        return []

    # Маппинги достаём запросом, а не через member.github_mapping: у уже
    # загруженного объекта связь может быть закеширована как None, и мы
    # добавим вторую строку — а на member_id стоит UNIQUE, то есть сохранение
    # упадёт в 500 ровно на том участнике, которого только что правили.
    existing = {
        m.member_id: m
        for m in db.query(GithubMapping)
        .filter(GithubMapping.member_id.in_([m.id for m in members]))
        .all()
    }

    touched: list[int] = []
    for member in members:
        mapping = existing.get(member.id)
        if mapping and mapping.github_username:
            continue
        if mapping:
            mapping.github_username = github_username
        else:
            # Через связь, а не db.add: иначе member.github_mapping остаётся
            # None в этой же сессии и ответ API выглядит как «не сохранилось».
            member.github_mapping = GithubMapping(
                member_id=member.id, github_username=github_username
            )
        touched.append(member.team_id)
    db.flush()
    return touched


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
    github_username: str | None = None,
) -> tuple[Team, Member]:
    if team_name_taken(db, name):
        raise TeamNameTakenError(name)

    # Логин человек уже вводил в другом проекте — не спрашиваем повторно.
    github_username = github_username or known_github_username(db, telegram_user_id)

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
    db.flush()

    if github_username:
        db.add(GithubMapping(member_id=member.id, github_username=github_username))

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

    github_username = github_username or known_github_username(db, telegram_user_id)

    member = (
        db.query(Member)
        .filter(Member.team_id == team.id, Member.telegram_user_id == telegram_user_id)
        .first()
    )
    if member:
        if not member.is_active:
            member.is_active = True
        # Участник уже был в проекте, но без привязки к GitHub — доставляем её
        # здесь, иначе он навсегда останется «нет данных».
        if github_username and not member.github_mapping:
            db.add(GithubMapping(member_id=member.id, github_username=github_username))
        db.commit()
        db.refresh(member)
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
    """Сохраняет логин и разносит его по остальным проектам человека.

    Через бота проходит тот же путь, что и через приложение, поэтому и правило
    то же: логин принадлежит человеку, а не его участию в одном проекте.
    """
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
        member.github_mapping = mapping
    mapping.github_username = github_username
    db.flush()
    propagate_github_username(db, telegram_user_id, github_username)
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
