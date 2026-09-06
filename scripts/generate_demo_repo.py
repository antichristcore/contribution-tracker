"""Generates a local git repo with a realistic 3-week commit history for
5 virtual team members (see demo_config.py), so the Contribution Tracker
has something believable to sync via the GitHub REST API without depending
on real activity during the demo.

Two of the five members ("falling" profile) taper off hard in weeks 2-3,
so the dashboard visibly shows a "before" dip.

Usage:
    python scripts/generate_demo_repo.py
    python scripts/generate_demo_repo.py --push --remote-url https://github.com/you/demo-repo.git
"""

import argparse
import random
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from demo_config import DEMO_MEMBERS, DEMO_WINDOW_DAYS

ROLE_FILES = {
    "backend": "backend_notes.md",
    "frontend": "frontend_notes.md",
    "design": "design_notes.md",
    "qa": "qa_notes.md",
}

COMMIT_TEMPLATES = {
    "backend": [
        "Add {n} endpoint handler",
        "Fix edge case in service layer #{n}",
        "Refactor DB query for task #{n}",
        "Add validation for request #{n}",
    ],
    "frontend": [
        "Add {n} component",
        "Fix layout bug in view #{n}",
        "Wire up API call #{n}",
        "Polish UI state #{n}",
    ],
    "design": [
        "Update mockup #{n}",
        "Add color/spacing tokens #{n}",
        "Iterate on card layout #{n}",
        "Add icon set #{n}",
    ],
    "qa": [
        "Add test case #{n}",
        "Fix flaky test #{n}",
        "Extend coverage for module #{n}",
        "Log bug report notes #{n}",
    ],
}

WORK_HOUR_RANGE = (9, 19)


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def init_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    if not (repo_dir / ".git").exists():
        run(["git", "init", "-b", "main"], cwd=repo_dir)

    for role, filename in ROLE_FILES.items():
        path = repo_dir / filename
        if not path.exists():
            path.write_text(f"# {role.capitalize()} notes\n\n", encoding="utf-8")
    readme = repo_dir / "README.md"
    if not readme.exists():
        readme.write_text("# Demo Project\n\nSynthetic repo for Contribution Tracker demo.\n", encoding="utf-8")


def commits_for_day(profile: str, week_index: int, rng: random.Random) -> int:
    if profile == "steady":
        if rng.random() < 0.15:
            return 0
        return rng.choice([1, 1, 2])
    # "falling": normal first week, then a steep 70-90% drop
    if week_index == 0:
        if rng.random() < 0.15:
            return 0
        return rng.choice([1, 1, 2])
    if rng.random() < 0.85:
        return 0
    return 1


def make_commit(
    repo_dir: Path, member: dict, commit_time: datetime, counter: int, rng: random.Random
) -> None:
    filename = ROLE_FILES[member["role"]]
    path = repo_dir / filename
    template = rng.choice(COMMIT_TEMPLATES[member["role"]])
    message = template.format(n=counter)

    with path.open("a", encoding="utf-8") as f:
        f.write(f"- [{commit_time:%Y-%m-%d %H:%M}] {message} (by {member['name']})\n")
        if rng.random() < 0.3:
            f.write(f"  detail: touched module {rng.randint(1, 20)}\n")

    if rng.random() < 0.15 and path.read_text(encoding="utf-8").count("\n") > 4:
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[rng.randrange(2, len(lines))]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    date_str = commit_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    env = {
        "GIT_AUTHOR_NAME": member["name"],
        "GIT_AUTHOR_EMAIL": member["email"],
        "GIT_AUTHOR_DATE": date_str,
        "GIT_COMMITTER_NAME": member["name"],
        "GIT_COMMITTER_EMAIL": member["email"],
        "GIT_COMMITTER_DATE": date_str,
    }
    import os

    full_env = {**os.environ, **env}
    run(["git", "add", "-A"], cwd=repo_dir)
    run(["git", "commit", "-m", message, "--no-gpg-sign"], cwd=repo_dir, env=full_env)


def generate(repo_dir: Path, days: int, end_date: datetime, seed: int) -> int:
    rng = random.Random(seed)
    init_repo(repo_dir)

    start_date = end_date - timedelta(days=days - 1)
    total_commits = 0
    counters = {m["email"]: 0 for m in DEMO_MEMBERS}

    for offset in range(days):
        day = start_date + timedelta(days=offset)
        week_index = offset // 7
        for member in DEMO_MEMBERS:
            n = commits_for_day(member["profile"], week_index, rng)
            for i in range(n):
                hour = rng.randint(*WORK_HOUR_RANGE)
                minute = rng.randint(0, 59)
                commit_time = day.replace(hour=hour, minute=minute, second=rng.randint(0, 59))
                counters[member["email"]] += 1
                make_commit(repo_dir, member, commit_time, counters[member["email"]], rng)
                total_commits += 1

    return total_commits


def push(repo_dir: Path, remote_url: str) -> None:
    remotes = subprocess.run(
        ["git", "remote"], cwd=repo_dir, capture_output=True, text=True, check=True
    ).stdout.split()
    if "origin" not in remotes:
        run(["git", "remote", "add", "origin", remote_url], cwd=repo_dir)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_dir, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "demo-repo"))
    parser.add_argument("--days", type=int, default=DEMO_WINDOW_DAYS)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--remote-url", default=None)
    args = parser.parse_args()

    repo_dir = Path(args.out_dir)
    end_date = datetime.utcnow().replace(microsecond=0)

    total = generate(repo_dir, args.days, end_date, args.seed)
    print(f"Generated {total} commits across {args.days} days in {repo_dir}")

    if args.push:
        if not args.remote_url:
            raise SystemExit("--push requires --remote-url")
        push(repo_dir, args.remote_url)
        print(f"Pushed to {args.remote_url}")


if __name__ == "__main__":
    main()
