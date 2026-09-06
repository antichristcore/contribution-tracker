from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.deps import get_current_member, get_db, require_teamlead
from backend.app.models import (
    Commit,
    GithubMapping,
    Member,
    PrReview,
    ScoreHistory,
    StatusColor,
    SystemRole,
    Task,
    Team,
)
from backend.app.schemas import (
    MemberCreate,
    MemberDetailOut,
    MemberOut,
    MemberSummaryOut,
    MemberUpdate,
    ScoreHistoryOut,
)
from backend.app.services.author_matching import rematch_unassigned
from backend.app.services.github_identity import check_github_username
from backend.app.services.team_membership import propagate_github_username
from backend.app.services.scoring import compute_team_scores, diagnose, get_raw_metrics
from backend.app.services.task_utils import commits_to_out, task_to_out
from backend.app.utils.time import utcnow

router = APIRouter(prefix="/api/members", tags=["members"])


def _latest_score(db: Session, member_id: int) -> ScoreHistory | None:
    return (
        db.query(ScoreHistory)
        .filter(ScoreHistory.member_id == member_id)
        .order_by(ScoreHistory.computed_at.desc())
        .first()
    )


class GithubCheckOut(BaseModel):
    ok: bool
    login: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    error: str | None = None
    warning: str | None = None


class GithubCheckIn(BaseModel):
    github_username: str


@router.post("/github-username/check", response_model=GithubCheckOut)
async def check_username(payload: GithubCheckIn) -> GithubCheckOut:
    """Существует ли такой логин на GitHub. Форма спрашивает до сохранения,
    чтобы человек увидел свою аватарку и понял, что привязался правильно."""
    check = await check_github_username(payload.github_username)
    return GithubCheckOut(**vars(check))


@router.get("", response_model=list[MemberSummaryOut])
def list_members(
    db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)
) -> list[MemberSummaryOut]:
    members = (
        db.query(Member)
        .filter(Member.team_id == teamlead.team_id, Member.is_active.is_(True))
        .all()
    )
    out = []
    for m in members:
        latest = _latest_score(db, m.id)
        out.append(
            MemberSummaryOut(
                **MemberOut.model_validate(m).model_dump(),
                status_color=latest.status_color if latest else StatusColor.no_data,
                contribution_score=latest.contribution_score if latest else None,
                has_data=latest.has_data if latest else False,
            )
        )
    return out


@router.get("/{member_id}", response_model=MemberDetailOut)
def get_member_detail(
    member_id: int,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> MemberDetailOut:
    member = db.get(Member, member_id)
    if not member or not member.is_active or member.team_id != current.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if current.system_role != SystemRole.teamlead and current.id != member.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")

    history = (
        db.query(ScoreHistory)
        .filter(ScoreHistory.member_id == member_id)
        .order_by(ScoreHistory.computed_at.asc())
        .all()
    )
    latest = history[-1] if history else None
    raw = get_raw_metrics(db, member, utcnow())
    tasks = db.query(Task).filter(Task.assignee_member_id == member_id).order_by(Task.created_at.desc()).all()
    commits = (
        db.query(Commit)
        .filter(Commit.member_id == member_id)
        .order_by(Commit.authored_at.desc())
        .limit(30)
        .all()
    )

    # Only surface the diagnosis once the member is already flagged — showing
    # a "no activity" note on an otherwise green member reads as a false alarm.
    is_flagged = latest is not None and latest.status_color in (StatusColor.yellow, StatusColor.red)

    peers = (
        db.query(Member)
        .filter(
            Member.team_id == member.team_id,
            Member.is_active.is_(True),
            Member.system_role != SystemRole.teamlead,
        )
        .all()
    )
    scored = next(
        (s for s in compute_team_scores(db, peers, utcnow()) if s["member"].id == member.id), None
    )

    return MemberDetailOut(
        member=MemberOut.model_validate(member),
        latest=ScoreHistoryOut.model_validate(latest) if latest else None,
        history=[ScoreHistoryOut.model_validate(h) for h in history],
        commits=commits_to_out(db, commits, db.get(Team, member.team_id)),
        diagnosis=diagnose(raw) if is_flagged else None,
        tasks=[task_to_out(db, t) for t in tasks],
        peer_basis=scored["peer_basis"] if scored else None,
        role_peer_count=scored["role_peer_count"] if scored else 0,
        breakdown=scored["breakdown"] if scored else None,
    )


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(
    payload: MemberCreate,
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> Member:
    member = Member(
        team_id=teamlead.team_id,
        display_name=payload.display_name,
        role_in_team=payload.role_in_team,
        system_role=payload.system_role,
        telegram_username=payload.telegram_username,
    )
    db.add(member)
    db.flush()

    if payload.github_username or payload.git_author_email or payload.git_author_name:
        db.add(
            GithubMapping(
                member_id=member.id,
                github_username=payload.github_username,
                git_author_email=payload.git_author_email,
                git_author_name=payload.git_author_name,
            )
        )
    db.commit()
    db.refresh(member)
    return member


def _would_leave_team_without_teamlead(db: Session, member: Member, new_role: SystemRole) -> bool:
    if member.system_role != SystemRole.teamlead or new_role == SystemRole.teamlead:
        return False
    others = (
        db.query(Member)
        .filter(
            Member.team_id == member.team_id,
            Member.id != member.id,
            Member.is_active.is_(True),
            Member.system_role == SystemRole.teamlead,
        )
        .count()
    )
    return others == 0


@router.patch("/{member_id}", response_model=MemberOut)
async def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> Member:
    member = db.get(Member, member_id)
    if not member or member.team_id != current.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    is_teamlead = current.system_role == SystemRole.teamlead
    is_self = current.id == member_id
    if not is_teamlead and not is_self:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")

    if not is_teamlead:
        # Members may only update their own GitHub mapping, not profile/role fields.
        if payload.display_name is not None or payload.role_in_team is not None or payload.system_role is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the teamlead can edit profile fields")

    if payload.display_name is not None:
        member.display_name = payload.display_name
    if payload.role_in_team is not None:
        member.role_in_team = payload.role_in_team
    if payload.system_role is not None and payload.system_role != member.system_role:
        # Иначе проектом становится некому управлять: приглашать, заводить
        # задачи и менять настройки может только тимлид.
        if _would_leave_team_without_teamlead(db, member, payload.system_role):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "В проекте не останется ни одного тимлида — сначала назначь другого",
            )
        member.system_role = payload.system_role

    if payload.github_username is not None or payload.git_author_email is not None or payload.git_author_name is not None:
        github_username = payload.github_username
        if github_username is not None:
            check = await check_github_username(github_username)
            if not check.ok:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, check.error)
            github_username = check.login
        mapping = member.github_mapping
        if not mapping:
            mapping = GithubMapping(member_id=member.id)
            member.github_mapping = mapping
        if github_username is not None:
            mapping.github_username = github_username
            db.flush()
            # Тот же человек в других проектах — тот же GitHub. Иначе блокирующий
            # экран встречает его заново на каждом проекте, и со стороны это
            # выглядит как «логин вообще не сохраняется».
            for team_id in propagate_github_username(db, member.telegram_user_id, github_username):
                rematch_unassigned(db, team_id)
        if payload.git_author_email is not None:
            mapping.git_author_email = payload.git_author_email
        if payload.git_author_name is not None:
            mapping.git_author_name = payload.git_author_name
        db.flush()
        # Человек привязал аккаунт уже после того, как его коммиты синканулись —
        # подбираем их сразу, иначе работа не засчитается до следующего синка.
        rematch_unassigned(db, member.team_id)

    db.commit()
    db.refresh(member)
    return member


@router.delete("/{member_id}/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_member_profile(
    member_id: int,
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> None:
    member = db.get(Member, member_id)
    if not member or member.team_id != current.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if current.system_role != SystemRole.teamlead and current.id != member.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")

    db.query(Commit).filter(Commit.member_id == member_id).update({Commit.member_id: None})
    db.query(PrReview).filter(PrReview.member_id == member_id).update({PrReview.member_id: None})
    db.query(ScoreHistory).filter(ScoreHistory.member_id == member_id).delete()
    db.query(Task).filter(Task.assignee_member_id == member_id).update({Task.assignee_member_id: None})
    if member.github_mapping:
        db.delete(member.github_mapping)
    member.is_active = False
    db.commit()
