from fastapi import APIRouter, Depends

from backend.app.deps import get_current_member
from backend.app.models import Member
from backend.app.schemas import MemberOut

me_router = APIRouter(prefix="/api", tags=["auth"])


@me_router.get("/me", response_model=MemberOut)
def get_me(member: Member = Depends(get_current_member)) -> Member:
    return member
