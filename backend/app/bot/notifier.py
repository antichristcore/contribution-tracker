import logging

from backend.app.bot.bot_instance import bot
from backend.app.models import Member, Task
from backend.app.utils.words import days as days_word

logger = logging.getLogger("notifier")


async def _send(chat_id: int | None, text: str) -> None:
    if not bot or not chat_id:
        return
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        logger.exception("Failed to send Telegram message to chat_id=%s", chat_id)


async def send_task_assigned(member: Member, task: Task) -> None:
    """Номер задачи в уведомлении не для красоты: это единственное место, где
    человек узнаёт, что писать в коммите, чтобы работа привязалась сама."""
    deadline = task.deadline_at.strftime("%d.%m.%Y") if task.deadline_at else "без срока"
    text = (
        f"📋 Тебе назначили задачу #{task.number}: <b>{task.title}</b>\n"
        f"Срок: {deadline}\n\n"
        f"Пиши #{task.number} в сообщениях коммитов, тогда они привяжутся к задаче сами."
    )
    await _send(member.telegram_chat_id, text)


async def send_yellow_reminder(member: Member) -> None:
    text = (
        "👋 По твоим задачам несколько дней тихо. "
        "Если что-то мешает или нужна помощь, напиши тимлиду."
    )
    await _send(member.telegram_chat_id, text)


async def send_red_alert(teamlead: Member, member: Member, days_stuck: int, task_title: str | None) -> None:
    task_part = f" по задаче «{task_title}»" if task_title else ""
    text = (
        f"🔴 У {member.display_name} ничего не менялось{task_part} уже {days_word(days_stuck)}. "
        "Похоже, стоит поговорить лично."
    )
    await _send(teamlead.telegram_chat_id, text)
