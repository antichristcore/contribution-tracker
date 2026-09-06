import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.deps import get_current_member, get_db, require_teamlead
from backend.app.models import GithubMapping, Member, Team
from backend.app.schemas import GithubMappingIn, GithubMappingOut
from backend.app.services.github_client import discover_repos_for_token
from backend.app.services.github_sync_service import sync_team
from backend.app.services.recalc import recalculate_team_scores

router = APIRouter(prefix="/api/github", tags=["github"])


class DiscoverRequest(BaseModel):
    token: str


class DiscoveredRepo(BaseModel):
    owner: str
    repo: str
    private: bool
    full_name: str


class DiscoverResponse(BaseModel):
    repos: list[DiscoveredRepo]
    error: str | None = None


def _get_team(db: Session, member: Member) -> Team:
    team = db.get(Team, member.team_id)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found")
    return team


@router.post("/discover-repos", response_model=DiscoverResponse)
async def discover_repos(
    payload: DiscoverRequest, _teamlead: Member = Depends(require_teamlead)
) -> DiscoverResponse:
    try:
        repos = await discover_repos_for_token(payload.token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            return DiscoverResponse(repos=[], error="Токен не принят GitHub — проверь, что скопирован полностью.")
        return DiscoverResponse(repos=[], error=f"GitHub ответил ошибкой: {exc.response.status_code}")
    except Exception as exc:
        return DiscoverResponse(repos=[], error=str(exc))

    return DiscoverResponse(repos=[DiscoveredRepo(**r) for r in repos])


@router.post("/sync")
async def trigger_sync(
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> dict:
    return await sync_team(db, _get_team(db, teamlead))


@router.post("/refresh")
async def trigger_refresh(
    db: Session = Depends(get_db),
    current: Member = Depends(get_current_member),
) -> dict:
    # Any team member can trigger this (not just the teamlead) — so after
    # pushing a commit, a participant can see their own task/score update
    # right away instead of waiting for the periodic background sync.
    team = _get_team(db, current)
    sync_result = await sync_team(db, team)
    await recalculate_team_scores(db, team)
    return sync_result


@router.get("/status")
def sync_status(
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> dict:
    team = _get_team(db, teamlead)
    mapped_members = (
        db.query(GithubMapping).join(Member).filter(Member.team_id == teamlead.team_id).count()
    )
    return {
        "github_owner": team.github_owner,
        "github_repo": team.github_repo,
        "last_synced_at": team.last_synced_at,
        "mapped_members": mapped_members,
    }


@router.get("/mappings", response_model=list[GithubMappingOut])
def list_mappings(
    db: Session = Depends(get_db), teamlead: Member = Depends(require_teamlead)
) -> list[GithubMapping]:
    return db.query(GithubMapping).join(Member).filter(Member.team_id == teamlead.team_id).all()


@router.post("/mappings", response_model=GithubMappingOut)
def upsert_mapping(
    payload: GithubMappingIn,
    db: Session = Depends(get_db),
    teamlead: Member = Depends(require_teamlead),
) -> GithubMapping:
    target_member = db.get(Member, payload.member_id)
    if not target_member or target_member.team_id != teamlead.team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")

    mapping = db.query(GithubMapping).filter(GithubMapping.member_id == payload.member_id).first()
    if not mapping:
        mapping = GithubMapping(member_id=payload.member_id)
        db.add(mapping)
    mapping.github_username = payload.github_username
    mapping.git_author_email = payload.git_author_email
    mapping.git_author_name = payload.git_author_name
    db.commit()
    db.refresh(mapping)
    return mapping
