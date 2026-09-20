import os
import asyncio
import logging
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from db import DB


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///bot.db"
).strip()


def parse_admin_ids(raw):
    ids = set()

    raw = raw.replace(";", ",")

    for value in raw.split(","):
        value = value.strip()

        if value.isdigit():
            ids.add(int(value))

    return ids


ADMIN_IDS = parse_admin_ids(ADMIN_IDS_RAW)


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add it in Railway Variables."
    )


if not ADMIN_IDS:
    raise RuntimeError(
        "ADMIN_IDS is missing/invalid. "
        "Add your numeric Telegram ID."
    )


bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher(
    storage=MemoryStorage()
)

db = DB(DATABASE_URL)


# =========================
# STATES
# =========================

class AdminState(StatesGroup):

    force_text = State()

    force_photo = State()

    gift_text = State()

    add_channel = State()

    edit_channel = State()


# =========================
# HELPERS
# =========================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📝 Force-Join Message",
                    callback_data="admin:force_text"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🖼 Force-Join Photo",
                    callback_data="admin:force_photo"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📢 Manage Channels",
                    callback_data="admin:channels"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🎁 Offer Message",
                    callback_data="admin:gift"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📊 Statistics",
                    callback_data="admin:stats"
                )
            ],

            [
                InlineKeyboardButton(
                    text="👁 Preview",
                    callback_data="admin:preview"
                )
            ]

        ]
    )


def back_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="admin:back"
                )
            ]

        ]
    )


async def send_admin_panel(message):

    await message.answer(
        "⚙️ <b>ADMIN PANEL</b>\n\n"
        "Bot settings yahin se manage karo:",
        reply_markup=admin_keyboard()
    )


# =========================
# FORCE JOIN
# =========================

async def force_keyboard():

    settings = await db.get_settings()

    rows = []

    for channel in settings["channels"]:

        rows.append(
            [
                InlineKeyboardButton(
                    text=channel["title"],
                    url=channel["url"]
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="✅ I've Joined — Verify",
                callback_data="verify"
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


async def membership_ok(user_id):

    settings = await db.get_settings()

    if not settings["channels"]:
        return True

    for channel in settings["channels"]:

        chat_id = str(
            channel.get("chat_id", "")
        ).strip()

        # URL-only button
        if not chat_id:
            continue

        try:

            member = await bot.get_chat_member(
                chat_id=int(chat_id),
                user_id=user_id
            )

            if member.status in (
                "left",
                "kicked"
            ):
                return False

        except Exception:

            logging.exception(
                "Membership check failed: %s",
                chat_id
            )

            return False

    return True


async def show_force_join(user_id):

    settings = await db.get_settings()

    keyboard = await force_keyboard()

    text = settings.get(
        "force_text"
    ) or "Please join the required channels."

    photo = settings.get(
        "force_photo"
    )

    if photo:

        await bot.send_photo(
            user_id,
            photo,
            caption=text,
            reply_markup=keyboard
        )

    else:

        await bot.send_message(
            user_id,
            text,
            reply_markup=keyboard
        )


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    await db.upsert_user(
        message.from_user.id,
        message.from_user.full_name,
        message.from_user.username
    )

    if await membership_ok(
        message.from_user.id
    ):

        settings = await db.get_settings()

        await message.answer(
            settings["gift_text"]
        )

        if is_admin(
            message.from_user.id
        ):

            await message.answer(
                "⚙️ Admin account detected.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚙️ Open Admin Panel",
                                callback_data="admin:open"
                            )
                        ]
                    ]
                )
            )

    else:

        await show_force_join(
            message.from_user.id
        )


# =========================
# ADMIN COMMAND
# =========================

@dp.message(Command("admin"))
async def admin_command(message: Message):

    allowed = is_admin(
        message.from_user.id
    )

    logging.info(
        "ADMIN COMMAND | user_id=%s | allowed=%s | configured=%s",
        message.from_user.id,
        allowed,
        sorted(ADMIN_IDS)
    )

    if not allowed:

        await message.answer(
            "⛔ <b>Access denied.</b>\n\n"
            "Your Telegram ID:\n"
            f"<code>{message.from_user.id}</code>\n\n"
            "This ID is not configured as an admin."
        )

        return

    await send_admin_panel(
        message
    )


# Also allows typing "admin"
@dp.message(F.text.casefold() == "admin")
async def admin_text(message: Message):

    if not is_admin(
        message.from_user.id
    ):

        await message.answer(
            "⛔ Access denied."
        )

        return

    await send_admin_panel(
        message
    )


# =========================
# ADMIN OPEN / BACK
# =========================

@dp.callback_query(F.data == "admin:open")
async def admin_open(callback: CallbackQuery):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    await callback.message.edit_text(
        "⚙️ <b>ADMIN PANEL</b>\n\n"
        "Bot settings yahin se manage karo:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


@dp.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    await callback.message.edit_text(
        "⚙️ <b>ADMIN PANEL</b>\n\n"
        "Bot settings yahin se manage karo:",
        reply_markup=admin_keyboard()
    )

    await callback.answer()


# =========================
# VERIFY
# =========================

@dp.callback_query(F.data == "verify")
async def verify(callback: CallbackQuery):

    ok = await membership_ok(
        callback.from_user.id
    )

    if ok:

        settings = await db.get_settings()

        await callback.message.answer(
            settings["gift_text"]
        )

        await callback.answer(
            "Verified ✅"
        )

    else:

        await callback.answer(
            "Please join all required channels first.",
            show_alert=True
        )


# =========================
# FORCE MESSAGE
# =========================

@dp.callback_query(F.data == "admin:force_text")
async def force_text_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    current = await db.get_setting(
        "force_text"
    )

    await state.set_state(
        AdminState.force_text
    )

    await callback.message.edit_text(
        "📝 <b>Force-Join Message</b>\n\n"
        "Current message:\n\n"
        f"{current}\n\n"
        "Send the new message now.\n"
        "HTML formatting supported.\n\n"
        "Use /cancel to cancel.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(AdminState.force_text)
async def force_text_save(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    if message.text == "/cancel":

        await state.clear()

        await send_admin_panel(
            message
        )

        return

    await db.set_setting(
        "force_text",
        message.text
    )

    await state.clear()

    await message.answer(
        "✅ Force-join message updated.",
        reply_markup=admin_keyboard()
    )


# =========================
# FORCE PHOTO
# =========================

@dp.callback_query(F.data == "admin:force_photo")
async def force_photo_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    await state.set_state(
        AdminState.force_photo
    )

    await callback.message.edit_text(
        "🖼 <b>Force-Join Photo</b>\n\n"
        "Send a photo now.\n\n"
        "Send /remove_photo to remove it.\n"
        "Use /cancel to cancel.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(AdminState.force_photo)
async def force_photo_save(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    if message.text == "/cancel":

        await state.clear()

        await send_admin_panel(
            message
        )

        return

    if message.text == "/remove_photo":

        await db.set_setting(
            "force_photo",
            ""
        )

        await state.clear()

        await message.answer(
            "✅ Force-join photo removed.",
            reply_markup=admin_keyboard()
        )

        return

    if not message.photo:

        await message.answer(
            "Please send a photo or /cancel."
        )

        return

    file_id = message.photo[-1].file_id

    await db.set_setting(
        "force_photo",
        file_id
    )

    await state.clear()

    await message.answer(
        "✅ Force-join photo updated.",
        reply_markup=admin_keyboard()
    )


# =========================
# OFFER MESSAGE
# =========================

@dp.callback_query(F.data == "admin:gift")
async def gift_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    current = await db.get_setting(
        "gift_text"
    )

    await state.set_state(
        AdminState.gift_text
    )

    await callback.message.edit_text(
        "🎁 <b>Offer Message</b>\n\n"
        f"Current:\n{current}\n\n"
        "Send the new message.\n\n"
        "Use /cancel to cancel.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(AdminState.gift_text)
async def gift_save(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    if message.text == "/cancel":

        await state.clear()

        await send_admin_panel(
            message
        )

        return

    await db.set_setting(
        "gift_text",
        message.text
    )

    await state.clear()

    await message.answer(
        "✅ Offer message updated.",
        reply_markup=admin_keyboard()
    )


# =========================
# CHANNEL MENU
# =========================

async def show_channels(
    target
):

    settings = await db.get_settings()

    rows = []

    for channel in settings["channels"]:

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {channel['title']}",
                    callback_data=f"admin:edit:{channel['id']}"
                ),

                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"admin:delete:{channel['id']}"
                )
            ]
        )

    if len(settings["channels"]) < 4:

        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Add Channel",
                    callback_data="admin:add_channel"
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data="admin:back"
            )
        ]
    )

    text = (
        "📢 <b>MANAGE CHANNELS</b>\n\n"
        f"Configured: <b>{len(settings['channels'])}/4</b>\n\n"
        "Format:\n"
        "<code>Button Name | Link | Chat ID</code>\n\n"
        "Chat ID optional."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=rows
    )

    if isinstance(
        target,
        CallbackQuery
    ):

        await target.message.edit_text(
            text,
            reply_markup=keyboard
        )

    else:

        await target.answer(
            text,
            reply_markup=keyboard
        )


@dp.callback_query(F.data == "admin:channels")
async def channels_menu(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    await show_channels(
        callback
    )

    await callback.answer()


# =========================
# ADD CHANNEL
# =========================

@dp.callback_query(F.data == "admin:add_channel")
async def add_channel_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    settings = await db.get_settings()

    if len(settings["channels"]) >= 4:

        await callback.answer(
            "Maximum 4 buttons.",
            show_alert=True
        )

        return

    await state.set_state(
        AdminState.add_channel
    )

    await callback.message.edit_text(
        "➕ <b>Add Channel Button</b>\n\n"
        "Example:\n"
        "<code>Channel 1 | https://t.me/example | -1001234567890</code>\n\n"
        "URL-only:\n"
        "<code>Channel 1 | https://t.me/example</code>\n\n"
        "Use /cancel to cancel.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


def parse_channel(text):

    parts = [
        x.strip()
        for x in text.split("|")
    ]

    if len(parts) not in (2, 3):
        return None

    title = parts[0]
    url = parts[1]

    chat_id = (
        parts[2]
        if len(parts) == 3
        else ""
    )

    if not title or not url:
        return None

    if not (
        url.startswith("https://t.me/")
        or url.startswith("http://t.me/")
        or url.startswith("https://telegram.me/")
        or url.startswith("http://telegram.me/")
    ):
        return None

    return title, url, chat_id


@dp.message(AdminState.add_channel)
async def add_channel_save(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    if message.text == "/cancel":

        await state.clear()

        await send_admin_panel(
            message
        )

        return

    parsed = parse_channel(
        message.text or ""
    )

    if not parsed:

        await message.answer(
            "❌ Invalid format.\n\n"
            "Example:\n"
            "<code>Channel 1 | https://t.me/example | -1001234567890</code>"
        )

        return

    settings = await db.get_settings()

    if len(settings["channels"]) >= 4:

        await state.clear()

        await message.answer(
            "Maximum 4 channels.",
            reply_markup=admin_keyboard()
        )

        return

    await db.add_channel(
        *parsed
    )

    await state.clear()

    await message.answer(
        "✅ Channel button added.",
        reply_markup=admin_keyboard()
    )


# =========================
# EDIT CHANNEL
# =========================

@dp.callback_query(
    F.data.startswith("admin:edit:")
)
async def edit_channel_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    channel_id = int(
        callback.data.split(":")[-1]
    )

    settings = await db.get_settings()

    channel = next(
        (
            x for x in settings["channels"]
            if x["id"] == channel_id
        ),
        None
    )

    if not channel:

        await callback.answer(
            "Channel not found.",
            show_alert=True
        )

        return

    await state.set_state(
        AdminState.edit_channel
    )

    await state.update_data(
        channel_id=channel_id
    )

    await callback.message.edit_text(
        "✏️ <b>Edit Channel</b>\n\n"
        f"Current: <b>{escape(channel['title'])}</b>\n"
        f"{escape(channel['url'])}\n"
        f"Chat ID: <code>{escape(channel['chat_id'])}</code>\n\n"
        "Send:\n"
        "<code>Button Name | Link | Chat ID</code>",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(AdminState.edit_channel)
async def edit_channel_save(
    message: Message,
    state: FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return

    if message.text == "/cancel":

        await state.clear()

        await send_admin_panel(
            message
        )

        return

    parsed = parse_channel(
        message.text or ""
    )

    if not parsed:

        await message.answer(
            "❌ Invalid format."
        )

        return

    data = await state.get_data()

    await db.update_channel(
        data["channel_id"],
        *parsed
   )

    await state.clear()

    await message.answer(
        "✅ Channel updated.",
        reply_markup=admin_keyboard()
    )


# =========================
# DELETE CHANNEL
# =========================

@dp.callback_query(
    F.data.startswith("admin:delete:")
)
async def delete_channel(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    channel_id = int(
        callback.data.split(":")[-1]
    )

    await db.delete_channel(
        channel_id
    )

    await callback.answer(
        "Deleted ✅"
    )

    await show_channels(
        callback
    )


# =========================
# STATISTICS
# =========================

@dp.callback_query(F.data == "admin:stats")
async def stats(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    data = await db.stats()

    await callback.message.edit_text(
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Users: <b>{data['users']}</b>\n"
        f"🆔 UID submissions: <b>{data['submissions']}</b>\n"
        f"📢 Join buttons: <b>{data['channels']}/4</b>",
        reply_markup=back_keyboard()
    )

    await callback.answer()


# =========================
# PREVIEW
# =========================

@dp.callback_query(F.data == "admin:preview")
async def preview(
    callback: CallbackQuery
):

    if not is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "Access denied.",
            show_alert=True
        )

        return

    await callback.answer(
        "Preview sent."
    )

    await show_force_join(
        callback.from_user.id
    )


# =========================
# UID
# =========================

@dp.message()
async def catch_uid(
    message: Message
):

    if (
        message.text
        and message.text.startswith("/")
    ):
        return

    if not message.text:
        return

    if is_admin(
        message.from_user.id
    ):
        return

    if not await membership_ok(
        message.from_user.id
    ):

        await show_force_join(
            message.from_user.id
        )

        return

    uid = message.text.strip()

    if len(uid) < 3 or len(uid) > 100:

        await message.answer(
            "❌ Please send a valid UID."
        )

        return

    await db.save_submission(
        message.from_user.id,
        uid
    )

    user = message.from_user

    username = (
        f"@{user.username}"
        if user.username
        else "No username"
    )

    notification = (
        "🆔 <b>NEW UID SUBMISSION</b>\n\n"
        f"👤 Name: {escape(user.full_name)}\n"
        f"🔗 Username: {escape(username)}\n"
        f"👤 User ID: <code>{user.id}</code>\n"
        f"🆔 UID: <code>{escape(uid)}</code>"
    )

    sent = 0

    for admin_id in ADMIN_IDS:

        try:

            await bot.send_message(
                admin_id,
                notification
            )

            sent += 1

        except Exception:

            logging.exception(
                "Could not notify admin %s",
                admin_id
            )

    if sent:

        await message.answer(
            "✅ UID received.\n\n"
            "It has been forwarded to the admin "
            "for manual handling."
        )

    else:

        await message.answer(
            "✅ UID received."
        )


# =========================
# START BOT
# =========================

async def main():

    await db.init()

    logging.info(
        "================================"
    )

    logging.info(
        "BOT STARTED"
    )

    logging.info(
        "DATABASE: %s",
        db.path
    )

    logging.info(
        "ADMIN IDS: %s",
        sorted(ADMIN_IDS)
    )

    logging.info(
        "================================"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
)
