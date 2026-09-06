from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.models import NotificationType, StatusColor, SystemRole, TaskStatus


def _round_score(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class GithubMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    github_username: str | None = None
    git_author_email: str | None = None
    git_author_name: str | None = None


class GithubMappingIn(BaseModel):
    member_id: int
    github_username: str | None = None
    git_author_email: str | None = None
    git_author_name: str | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    role_in_team: str
    system_role: SystemRole
    telegram_username: str | None = None
    is_active: bool
    github_mapping: GithubMappingOut | None = None


class MemberSummaryOut(MemberOut):
    status_color: StatusColor = StatusColor.no_data
    contribution_score: float | None = None
    has_data: bool = False

    _round_score = field_validator("contribution_score")(_round_score)


class MemberCreate(BaseModel):
    display_name: str
    role_in_team: str = "member"
    system_role: SystemRole = SystemRole.member
    telegram_username: str | None = None
    github_username: str | None = None
    git_author_email: str | None = None
    git_author_name: str | None = None


class MemberUpdate(BaseModel):
    display_name: str | None = None
    role_in_team: str | None = None
    system_role: SystemRole | None = None
    github_username: str | None = None
    git_author_email: str | None = None
    git_author_name: str | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Номер внутри проекта — то, что человек пишет в коммите. id остаётся
    # техническим идентификатором для маршрутов API.
    number: int
    title: str
    description: str | None
    assignee_member_id: int | None
    created_by_member_id: int | None
    status: TaskStatus
    deadline_at: datetime | None
    status_changed_at: datetime
    completed_at: datetime | None
    created_at: datetime
    stuck_days: int = 0
    linked_commits_count: int = 0
    assignee_name: str | None = None


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    assignee_member_id: int | None = None
    deadline_at: datetime | None = None

    _normalize_deadline = field_validator("deadline_at")(_naive_utc)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee_member_id: int | None = None
    deadline_at: datetime | None = None
    status: TaskStatus | None = None

    _normalize_deadline = field_validator("deadline_at")(_naive_utc)


class ScoreHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    computed_at: datetime
    contribution_score: float | None
    commits_count_7d: int
    commits_lines_changed_7d: int
    tasks_assigned: int
    tasks_completed_on_time: int
    tasks_status_stuck_days_max: int
    pr_review_comments_given: int
    last_activity_days_ago: int | None
    status_color: StatusColor
    has_data: bool

    _round_score = field_validator("contribution_score")(_round_score)


class TeamSummaryMemberOut(BaseModel):
    member_id: int
    display_name: str
    status_color: StatusColor
    contribution_score: float | None

    _round_score = field_validator("contribution_score")(_round_score)


class TeamSummaryOut(BaseModel):
    median_score: float | None
    green_count: int
    yellow_count: int
    red_count: int
    no_data_count: int
    members: list[TeamSummaryMemberOut]

    _round_score = field_validator("median_score")(_round_score)


class CommitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sha: str
    message: str | None
    authored_at: datetime
    additions: int | None
    deletions: int | None
    author_name: str | None = None
    html_url: str | None = None
    # Номер задачи, к которой привязан коммит, — суть продукта видна прямо
    # в списке коммитов, а не только внутри карточки задачи.
    task_number: int | None = None


class TaskHistoryOut(BaseModel):
    old_status: TaskStatus | None
    new_status: TaskStatus
    changed_at: datetime
    changed_by_name: str | None = None


class ScoreComponentOut(BaseModel):
    """Одно слагаемое формулы вклада. Заполняются только поля своей компоненты —
    подписи и формулировки живут на фронте, сюда идут только числа и ключи."""

    key: str
    # Вес уже после перераспределения: исключённая компонента отдаёт свой вес
    # остальным, и экран объясняет правило сам, ничего не дублируя.
    weight: float
    value: float | None = None
    points: float
    excluded: bool = False

    done_on_time: int | None = None
    eligible: int | None = None
    assigned: int | None = None
    raw_value: int | None = None
    peer_median: float | None = None
    capped: bool | None = None
    active_days: int | None = None
    target_days: int | None = None
    window_days: int | None = None
    stuck_days: int | None = None
    red_days: int | None = None


class ScoreBreakdownOut(BaseModel):
    score: int
    components: list[ScoreComponentOut]
    # Ключи пояснений: tasks_excluded | reviews_excluded | code_capped | peer_fallback_team
    notes: list[str] = []


class DiagnosisOut(BaseModel):
    label: str
    explanation: str


class TaskDetailOut(BaseModel):
    task: TaskOut
    commits: list[CommitOut]
    history: list[TaskHistoryOut]


class MemberDetailOut(BaseModel):
    member: MemberOut
    latest: ScoreHistoryOut | None
    history: list[ScoreHistoryOut]
    diagnosis: DiagnosisOut | None
    tasks: list[TaskOut]
    commits: list[CommitOut]
    # С чем сравнивали при нормализации: "role" или "team" (+ сколько человек в роли). Нужно, чтобы не выдавать откат на всю команду за нормализацию по роли.
    peer_basis: str | None = None
    role_peer_count: int = 0
    # Разбор балла на слагаемые — считается тем же кодом, что и сам балл.
    breakdown: ScoreBreakdownOut | None = None


class NotificationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    type: NotificationType
    related_task_id: int | None
    sent_at: datetime
    payload_summary: str | None
