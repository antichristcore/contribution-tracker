"""Rich, fully local synthetic demo dataset — no GitHub push, no real
Telegram accounts needed. Resets and repopulates the "Демо-команда" team
with 8 members across 4 activity profiles (steady / falling / recovering /
sporadic), a variety of tasks, and a full 21-day score_history backfill so
the score charts and "До/После" screen have real, varied data to explore
instead of a single flat point.

Only ever touches the team named DEMO_TEAM_NAME — never the user's own
real teams.

Usage:
    python scripts/seed_synthetic_demo.py
"""

import asyncio
import hashlib
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db import Base, SessionLocal, engine  # noqa: E402
from backend.app.models import (  # noqa: E402
    Commit,
    GithubMapping,
    Member,
    NotificationLog,
    PrReview,
    ScoreHistory,
    SystemRole,
    Task,
    TaskStatus,
    TaskStatusHistory,
    Team,
)
from backend.app.services.invite_codes import generate_unique_invite_code  # noqa: E402
from backend.app.services.recalc import recalculate_team_scores  # noqa: E402
from backend.app.services.task_numbers import next_task_number  # noqa: E402
from backend.app.utils.time import utcnow  # noqa: E402

DEMO_TEAM_NAME = "Демо-команда"
WINDOW_DAYS = 21
SEED = 7

MEMBERS = [
    {"name": "Anna Volkova", "email": "anna.volkova@demo.local", "role": "backend", "profile": "steady"},
    {"name": "Boris Titov", "email": "boris.titov@demo.local", "role": "frontend", "profile": "steady"},
    {"name": "Vera Sokolova", "email": "vera.sokolova@demo.local", "role": "design", "profile": "steady"},
    {"name": "Ivan Kuznetsov", "email": "ivan.kuznetsov@demo.local", "role": "backend", "profile": "steady"},
    {"name": "Denis Orlov", "email": "denis.orlov@demo.local", "role": "backend", "profile": "falling"},
    {"name": "Egor Panin", "email": "egor.panin@demo.local", "role": "qa", "profile": "falling"},
    {"name": "Olga Sidorova", "email": "olga.sidorova@demo.local", "role": "frontend", "profile": "recovering"},
    {"name": "Pavel Titov", "email": "pavel.titov@demo.local", "role": "qa", "profile": "sporadic"},
]

# No "#N" in these: a bare "#N" is the task-reference syntax, so generic
# background commits must not look like they belong to a task.
ROLE_MESSAGES = {
    "backend": ["Add endpoint handler {n}", "Fix edge case in service layer {n}", "Refactor DB query {n}"],
    "frontend": ["Add component {n}", "Fix layout bug in view {n}", "Wire up API call {n}"],
    "design": ["Update mockup {n}", "Add spacing tokens {n}", "Iterate on card layout {n}"],
    "qa": ["Add test case {n}", "Fix flaky test {n}", "Extend coverage for module {n}"],
}

# Tasks whose commits deliberately do NOT mention the task number — they show
# up in "Привязать коммиты" so the manual fallback has something to demo.
UNREFERENCED_TASK_TITLES = {"Fix responsive layout bugs", "Write regression checklist"}

TASK_COMMIT_MESSAGES = [
    "Draft implementation for {title} #{id}",
    "Handle edge cases in {title} #{id}",
    "Address review notes on {title} #{id}",
    "Polish {title} #{id}",
]


def commits_for_day(profile: str, week_index: int, rng: random.Random) -> int:
    if profile == "steady":
        return 0 if rng.random() < 0.15 else rng.choice([1, 1, 2])
    if profile == "falling":
        if week_index == 0:
            return 0 if rng.random() < 0.15 else rng.choice([1, 1, 2])
        return 0 if rng.random() < 0.85 else 1
    if profile == "recovering":
        if week_index == 0:
            return 0 if rng.random() < 0.2 else rng.choice([1, 1, 2])
        if week_index == 1:
            return 0 if rng.random() < 0.8 else 1
        return 0 if rng.random() < 0.1 else rng.choice([1, 2])  # bounces back hard in the final week
    if profile == "sporadic":
        return 0 if rng.random() < 0.55 else 1
    raise ValueError(profile)


def get_or_reset_team(db) -> Team:
    team = db.query(Team).filter(Team.name == DEMO_TEAM_NAME).first()
    if team:
        member_ids = [m.id for m in db.query(Member).filter(Member.team_id == team.id).all()]
        if member_ids:
            db.query(NotificationLog).filter(NotificationLog.member_id.in_(member_ids)).delete(synchronize_session=False)
            db.query(GithubMapping).filter(GithubMapping.member_id.in_(member_ids)).delete(synchronize_session=False)
        task_ids = [t.id for t in db.query(Task).filter(Task.team_id == team.id).all()]
        if task_ids:
            db.query(TaskStatusHistory).filter(TaskStatusHistory.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(Task).filter(Task.team_id == team.id).delete(synchronize_session=False)
        db.query(ScoreHistory).filter(ScoreHistory.team_id == team.id).delete(synchronize_session=False)
        db.query(PrReview).filter(PrReview.team_id == team.id).delete(synchronize_session=False)
        db.query(Commit).filter(Commit.team_id == team.id).delete(synchronize_session=False)
        db.query(Member).filter(Member.team_id == team.id, Member.system_role != SystemRole.teamlead).delete(
            synchronize_session=False
        )
        db.commit()
    else:
        team = Team(name=DEMO_TEAM_NAME, invite_code=generate_unique_invite_code(db))
        db.add(team)
        db.commit()
        db.refresh(team)

    if not db.query(Member).filter(Member.team_id == team.id, Member.system_role == SystemRole.teamlead).first():
        db.add(Member(team_id=team.id, display_name="Тимлид", role_in_team="teamlead", system_role=SystemRole.teamlead))
        db.commit()

    return team


def seed_members(db, team: Team) -> dict[str, Member]:
    members = {}
    for cfg in MEMBERS:
        member = Member(team_id=team.id, display_name=cfg["name"], role_in_team=cfg["role"], system_role=SystemRole.member)
        db.add(member)
        db.flush()
        db.add(GithubMapping(member_id=member.id, git_author_email=cfg["email"], git_author_name=cfg["name"]))
        members[cfg["name"]] = member
    db.commit()
    return members


def seed_commits_and_reviews(db, team: Team, members: dict[str, Member], rng: random.Random, start_date) -> None:
    counters = {name: 0 for name in members}
    review_id = 900_000

    for offset in range(WINDOW_DAYS):
        day = start_date + timedelta(days=offset)
        week_index = offset // 7
        for cfg in MEMBERS:
            member = members[cfg["name"]]
            n = commits_for_day(cfg["profile"], week_index, rng)
            for _ in range(n):
                counters[cfg["name"]] += 1
                idx = counters[cfg["name"]]
                hour, minute = rng.randint(9, 19), rng.randint(0, 59)
                authored_at = day.replace(hour=hour, minute=minute, second=rng.randint(0, 59))
                message = rng.choice(ROLE_MESSAGES[cfg["role"]]).format(n=idx)
                sha = hashlib.sha1(f"{cfg['email']}-{offset}-{idx}".encode()).hexdigest()
                db.add(
                    Commit(
                        team_id=team.id,
                        member_id=member.id,
                        sha=sha,
                        raw_author_login=None,
                        raw_author_email=cfg["email"],
                        raw_author_name=cfg["name"],
                        message=message,
                        authored_at=authored_at,
                        additions=rng.randint(5, 120),
                        deletions=rng.randint(0, 40),
                        stats_fetched=True,
                    )
                )
            # steady members occasionally review each other's work
            if cfg["profile"] == "steady" and rng.random() < 0.12:
                review_id += 1
                db.add(
                    PrReview(
                        team_id=team.id,
                        member_id=member.id,
                        github_username=cfg["email"],
                        pr_number=rng.randint(1, 60),
                        review_id=review_id,
                        submitted_at=day.replace(hour=rng.randint(9, 19)),
                        state="APPROVED",
                    )
                )
    db.commit()


def add_task(db, team, teamlead, assignee, title, status, deadline_days_from_now, status_changed_days_ago, completed_days_ago=None) -> Task:
    now = utcnow()
    task = Task(
        team_id=team.id,
        number=next_task_number(db, team.id),
        title=title,
        assignee_member_id=assignee.id,
        created_by_member_id=teamlead.id,
        status=status,
        deadline_at=now + timedelta(days=deadline_days_from_now),
        status_changed_at=now - timedelta(days=status_changed_days_ago),
        completed_at=(now - timedelta(days=completed_days_ago)) if completed_days_ago is not None else None,
        created_at=now - timedelta(days=max(status_changed_days_ago, 1) + 2),
    )
    db.add(task)
    db.flush()
    db.add(TaskStatusHistory(task_id=task.id, old_status=None, new_status=TaskStatus.todo, changed_by_member_id=teamlead.id))
    if status == TaskStatus.in_progress:
        db.add(TaskStatusHistory(task_id=task.id, old_status=TaskStatus.todo, new_status=status,
                                 changed_at=task.status_changed_at, changed_by_member_id=None))
    if status == TaskStatus.done:
        # Закрытие руками — единственный путь к «готово», и на демо это должно
        # быть видно в истории задачи: с именем человека, а не «автоматически».
        db.add(TaskStatusHistory(task_id=task.id, old_status=TaskStatus.in_progress, new_status=status,
                                 changed_at=task.completed_at, changed_by_member_id=task.assignee_member_id))
    return task


def seed_task_commits(db, team: Team, tasks: list[Task], members: dict[str, Member], rng: random.Random) -> None:
    """Commits that actually belong to a task: referencing #<id> for most of
    them, and a couple of deliberately unreferenced ones so the manual
    "привязать коммиты" flow has something to show."""
    cfg_by_member_id = {members[cfg["name"]].id: cfg for cfg in MEMBERS}

    for task in tasks:
        if task.status == TaskStatus.todo or not task.assignee_member_id:
            continue  # a linked commit would have moved it out of "todo"
        cfg = cfg_by_member_id.get(task.assignee_member_id)
        if not cfg:
            continue

        anchor = task.completed_at if task.status == TaskStatus.done else task.status_changed_at
        span_days = max((anchor - task.created_at).days, 1)
        short_title = task.title.lower()
        unreferenced = task.title in UNREFERENCED_TASK_TITLES
        count = rng.randint(2, 4)

        for i in range(count):
            is_last = i == count - 1
            # Oldest first, newest exactly at the task's last-activity anchor,
            # so "N дн. без изменений" on the board matches the commit history.
            offset_days = 0 if is_last else rng.randint(1, span_days)
            authored_at = anchor - timedelta(days=offset_days, hours=rng.randint(0, 6))
            authored_at = max(authored_at, task.created_at + timedelta(hours=1))

            if unreferenced:
                message = f"Work on {short_title}"
            elif is_last and task.status == TaskStatus.done:
                # Без «closes»: коммит задачу не закрывает, её закрывает человек.
                message = f"Wrap up {short_title} #{task.number}"
            else:
                message = rng.choice(TASK_COMMIT_MESSAGES).format(title=short_title, id=task.number)

            db.add(
                Commit(
                    team_id=team.id,
                    member_id=task.assignee_member_id,
                    task_id=None if unreferenced else task.id,
                    sha=hashlib.sha1(f"task-{task.id}-{i}".encode()).hexdigest(),
                    raw_author_login=None,
                    raw_author_email=cfg["email"],
                    raw_author_name=cfg["name"],
                    message=message,
                    authored_at=authored_at,
                    additions=rng.randint(10, 180),
                    deletions=rng.randint(0, 60),
                    stats_fetched=True,
                )
            )
    db.commit()


def seed_tasks(db, team, teamlead, members: dict[str, Member]) -> list[Task]:
    anna, boris, vera, ivan = members["Anna Volkova"], members["Boris Titov"], members["Vera Sokolova"], members["Ivan Kuznetsov"]
    denis, egor = members["Denis Orlov"], members["Egor Panin"]
    olga, pavel = members["Olga Sidorova"], members["Pavel Titov"]

    tasks = [
        add_task(db, team, teamlead, anna, "Design auth schema", TaskStatus.done, -5, 6, completed_days_ago=6),
        add_task(db, team, teamlead, anna, "Implement /api/tasks CRUD", TaskStatus.done, -2, 3, completed_days_ago=3),
        add_task(db, team, teamlead, anna, "Add GitHub sync job", TaskStatus.in_progress, 3, 1),

        add_task(db, team, teamlead, boris, "Build dashboard skeleton", TaskStatus.done, -4, 5, completed_days_ago=5),
        add_task(db, team, teamlead, boris, "Wire up score chart", TaskStatus.done, -1, 2, completed_days_ago=2),
        add_task(db, team, teamlead, boris, "Polish member detail view", TaskStatus.in_progress, 4, 1),

        add_task(db, team, teamlead, vera, "Design member card states", TaskStatus.done, -3, 4, completed_days_ago=4),
        add_task(db, team, teamlead, vera, "Design before/after screen", TaskStatus.todo, 5, 1),

        add_task(db, team, teamlead, ivan, "Set up CI pipeline", TaskStatus.done, -6, 7, completed_days_ago=7),
        add_task(db, team, teamlead, ivan, "Add rate limiting", TaskStatus.in_progress, 6, 2),

        add_task(db, team, teamlead, denis, "Refactor scoring service", TaskStatus.in_progress, -6, 9),
        add_task(db, team, teamlead, denis, "Add rate-limit handling to GitHub client", TaskStatus.todo, -2, 10),
        add_task(db, team, teamlead, denis, "Write DB migration notes", TaskStatus.done, -12, 13, completed_days_ago=13),

        add_task(db, team, teamlead, egor, "Write E2E test plan", TaskStatus.in_progress, -4, 8),
        add_task(db, team, teamlead, egor, "Automate task status regression tests", TaskStatus.in_progress, -1, 11),
        add_task(db, team, teamlead, egor, "Set up test data fixtures", TaskStatus.done, -14, 15, completed_days_ago=15),

        # Olga: was stuck, then recovered — task got unstuck and finished recently.
        add_task(db, team, teamlead, olga, "Redesign onboarding flow", TaskStatus.done, -1, 2, completed_days_ago=2),
        add_task(db, team, teamlead, olga, "Fix responsive layout bugs", TaskStatus.in_progress, 5, 1),

        # Pavel: moving, but slowly — moderate stuck days, not enough to hit the red short-circuit.
        add_task(db, team, teamlead, pavel, "Write regression checklist", TaskStatus.in_progress, 2, 4),
        add_task(db, team, teamlead, pavel, "Triage backlog bugs", TaskStatus.todo, 7, 2),
    ]

    db.commit()
    return tasks


async def backfill_score_history(team: Team, start_date) -> None:
    for offset in range(WINDOW_DAYS):
        as_of = start_date + timedelta(days=offset, hours=20)
        db = SessionLocal()
        try:
            fresh_team = db.get(Team, team.id)
            await recalculate_team_scores(db, fresh_team, as_of)
        finally:
            db.close()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    rng = random.Random(SEED)
    start_date = utcnow() - timedelta(days=WINDOW_DAYS - 1)

    db = SessionLocal()
    try:
        team = get_or_reset_team(db)
        teamlead = db.query(Member).filter(Member.team_id == team.id, Member.system_role == SystemRole.teamlead).first()
        members = seed_members(db, team)
        seed_commits_and_reviews(db, team, members, rng, start_date)
        tasks = seed_tasks(db, team, teamlead, members)
        seed_task_commits(db, team, tasks, members, rng)
    finally:
        db.close()

    print(f"Seeded {len(MEMBERS)} members + tasks + commits for '{DEMO_TEAM_NAME}'. Backfilling {WINDOW_DAYS} days of score history...")
    asyncio.run(backfill_score_history(team, start_date))
    print("Done. Open the dashboard and pick this team from 'Мои проекты' to explore.")


if __name__ == "__main__":
    main()
