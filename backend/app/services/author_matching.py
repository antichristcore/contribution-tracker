"""Сопоставление коммитов и ревью с участниками команды.

Раньше автор определялся только в момент вставки коммита. Если человек
привязывал GitHub-аккаунт после синка — а так и происходит, сначала люди
коммитят, потом заходят в приложение, — его коммиты навсегда оставались
ничьими и в метрики не попадали. Поэтому сопоставление гоняется повторно.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models import Commit, GithubMapping, Member, PrReview


def resolve_member_id(
    db: Session, team_id: int, login: str | None, email: str | None, name: str | None
) -> int | None:
    """Участник команды по данным автора из git. Сравнение регистронезависимое:
    GitHub не различает регистр в логинах, а почту люди пишут как придётся."""
    query = db.query(GithubMapping).join(Member).filter(Member.team_id == team_id)

    for value, column in (
        (login, GithubMapping.github_username),
        (email, GithubMapping.git_author_email),
        (name, GithubMapping.git_author_name),
    ):
        if not value:
            continue
        mapping = query.filter(func.lower(column) == value.lower()).first()
        if mapping:
            return mapping.member_id
    return None


def rematch_unassigned(db: Session, team_id: int) -> int:
    """Проходит по коммитам и ревью без автора и пытается сопоставить снова.

    Возвращает, скольким записям нашёлся владелец.
    """
    matched = 0

    commits = (
        db.query(Commit)
        .filter(Commit.team_id == team_id, Commit.member_id.is_(None))
        .all()
    )
    for commit in commits:
        member_id = resolve_member_id(
            db, team_id, commit.raw_author_login, commit.raw_author_email, commit.raw_author_name
        )
        if member_id is not None:
            commit.member_id = member_id
            matched += 1

    reviews = (
        db.query(PrReview)
        .filter(PrReview.team_id == team_id, PrReview.member_id.is_(None))
        .all()
    )
    for review in reviews:
        member_id = resolve_member_id(db, team_id, review.github_username, None, None)
        if member_id is not None:
            review.member_id = member_id
            matched += 1

    return matched
