import logging
from datetime import datetime

import httpx

logger = logging.getLogger("github_client")

GITHUB_API_BASE = "https://api.github.com"


class GitHubClient:
    def __init__(self, owner: str, repo: str, token: str | None = None):
        self.owner = owner
        self.repo = repo
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(base_url=GITHUB_API_BASE, headers=headers, timeout=30.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _check_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) < 50:
            logger.warning("GitHub rate limit low: %s requests remaining", remaining)

    async def _get_all_pages(self, url: str, params: dict) -> list[dict]:
        results: list[dict] = []
        next_url: str | None = url
        next_params: dict | None = {**params, "per_page": 100}
        while next_url:
            response = await self._client.get(next_url, params=next_params)
            response.raise_for_status()
            self._check_rate_limit(response)
            results.extend(response.json())
            next_url = response.links.get("next", {}).get("url")
            next_params = None
        return results

    async def list_commits(self, since: datetime | None = None) -> list[dict]:
        params: dict = {}
        if since:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        return await self._get_all_pages(f"/repos/{self.owner}/{self.repo}/commits", params)

    async def get_commit(self, sha: str) -> dict:
        response = await self._client.get(f"/repos/{self.owner}/{self.repo}/commits/{sha}")
        response.raise_for_status()
        self._check_rate_limit(response)
        return response.json()

    async def list_recent_pull_requests(self, state: str = "all", limit: int = 30) -> list[dict]:
        # Single page only, sorted by most recently updated — a repo with a
        # huge PR history (e.g. thousands of forks/tutorial PRs) must not
        # trigger unbounded pagination + one reviews-call per PR.
        response = await self._client.get(
            f"/repos/{self.owner}/{self.repo}/pulls",
            params={"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
        )
        response.raise_for_status()
        self._check_rate_limit(response)
        return response.json()

    async def list_pr_reviews(self, pr_number: int) -> list[dict]:
        return await self._get_all_pages(f"/repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews", {})


async def discover_repos_for_token(token: str) -> list[dict]:
    """List repos a PAT can see via GET /user/repos. For a fine-grained token
    scoped to one repo, GitHub only returns that repo here — which is what
    lets us skip asking for owner/repo separately when the token already
    implies it."""
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=GITHUB_API_BASE, headers=headers, timeout=15.0) as client:
        response = await client.get("/user/repos", params={"per_page": 100, "sort": "pushed"})
        response.raise_for_status()
        repos = response.json()

    return [
        {"owner": r["owner"]["login"], "repo": r["name"], "private": r["private"], "full_name": r["full_name"]}
        for r in repos
    ]
