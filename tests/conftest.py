"""Общие фикстуры и фабрики для тестов.

Каждый тест получает пустую SQLite в памяти — рабочая база `data/app.db`
не трогается вообще. Все датировки считаются от фиксированного момента `NOW`,
чтобы тесты не зависели от реального времени запуска.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base
from backend.app.services.task_numbers import next_task_number
from backend.app.models import (
    Commit,
    GithubMapping,
    Member,
    PrReview,
    ScoreHistory,
    SystemRole,
    Task,
    TaskStatus,
    TaskStatusHistory,
    Team,
)

# Точка отсчёта для всех "N дней назад". Полдень — чтобы арифметика по суткам
# не прыгала через границу дня.
NOW = datetime(2026, 3, 15, 12, 0, 0)


@pytest.fixture(autouse=True)
def clear_github_cache():
    """Проверки логинов кешируются на 15 минут в памяти процесса. Между
    тестами кеш надо чистить, иначе заглушка одного теста отвечает за другой."""
    from backend.app.services.github_identity import forget_cached_logins

    forget_cached_logins()
    yield
    forget_cached_logins()


@pytest.fixture
def db():
    """Изолированная база в памяти. StaticPool — чтобы все сессии видели
    одно и то же соединение (иначе :memory: создаётся заново на каждый коннект)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def team(db):
    return make_team(db, name="Тестовая команда")


# --- фабрики -----------------------------------------------------------------


def make_team(db, name="Команда", code=None):
    t = Team(name=name, invite_code=code or uuid4().hex[:8].upper())
    db.add(t)
    db.commit()
    return t


def make_member(
    db,
    team,
    name="Участник",
    role="backend",
    system_role=SystemRole.member,
    with_github=True,
):
    m = Member(
        team_id=team.id,
        display_name=name,
        role_in_team=role,
        system_role=system_role,
    )
    db.add(m)
    db.commit()
    if with_github:
        db.add(GithubMapping(member_id=m.id, github_username=name.lower()))
        db.commit()
        # refresh сбрасывает и загруженные связи — иначе has_data увидит None.
        db.refresh(m)
    return m


def make_commit(
    db,
    team,
    member,
    days_ago=0,
    additions=50,
    deletions=10,
    message=None,
    task=None,
):
    c = Commit(
        team_id=team.id,
        member_id=member.id,
        task_id=task.id if task else None,
        sha=uuid4().hex,
        authored_at=NOW - timedelta(days=days_ago),
        additions=additions,
        deletions=deletions,
        stats_fetched=True,
        message=message,
    )
    db.add(c)
    db.commit()
    return c


def make_task(
    db,
    team,
    assignee=None,
    status=TaskStatus.todo,
    title="Задача",
    created_days_ago=30,
    status_changed_days_ago=0,
    deadline_days_ago=None,
    completed_days_ago=None,
):
    t = Task(
        team_id=team.id,
        number=next_task_number(db, team.id),
        title=title,
        assignee_member_id=assignee.id if assignee else None,
        status=status,
        created_at=NOW - timedelta(days=created_days_ago),
        status_changed_at=NOW - timedelta(days=status_changed_days_ago),
        deadline_at=None if deadline_days_ago is None else NOW - timedelta(days=deadline_days_ago),
        completed_at=None if completed_days_ago is None else NOW - timedelta(days=completed_days_ago),
    )
    db.add(t)
    db.commit()
    return t


def make_status_change(db, task, member, days_ago=0, new_status=TaskStatus.in_progress):
    h = TaskStatusHistory(
        task_id=task.id,
        old_status=TaskStatus.todo,
        new_status=new_status,
        changed_at=NOW - timedelta(days=days_ago),
        changed_by_member_id=member.id,
    )
    db.add(h)
    db.commit()
    return h


def make_pr_review(db, team, member, days_ago=0, pr_number=1):
    r = PrReview(
        team_id=team.id,
        member_id=member.id,
        github_username=member.display_name.lower(),
        pr_number=pr_number,
        review_id=int(uuid4().int % 10**9),
        submitted_at=NOW - timedelta(days=days_ago),
        state="COMMENTED",
    )
    db.add(r)
    db.commit()
    return r


def make_score_row(
    db,
    team,
    member,
    days_ago,
    score,
    *,
    has_data=True,
    stuck_days=0,
    last_activity_days_ago=0,
    tasks_assigned=0,
    tasks_completed_on_time=0,
):
    row = ScoreHistory(
        team_id=team.id,
        member_id=member.id,
        computed_at=NOW - timedelta(days=days_ago),
        contribution_score=score,
        tasks_status_stuck_days_max=stuck_days,
        last_activity_days_ago=last_activity_days_ago,
        tasks_assigned=tasks_assigned,
        tasks_completed_on_time=tasks_completed_on_time,
        has_data=has_data,
    )
    db.add(row)
    db.commit()
    return row


def raw_metrics(**overrides):
    """Готовый словарь метрик для чистых функций — без похода в базу."""
    base = {
        "commits_count_7d": 0,
        "commits_lines_changed_7d": 0,
        "active_days_14d": 0,
        "tasks_assigned": 0,
        "tasks_deadline_eligible": 0,
        "tasks_completed_on_time": 0,
        "tasks_status_stuck_days_max": 0,
        "pr_review_comments_given": 0,
        "last_activity_days_ago": 0,
        "has_data": True,
    }
    base.update(overrides)
    return base
