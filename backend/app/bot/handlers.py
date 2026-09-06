from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import Member
from backend.app.services.github_client import discover_repos_for_token
from backend.app.services.team_membership import (
    TeamNameTakenError,
    create_team,
    join_team_by_code,
    list_member_teams,
    set_github_username,
    team_name_taken,
)

router = Router()

TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")


def _looks_like_token(text: str) -> bool:
    return text.startswith(TOKEN_PREFIXES)

ROLE_LABELS = {
    "backend": "Backend",
    "frontend": "Frontend",
    "design": "Design",
    "qa": "QA",
    "pm": "PM",
    "ba": "Бизнес-аналитик",
    "sa": "Системный аналитик",
    "devops": "DevOps",
}


class Onboarding(StatesGroup):
    awaiting_invite_code = State()
    awaiting_team_name = State()
    awaiting_repo = State()
    awaiting_github_username = State()


def _open_app_keyboard(team_id: int):
    builder = InlineKeyboardBuilder()
    if settings.MINI_APP_URL:
        builder.button(
            text="Открыть дашборд",
            web_app=WebAppInfo(url=f"{settings.MINI_APP_URL}?team={team_id}"),
        )
    return builder.as_markup()


def _choose_role_keyboard(team_id: int):
    builder = InlineKeyboardBuilder()
    for role, label in ROLE_LABELS.items():
        builder.button(text=label, callback_data=f"role:{team_id}:{role}")
    builder.adjust(2)
    return builder.as_markup()


def _skip_keyboard(callback_data: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить", callback_data=callback_data)
    return builder.as_markup()


async def _finish_create_team(
    message: Message,
    state: FSMContext,
    name: str,
    user: User,
    github_owner: str | None,
    github_repo: str | None,
    github_token: str | None = None,
) -> None:
    await state.clear()
    db = SessionLocal()
    try:
        team, _member = create_team(
            db, name, user.id, user.username, user.first_name, github_owner, github_repo, github_token
        )
    except TeamNameTakenError:
        await message.answer(f"Пока ты вводил(а) данные, название «{name}» кто-то уже занял. Отправь /start и попробуй снова с другим названием.")
        return
    finally:
        db.close()

    repo_note = f" Репозиторий {github_owner}/{github_repo} подключён." if github_owner else ""
    await message.answer(f"Проект «{team.name}» создан!{repo_note} Ссылка-приглашение есть в дашборде.")
    await message.answer("Открыть дашборд:", reply_markup=_open_app_keyboard(team.id))


async def _ask_for_github_username(message: Message, state: FSMContext, team_id: int) -> None:
    await state.set_state(Onboarding.awaiting_github_username)
    await state.update_data(team_id=team_id)
    await message.answer(
        "Укажи свой GitHub username, чтобы бот мог считать твои коммиты.",
        reply_markup=_skip_keyboard("skip_github"),
    )


async def _finish_github_username(message: Message, team_id: int | None, github_username: str | None) -> None:
    if team_id and github_username:
        db = SessionLocal()
        try:
            set_github_username(db, team_id, message.from_user.id, github_username)
        finally:
            db.close()
        await message.answer(f"Готово, привязал GitHub: {github_username}.")
    else:
        await message.answer("Ок, пропускаем — тимлид сможет добавить это позже.")

    if team_id:
        await message.answer("Открыть дашборд:", reply_markup=_open_app_keyboard(team_id))


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_code(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    code = (command.args or "").strip()
    user = message.from_user

    db = SessionLocal()
    try:
        result = join_team_by_code(db, code, user.id, user.username, user.first_name)
        if result:
            member = result[1]
            if member.telegram_chat_id != message.chat.id:
                member.telegram_chat_id = message.chat.id
                db.commit()
    finally:
        db.close()

    if not result:
        await message.answer("Код приглашения не найден. Проверь ссылку у тимлида и попробуй ещё раз.")
        return

    team, _member = result
    await message.answer(
        f"Готово! Ты в команде «{team.name}». Какая у тебя роль?",
        reply_markup=_choose_role_keyboard(team.id),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user

    db = SessionLocal()
    try:
        memberships = list_member_teams(db, user.id)
        for member, _team in memberships:
            if member.telegram_chat_id != message.chat.id:
                member.telegram_chat_id = message.chat.id
        db.commit()
    finally:
        db.close()

    builder = InlineKeyboardBuilder()
    if settings.MINI_APP_URL:
        for _member, team in memberships:
            builder.button(
                text=f"Открыть «{team.name}»",
                web_app=WebAppInfo(url=f"{settings.MINI_APP_URL}?team={team.id}"),
            )
    builder.button(
        text="Создать ещё один проект" if memberships else "Я тимлид, создать проект",
        callback_data="create_team",
    )
    builder.button(text="У меня есть код приглашения", callback_data="have_code")
    builder.adjust(1)

    if not memberships:
        text = (
            "Привет! Ты пока не состоишь ни в одном проекте.\n\n"
            "Если ты тимлид — создай проект. Если тебя пригласили — введи код приглашения."
        )
    elif len(memberships) == 1:
        text = f"С возвращением в «{memberships[0][1].name}»!"
    else:
        text = "Твои проекты:"

    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "create_team")
async def cb_create_team(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.awaiting_team_name)
    await callback.message.edit_text("Как назовём проект? Пришли название одним сообщением.")
    await callback.answer()


@router.message(StateFilter(Onboarding.awaiting_team_name))
async def on_team_name_message(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым. Попробуй ещё раз.")
        return

    db = SessionLocal()
    try:
        taken = team_name_taken(db, name)
    finally:
        db.close()
    if taken:
        await message.answer(f"Проект «{name}» уже существует. Придумай другое название.")
        return

    await state.set_state(Onboarding.awaiting_repo)
    await state.update_data(pending_team_name=name)
    await message.answer(
        f"Отлично, проект будет называться «{name}». Теперь укажи GitHub-репозиторий в формате owner/repo "
        "(например octocat/Hello-World).\n\n"
        "Если репозиторий приватный — вместо этого просто пришли токен доступа (ghp_... или github_pat_...), "
        "и я сам найду репозиторий."
    )
    await message.answer("Или пропусти — добавишь позже в дашборде:", reply_markup=_skip_keyboard("skip_repo"))


@router.message(StateFilter(Onboarding.awaiting_repo))
async def on_repo_message(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    data = await state.get_data()
    name = data["pending_team_name"]

    if _looks_like_token(text):
        try:
            repos = await discover_repos_for_token(text)
        except Exception:
            await message.answer(
                "Не получилось проверить токен. Проверь, что скопирован полностью, и попробуй снова.",
                reply_markup=_skip_keyboard("skip_repo"),
            )
            return

        if not repos:
            await message.answer(
                "Токен не даёт доступа ни к одному репозиторию. Пришли owner/repo вручную или пропусти.",
                reply_markup=_skip_keyboard("skip_repo"),
            )
            return
        if len(repos) > 1:
            names = "\n".join(f"• {r['full_name']}" for r in repos[:15])
            await message.answer(
                f"Токен даёт доступ к нескольким репозиториям:\n{names}\n\nПришли нужный в формате owner/repo."
            )
            await state.update_data(pending_token=text)
            return

        repo = repos[0]
        await _finish_create_team(message, state, name, message.from_user, repo["owner"], repo["repo"], text)
        return

    parts = text.strip("/ ").split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        await message.answer(
            "Не похоже на owner/repo или токен. Пример: octocat/Hello-World.",
            reply_markup=_skip_keyboard("skip_repo"),
        )
        return

    token = data.get("pending_token")
    await _finish_create_team(message, state, name, message.from_user, parts[0], parts[1], token)


@router.callback_query(F.data == "skip_repo", StateFilter(Onboarding.awaiting_repo))
async def cb_skip_repo(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await callback.message.edit_text("Без репозитория — ок.")
    await _finish_create_team(callback.message, state, data["pending_team_name"], callback.from_user, None, None)
    await callback.answer()


@router.callback_query(F.data == "have_code")
async def cb_have_code(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.awaiting_invite_code)
    await callback.message.edit_text("Пришли код приглашения одним сообщением (его даёт тимлид).")
    await callback.answer()


@router.message(StateFilter(Onboarding.awaiting_invite_code))
async def on_invite_code_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    code = message.text.strip()

    db = SessionLocal()
    try:
        result = join_team_by_code(db, code, user.id, user.username, user.first_name)
    finally:
        db.close()

    if not result:
        await message.answer("Такой код не найден. Уточни у тимлида и попробуй снова: отправь /start.")
        return

    team, _member = result
    await message.answer(
        f"Готово! Ты в команде «{team.name}». Какая у тебя роль?",
        reply_markup=_choose_role_keyboard(team.id),
    )


@router.callback_query(F.data.startswith("role:"))
async def cb_choose_role(callback: CallbackQuery, state: FSMContext) -> None:
    _prefix, team_id_str, role = callback.data.split(":", 2)
    team_id = int(team_id_str)
    user = callback.from_user

    db = SessionLocal()
    try:
        member = (
            db.query(Member)
            .filter(Member.team_id == team_id, Member.telegram_user_id == user.id)
            .first()
        )
        if member:
            member.role_in_team = role
            if member.telegram_chat_id != callback.message.chat.id:
                member.telegram_chat_id = callback.message.chat.id
            db.commit()
    finally:
        db.close()

    await callback.message.edit_text(f"Роль сохранена: {ROLE_LABELS.get(role, role)}.")
    await _ask_for_github_username(callback.message, state, team_id)
    await callback.answer()


@router.message(StateFilter(Onboarding.awaiting_github_username))
async def on_github_username_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    team_id = data.get("team_id")
    github_username = message.text.strip().lstrip("@")
    await state.clear()
    await _finish_github_username(message, team_id, github_username)


@router.callback_query(F.data == "skip_github", StateFilter(Onboarding.awaiting_github_username))
async def cb_skip_github(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    team_id = data.get("team_id")
    await state.clear()
    await callback.message.edit_text("Ок, пропускаем GitHub.")
    await _finish_github_username(callback.message, team_id, None)
    await callback.answer()
