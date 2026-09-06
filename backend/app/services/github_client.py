import logging
from datetime import datetime

import httpx

logger = logging.getLogger("github_client")

GITHUB_API_BASE = "https://api.github.com"


def plausible_token(token: str | None) -> str | None:
    """Пустой или заведомо битый токен не отправляем в GitHub.

    Guards against shipped-example placeholders (like ".env.example"'s
    "ghp_xxx") being sent to GitHub as a real credential — real PATs are much
    longer than that, so a short one is almost certainly a leftover placeholder.
    Отправленный мусор хуже отсутствия токена: GitHub отвечает 401 на запрос,
    который анонимно прошёл бы, и проверка логина молча превращается в
    «сохранили как есть».
    """
    if token and len(token.strip()) >= 20:
        return token.strip()
    return None


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


async def fetch_github_user(login: str, token: str | None = None) -> dict | None | str:
    """Профиль пользователя по логину.

    dict  — пользователь есть;
    None  — такого логина на GitHub нет (404);
    str   — проверить не удалось, внутри причина человеческими словами.

    Токен не обязателен: GET /users/{login} открыт анонимно. Но анонимно
    GitHub даёт всего 60 запросов в час на IP, а через туннель этот IP один
    на всех — поэтому токен команды, если он есть, поднимает лимит до 5000.
    Битый токен отбрасываем: с ним запрос вернул бы 401 там, где анонимно
    он бы прошёл.
    """
    token = plausible_token(token)
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(base_url=GITHUB_API_BASE, headers=headers, timeout=8.0) as client:
            response = await client.get(f"/users/{login}")
    except httpx.HTTPError as exc:
        logger.warning("GitHub user lookup failed for %s: %s", login, exc)
        return "GitHub сейчас не отвечает"

    if response.status_code == 404:
        return None
    if response.status_code in (403, 429):
        # 403 здесь почти всегда исчерпанный лимит, а не запрет доступа:
        # у публичного профиля запрещать нечего.
        logger.warning("GitHub rate limit hit while checking %s", login)
        return "GitHub временно ограничил проверки"
    if response.status_code != 200:
        logger.warning("GitHub user lookup returned %s for %s", response.status_code, login)
        return "GitHub ответил ошибкой"
    return response.json()
