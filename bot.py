import os
import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from db import DB

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
DB_URL = os.getenv("DATABASE_URL", "sqlite:///bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is missing")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
db = DB(DB_URL)

class AdminStates(StatesGroup):
    waiting_message = State()
    waiting_photo = State()
    waiting_channel = State()
    waiting_remove_channel = State()
    waiting_link = State()
    waiting_gift_text = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_settings():
    return await db.get_settings()

async def force_join_keyboard(settings):
    rows = []
    for ch in settings["channels"]:
        rows.append([InlineKeyboardButton(text=ch["title"], url=ch["url"])])
    rows.append([InlineKeyboardButton(text="✅ I've Joined — Verify", callback_data="verify_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def check_membership(user_id: int, settings) -> bool:
    # Telegram can verify membership for normal/private channels when the bot
    # has access to the channel. Folder links are not directly checkable.
    for ch in settings["channels"]:
        chat_id = ch.get("chat_id")
        if not chat_id:
            continue
        try:
            member = await bot.get_chat_member(chat_id=int(chat_id), user_id=user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logging.warning("Membership check failed for %s: %s", chat_id, e)
            # If a channel cannot be checked, do not silently block the user.
            continue
    return True

async def send_force_join(message: Message):
    settings = await get_settings()
    kb = await force_join_keyboard(settings)
    text = settings["force_text"]
    photo = settings.get("force_photo")
    if photo:
        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)

async def send_main_offer(user_id: int):
    settings = await get_settings()
    await bot.send_message(
        user_id,
        settings["gift_text"],
        disable_web_page_preview=False
    )

@dp.message(CommandStart())
async def start(message: Message):
    await db.upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    settings = await get_settings()
    if await check_membership(message.from_user.id, settings):
        await send_main_offer(message.from_user.id)
    else:
        await send_force_join(message)

@dp.callback_query(F.data == "verify_join")
async def verify_join(callback: CallbackQuery):
    settings = await get_settings()
    if await check_membership(callback.from_user.id, settings):
        await callback.message.answer(settings["gift_text"])
        await callback.answer("Verified ✅")
    else:
        await callback.answer("Please join all required channels first.", show_alert=True)

@dp.message(F.text)
async def receive_uid(message: Message):
    if message.text.startswith("/"):
        return
    settings = await get_settings()
    if not await check_membership(message.from_user.id, settings):
        await send_force_join(message)
        return

    uid = message.text.strip()
    if 3 <= len(uid) <= 100:
        await db.save_submission(message.from_user.id, uid)
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"📥 <b>New UID Submission</b>\n\n"
                    f"👤 Name: {message.from_user.full_name}\n"
                    f"🔹 Username: @{message.from_user.username or 'N/A'}\n"
                    f"🆔 User ID: <code>{message.from_user.id}</code>\n"
                    f"🎮 UID: <code>{uid}</code>"
                )
            except Exception:
                pass
        await message.answer("✅ UID received. Admin has been notified.")
    else:
        await message.answer("Please send a valid UID.")

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Force-Join Text", callback_data="a_force_text")],
        [InlineKeyboardButton(text="🖼 Force-Join Photo", callback_data="a_force_photo")],
        [InlineKeyboardButton(text="📢 Channels / Buttons", callback_data="a_channels")],
        [InlineKeyboardButton(text="🎁 Offer Message", callback_data="a_gift_text")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="a_stats")],
    ])
    await message.answer("⚙️ <b>Bot Admin Panel</b>\n\nEverything important can be changed here.", reply_markup=kb)

@dp.callback_query(F.data == "a_force_text")
async def a_force_text(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(AdminStates.waiting_message)
    await c.message.answer("Send the new force-join message. HTML formatting is supported.")

@dp.message(AdminStates.waiting_message)
async def save_force_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await db.set_setting("force_text", message.text)
    await state.clear()
    await message.answer("✅ Force-join message updated.")

@dp.callback_query(F.data == "a_force_photo")
async def a_force_photo(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(AdminStates.waiting_photo)
    await c.message.answer("Send the new photo. Send /remove_photo to remove it.")

@dp.message(AdminStates.waiting_photo)
async def save_force_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    if message.text == "/remove_photo":
        await db.set_setting("force_photo", "")
        await state.clear()
        await message.answer("✅ Photo removed.")
        return
    if not message.photo:
        await message.answer("Please send a photo.")
        return
    await db.set_setting("force_photo", message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ Force-join photo updated.")

@dp.callback_query(F.data == "a_gift_text")
async def a_gift_text(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(AdminStates.waiting_gift_text)
    await c.message.answer("Send the message users should receive after verification.")

@dp.message(AdminStates.waiting_gift_text)
async def save_gift_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await db.set_setting("gift_text", message.text)
    await state.clear()
    await message.answer("✅ Offer message updated.")

@dp.callback_query(F.data == "a_channels")
async def a_channels(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    settings = await get_settings()
    rows = []
    for ch in settings["channels"]:
        rows.append([
            InlineKeyboardButton(text=f"✏️ {ch['title']}", callback_data=f"edit_ch:{ch['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"del_ch:{ch['id']}")
        ])
    if len(settings["channels"]) < 4:
        rows.append([InlineKeyboardButton(text="➕ Add Channel", callback_data="add_ch")])
    rows.append([InlineKeyboardButton(text="🔙 Admin", callback_data="back_admin")])
    await c.message.answer("📢 <b>Channels</b>\nMax 4 entries. A link can be public, private invite, or a Telegram folder link.", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data == "add_ch")
async def add_ch(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    settings = await get_settings()
    if len(settings["channels"]) >= 4:
        await c.answer("Maximum 4 channels.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_channel)
    await c.message.answer(
        "Send one line in this format:\n"
        "<code>Button Name | https://t.me/... | CHAT_ID(optional)</code>\n\n"
        "For membership verification, add the numeric chat ID and make the bot an admin in that channel.\n"
        "For folder links, leave CHAT_ID empty; Telegram does not expose folder membership to bots."
    )

@dp.message(AdminStates.waiting_channel)
async def save_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) < 2:
        await message.answer("Format: Button Name | https://t.me/... | CHAT_ID(optional)")
        return
    title, url = parts[0], parts[1]
    chat_id = parts[2] if len(parts) > 2 else ""
    settings = await get_settings()
    if len(settings["channels"]) >= 4:
        await state.clear()
        await message.answer("Maximum 4 channels.")
        return
    await db.add_channel(title, url, chat_id)
    await state.clear()
    await message.answer("✅ Channel/button added.")

@dp.callback_query(F.data.startswith("del_ch:"))
async def del_ch(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    cid = int(c.data.split(":")[1])
    await db.delete_channel(cid)
    await c.answer("Deleted.")
    await a_channels(c)

@dp.callback_query(F.data == "a_stats")
async def a_stats(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    s = await db.stats()
    await c.message.answer(
        f"📊 <b>Stats</b>\n\n"
        f"👥 Users: <b>{s['users']}</b>\n"
        f"📥 UID submissions: <b>{s['submissions']}</b>"
    )

@dp.callback_query(F.data == "back_admin")
async def back_admin(c: CallbackQuery):
    if not is_admin(c.from_user.id): return
    await c.message.answer("Use /admin to open the panel.")

async def main():
    await db.init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
