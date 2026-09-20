import json
import os
import aiosqlite
from urllib.parse import urlparse

DEFAULT_FORCE_TEXT = (
    "🔥 <b>Welcome!</b>\n\n"
    "To continue, join all required channels below and then tap <b>I've Joined — Verify</b>."
)
DEFAULT_GIFT_TEXT = (
    "🎁 <b>YONO Gift Codes</b>\n\n"
    "Register using this link:\n"
    "https://example.com/register\n\n"
    "After registration, send your UID here. Your UID will be forwarded to the admin for manual processing."
)

class DB:
    def __init__(self, url):
        self.url = url

    def sqlite_path(self):
        if self.url.startswith("sqlite:///"):
            return self.url.replace("sqlite:///", "", 1)
        return "bot.db"

    async def init(self):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )""")
            await db.execute("""CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                chat_id TEXT DEFAULT ''
            )""")
            await db.execute("""CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            await db.execute("""CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                uid TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            for k, v in [
                ("force_text", DEFAULT_FORCE_TEXT),
                ("force_photo", ""),
                ("gift_text", DEFAULT_GIFT_TEXT),
            ]:
                await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k,v))
            await db.commit()

    async def get_setting(self, key):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
            return row[0] if row else ""

    async def set_setting(self, key, value):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            await db.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value)
            )
            await db.commit()

    async def get_settings(self):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            cur = await db.execute("SELECT key,value FROM settings")
            settings = {k:v for k,v in await cur.fetchall()}
            cur = await db.execute("SELECT id,title,url,chat_id FROM channels ORDER BY id")
            channels = [
                {"id":r[0], "title":r[1], "url":r[2], "chat_id":r[3]}
                for r in await cur.fetchall()
            ]
            settings["channels"] = channels
            return settings

    async def add_channel(self, title, url, chat_id=""):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            await db.execute("INSERT INTO channels(title,url,chat_id) VALUES(?,?,?)", (title,url,chat_id))
            await db.commit()

    async def delete_channel(self, channel_id):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            await db.execute("DELETE FROM channels WHERE id=?", (channel_id,))
            await db.commit()

    async def upsert_user(self, user_id, name, username):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            await db.execute(
                "INSERT INTO users(user_id,name,username) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username",
                (user_id,name,username)
            )
            await db.commit()

    async def save_submission(self, user_id, uid):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            await db.execute("INSERT INTO submissions(user_id,uid) VALUES(?,?)", (user_id,uid))
            await db.commit()

    async def stats(self):
        async with aiosqlite.connect(self.sqlite_path()) as db:
            a = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
            b = await (await db.execute("SELECT COUNT(*) FROM submissions")).fetchone()
            return {"users": a[0], "submissions": b[0]}
