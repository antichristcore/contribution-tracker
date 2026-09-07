import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models import Commit, GithubMapping, Member, PrReview, Team
from backend.app.services.github_client import GitHubClient, plausible_token as _plausible_token
from backend.app.services.author_matching import rematch_unassigned, resolve_member_id
from backend.app.services.task_linking import relink_unlinked_commits
from backend.app.utils.time import utcnow

logger = logging.getLogger("github_sync")

MAX_STATS_FETCH_PER_RUN = 40
MAX_PRS_PER_RUN = 30


def _parse_github_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    # GitHub timestamps are always UTC ("...Z"); store naive UTC to match
    # how SQLite round-trips every other datetime in this app.
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)


def _resolve_member_id(
    db: Session, team_id: int, login: str | None, email: str | None, name: str | None
) -> int | None:
    return resolve_member_id(db, team_id, login, email, name)



async def sync_team(db: Session, team: Team) -> dict:
    """Pull new commits + PR reviews for a team's repo. Never raises: any
    GitHub API failure (rate limit, network, bad repo) is reported back as
    {"error": ...} so a flaky GitHub call never 500s the demo."""
    if not team.github_owner or not team.github_repo:
        return {"error": "team has no github_owner/github_repo configured"}

    token = _plausible_token(team.github_token) or _plausible_token(settings.GITHUB_TOKEN)
    client = GitHubClient(team.github_owner, team.github_repo, token)
    try:
        return await _sync_commits_and_reviews(db, team, client)
    except Exception as exc:
        logger.exception("GitHub sync failed for team %s", team.id)
        db.rollback()
        return {"error": str(exc)}
    finally:
        await client.aclose()


async def _sync_commits_and_reviews(db: Session, team: Team, client: GitHubClient) -> dict:
    last_commit = (
        db.query(Commit).filter(Commit.team_id == team.id).order_by(Commit.authored_at.desc()).first()
    )
    since = (
        last_commit.authored_at
        if last_commit
        else utcnow() - timedelta(days=settings.GITHUB_SYNC_LOOKBACK_DAYS)
    )

    existing_shas = {row[0] for row in db.query(Commit.sha).filter(Commit.team_id == team.id).all()}

    new_commits = 0
    unresolved_authors: set[str] = set()

    commits_data = await client.list_commits(since=since)
    for c in commits_data:
        sha = c["sha"]
        if sha in existing_shas:
            continue

        commit_info = c.get("commit", {})
        author_info = commit_info.get("author") or {}
        gh_author = c.get("author") or {}
        login = gh_author.get("login")
        email = author_info.get("email")
        name = author_info.get("name")
        authored_at = _parse_github_timestamp(author_info.get("date")) or utcnow()
        message = commit_info.get("message")

        member_id = _resolve_member_id(db, team.id, login, email, name)
        if member_id is None:
            unresolved_authors.add(login or email or name or "unknown")

        db.add(
            Commit(
                team_id=team.id,
                member_id=member_id,
                sha=sha,
                raw_author_login=login,
                raw_author_email=email,
                raw_author_name=name,
                message=message,
                authored_at=authored_at,
                stats_fetched=False,
            )
        )
        existing_shas.add(sha)
        new_commits += 1

    db.flush()

    # Автор коммита мог быть неизвестен в момент вставки: человек привязал
    # GitHub уже после того, как его коммиты синканулись. Проходим по ничейным
    # ещё раз, иначе работа не засчитается до правки профиля вручную.
    rematched = rematch_unassigned(db, team.id)

    # Attach commits to tasks in one pass, oldest first: this covers both the
    # commits just fetched and any that arrived before their task existed.
    linked_commits = relink_unlinked_commits(db, team.id)

    pending_stats = (
        db.query(Commit)
        .filter(Commit.team_id == team.id, Commit.stats_fetched.is_(False))
        .limit(MAX_STATS_FETCH_PER_RUN)
        .all()
    )
    stats_fetched = 0
    for commit_row in pending_stats:
        try:
            detail = await client.get_commit(commit_row.sha)
        except Exception:
            logger.exception("Failed to fetch stats for commit %s", commit_row.sha)
            continue
        stats = detail.get("stats", {})
        commit_row.additions = stats.get("additions", 0)
        commit_row.deletions = stats.get("deletions", 0)
        commit_row.stats_fetched = True
        stats_fetched += 1

    new_reviews = 0
    existing_review_ids = {
        row[0] for row in db.query(PrReview.review_id).filter(PrReview.team_id == team.id).all()
    }
    try:
        pull_requests = await client.list_recent_pull_requests(state="all", limit=MAX_PRS_PER_RUN)
    except Exception:
        logger.exception("Failed to list pull requests")
        pull_requests = []

    for pr in pull_requests:
        pr_number = pr["number"]
        try:
            reviews = await client.list_pr_reviews(pr_number)
        except Exception:
            logger.exception("Failed to list reviews for PR %s", pr_number)
            continue
        for review in reviews:
            review_id = review["id"]
            if review_id in existing_review_ids:
                continue
            login = (review.get("user") or {}).get("login")
            member_id = _resolve_member_id(db, team.id, login, None, None)
            submitted_at = _parse_github_timestamp(review.get("submitted_at"))
            db.add(
                PrReview(
                    team_id=team.id,
                    member_id=member_id,
                    github_username=login,
                    pr_number=pr_number,
                    review_id=review_id,
                    submitted_at=submitted_at,
                    state=review.get("state"),
                )
            )
            existing_review_ids.add(review_id)
            new_reviews += 1

    team.last_synced_at = utcnow()
    db.commit()

    return {
        "new_commits": new_commits,
        "linked_commits": linked_commits,
        "rematched_authors": rematched,
        "stats_fetched": stats_fetched,
        "new_reviews": new_reviews,
        "unresolved_authors": sorted(unresolved_authors),
    }
