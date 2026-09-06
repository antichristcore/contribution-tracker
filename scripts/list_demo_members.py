"""Печатает id участников по командам — нужны для локального демо
(http://localhost:8001/?as=<id>, см. scripts/demo_local.ps1).

    python scripts/list_demo_members.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db import SessionLocal  # noqa: E402
from backend.app.models import Member, Team  # noqa: E402

db = SessionLocal()
try:
    for team in db.query(Team).order_by(Team.id).all():
        repo = f"{team.github_owner}/{team.github_repo}" if team.github_owner else "репозиторий не подключён"
        print(f"\n[{team.id}] {team.name}  ({repo})")
        for m in db.query(Member).filter(Member.team_id == team.id).order_by(Member.id).all():
            mark = "тимлид" if m.system_role.value == "teamlead" else m.role_in_team
            print(f"    ?as={m.id:<4} {m.display_name}  ({mark})")
finally:
    db.close()
