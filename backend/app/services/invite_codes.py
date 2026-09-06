import secrets
import string

from sqlalchemy.orm import Session

from backend.app.models import Team

_ALPHABET = string.ascii_uppercase + string.digits
# Excludes visually ambiguous characters (0/O, 1/I) since people retype these by hand.
_ALPHABET = _ALPHABET.translate(str.maketrans("", "", "0O1I"))


def generate_unique_invite_code(db: Session, length: int = 6) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if not db.query(Team).filter(Team.invite_code == code).first():
            return code
    raise RuntimeError("Could not generate a unique invite code")
