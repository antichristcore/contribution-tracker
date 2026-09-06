import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base
from backend.app.utils.time import utcnow


class SystemRole(str, enum.Enum):
    teamlead = "teamlead"
    member = "member"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class StatusColor(str, enum.Enum):
    green = "green"
    yellow = "yellow"
    red = "red"
    no_data = "no_data"


class NotificationType(str, enum.Enum):
    task_assigned = "task_assigned"
    yellow_threshold = "yellow_threshold"
    red_threshold = "red_threshold"


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    github_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    github_repo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Per-team PAT, used instead of the server-wide GITHUB_TOKEN env var when
    # set — needed once different teams' repos aren't accessible by one shared
    # token (e.g. each teamlead's own private repo).
    github_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["Member"]] = relationship(back_populates="team")


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("team_id", "telegram_user_id", name="uq_member_team_telegram_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    display_name: Mapped[str] = mapped_column(String(200))
    role_in_team: Mapped[str] = mapped_column(String(50), default="member")
    system_role: Mapped[SystemRole] = mapped_column(Enum(SystemRole), default=SystemRole.member)

    # A person can be a member of several teams (e.g. a teamlead running
    # multiple projects), so telegram_user_id is unique per-team, not globally.
    telegram_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    team: Mapped["Team"] = relationship(back_populates="members")
    github_mapping: Mapped["GithubMapping | None"] = relationship(
        back_populates="member", uselist=False, cascade="all, delete-orphan"
    )


class GithubMapping(Base):
    __tablename__ = "github_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), unique=True)
    github_username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    git_author_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    git_author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    member: Mapped["Member"] = relationship(back_populates="github_mapping")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("team_id", "number", name="uq_task_team_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    # Номер, который человек пишет в коммите. Сквозной id не годится: он общий
    # на всю базу, и у второго проекта задачи начинались бы с "#46".
    number: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    created_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.todo)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assignee: Mapped["Member | None"] = relationship(foreign_keys=[assignee_member_id])
    history: Mapped[list["TaskStatusHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    old_status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
    new_status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    changed_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="history")


class Commit(Base):
    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("team_id", "sha", name="uq_commit_team_sha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    sha: Mapped[str] = mapped_column(String(64))
    raw_author_login: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_author_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stats_fetched: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PrReview(Base):
    __tablename__ = "pr_reviews"
    __table_args__ = (UniqueConstraint("team_id", "review_id", name="uq_review_team_review_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pr_number: Mapped[int] = mapped_column(Integer)
    review_id: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    contribution_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    commits_count_7d: Mapped[int] = mapped_column(Integer, default=0)
    commits_lines_changed_7d: Mapped[int] = mapped_column(Integer, default=0)
    tasks_assigned: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed_on_time: Mapped[int] = mapped_column(Integer, default=0)
    tasks_status_stuck_days_max: Mapped[int] = mapped_column(Integer, default=0)
    pr_review_comments_given: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_days_ago: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status_color: Mapped[StatusColor] = mapped_column(Enum(StatusColor), default=StatusColor.no_data)
    has_data: Mapped[bool] = mapped_column(Boolean, default=False)


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType))
    related_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
