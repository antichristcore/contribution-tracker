"""Shared config for the demo repo generator and the DB seed script, so
member names/emails/roles stay in sync between the two (github_sync_service
resolves virtual commit authors by email, since they have no real GitHub
account/login)."""

DEMO_MEMBERS = [
    {"name": "Anna Volkova", "email": "anna.volkova@demo.local", "role": "backend", "profile": "steady"},
    {"name": "Boris Titov", "email": "boris.titov@demo.local", "role": "frontend", "profile": "steady"},
    {"name": "Vera Sokolova", "email": "vera.sokolova@demo.local", "role": "design", "profile": "steady"},
    {"name": "Denis Orlov", "email": "denis.orlov@demo.local", "role": "backend", "profile": "falling"},
    {"name": "Egor Panin", "email": "egor.panin@demo.local", "role": "qa", "profile": "falling"},
]

DEMO_WINDOW_DAYS = 21
