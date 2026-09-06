import logging

from backend.app.bot.bot_instance import bot
from backend.app.models import Member, Task

logger = logging.getLogger("notifier")


async def _send(chat_id: int | None, text: str) -> None:
    if not bot or not chat_id:
        return
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.exception("Failed to send Telegram message to chat_id=%s", chat_id)


async def send_task_assigned(member: Member, task: Task) -> None:
    deadline = task.deadline_at.strftime("%d.%m.%Y") if task.deadline_at else "без дедлайна"
    text = f"📋 Тебе назначена новая задача: <b>{task.title}</b>\nДедлайн: {deadline}"
    await _send(member.telegram_chat_id, text)


async def send_yellow_reminder(member: Member) -> None:
    text = (
        "👋 Заметил(а), что активность по твоим задачам просела последние дни. "
        "Нужна помощь или что-то мешает? Напиши тимлиду, если застрял(а)."
    )
    await _send(member.telegram_chat_id, text)


async def send_red_alert(teamlead: Member, member: Member, days_stuck: int, task_title: str | None) -> None:
    task_part = f" по задаче «{task_title}»" if task_title else ""
    text = (
        f"🔴 Внимание: у {member.display_name} нет прогресса{task_part} уже {days_stuck} дн. "
        "Похоже, пора поговорить лично."
    )
    await _send(teamlead.telegram_chat_id, text)
