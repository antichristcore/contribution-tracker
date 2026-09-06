from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.bot import notifier
from backend.app.models import (
    Member,
    NotificationLog,
    NotificationType,
    StatusColor,
    SystemRole,
    Task,
    TaskStatus,
)
from backend.app.utils.time import utcnow


def _already_sent_on(db: Session, member_id: int, ntype: NotificationType, as_of: datetime) -> bool:
    day = as_of.date()
    row = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.member_id == member_id,
            NotificationLog.type == ntype,
            func.date(NotificationLog.sent_at) == day,
        )
        .first()
    )
    return row is not None


async def notify_task_assigned(db: Session, task: Task) -> None:
    if not task.assignee_member_id:
        return
    member = db.get(Member, task.assignee_member_id)
    if not member:
        return
    await notifier.send_task_assigned(member, task)
    db.add(
        NotificationLog(
            member_id=member.id,
            type=NotificationType.task_assigned,
            related_task_id=task.id,
            payload_summary=task.title,
        )
    )
    db.commit()


async def notify_task_assigned_by_id(task_id: int) -> None:
    # Runs as a FastAPI BackgroundTask after the response is sent, so it opens
    # its own session rather than reusing the request-scoped one.
    from backend.app.db import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task:
            await notify_task_assigned(db, task)
    finally:
        db.close()


async def process_member_threshold(
    db: Session, team_id: int, member: Member, status_color: StatusColor, raw: dict, as_of: datetime | None = None
) -> None:
    as_of = as_of or utcnow()

    # Балл тимлиду считается, но пороги про него не пишут никому: жёлтое
    # напоминание «по твоим задачам тихо» он отправил бы сам себе, а красное
    # уведомление уходит всем тимлидам команды — то есть снова ему же, про него.
    if member.system_role == SystemRole.teamlead:
        return

    if status_color == StatusColor.yellow:
        if _already_sent_on(db, member.id, NotificationType.yellow_threshold, as_of):
            return
        await notifier.send_yellow_reminder(member)
        db.add(
            NotificationLog(
                member_id=member.id,
                type=NotificationType.yellow_threshold,
                payload_summary="score below team median for 5+ days",
                sent_at=as_of,
            )
        )
        db.commit()
        return

    if status_color == StatusColor.red:
        if _already_sent_on(db, member.id, NotificationType.red_threshold, as_of):
            return
        teamleads = (
            db.query(Member)
            .filter(Member.team_id == team_id, Member.system_role == SystemRole.teamlead, Member.is_active.is_(True))
            .all()
        )
        stuck_task = (
            db.query(Task)
            .filter(Task.assignee_member_id == member.id, Task.status != TaskStatus.done)
            .order_by(Task.status_changed_at.asc())
            .first()
        )
        days_stuck = raw.get("tasks_status_stuck_days_max", 0)
        for teamlead in teamleads:
            await notifier.send_red_alert(teamlead, member, days_stuck, stuck_task.title if stuck_task else None)
        db.add(
            NotificationLog(
                member_id=member.id,
                type=NotificationType.red_threshold,
                sent_at=as_of,
                related_task_id=stuck_task.id if stuck_task else None,
                payload_summary=f"stuck {days_stuck} days",
            )
        )
        db.commit()
