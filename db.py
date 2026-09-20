import aiosqlite

DEFAULT_FORCE_TEXT = """🔥 <b>Welcome!</b>

Join all required channels below and then tap <b>I've Joined — Verify</b>."""

DEFAULT_GIFT_TEXT = """🎁 <b>Registration / Gift Code</b>

Register using the configured link, then send your UID here.

Your UID will be forwarded to the admin for manual handling."""


class DB:
    def __init__(self, url):
        self.path = (
            url.replace("sqlite:///", "", 1)
            if url.startswith("sqlite:///")
            else "bot.db"
        )

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS channels(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    chat_id TEXT DEFAULT ''
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS users(
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS submissions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    uid TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for key, value in [
                ("force_text", DEFAULT_FORCE_TEXT),
                ("force_photo", ""),
                ("gift_text", DEFAULT_GIFT_TEXT),
            ]:
                await db.execute(
                    "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                    (key, value)
                )

            await db.commit()

    async def get_setting(self, key):
        async with aiosqlite.connect(self.path) as db:
            row = await (
                await db.execute(
                    "SELECT value FROM settings WHERE key=?",
                    (key,)
                )
            ).fetchone()

            return row[0] if row else ""

    async def set_setting(self, key, value):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO settings(key,value) VALUES(?,?)
                ON CONFLICT(key)
                DO UPDATE SET value=excluded.value
            """, (key, value))

            await db.commit()

    async def get_settings(self):
        async with aiosqlite.connect(self.path) as db:
            settings = dict(
                await (
                    await db.execute(
                        "SELECT key,value FROM settings"
                    )
                ).fetchall()
            )

            rows = await (
                await db.execute(
                    "SELECT id,title,url,chat_id FROM channels ORDER BY id"
                )
            ).fetchall()

            settings["channels"] = [
                {
                    "id": row[0],
                    "title": row[1],
                    "url": row[2],
                    "chat_id": row[3] or ""
                }
                for row in rows
            ]

            return settings

    async def add_channel(self, title, url, chat_id=""):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO channels(title,url,chat_id) VALUES(?,?,?)",
                (title, url, chat_id)
            )
            await db.commit()

    async def update_channel(
        self,
        channel_id,
        title,
        url,
        chat_id=""
    ):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE channels
                SET title=?,url=?,chat_id=?
                WHERE id=?
                """,
                (title, url, chat_id, channel_id)
            )
            await db.commit()

    async def delete_channel(self, channel_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM channels WHERE id=?",
                (channel_id,)
            )
            await db.commit()

    async def upsert_user(
        self,
        user_id,
        name,
        username
    ):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO users(user_id,name,username)
                VALUES(?,?,?)

                ON CONFLICT(user_id)
                DO UPDATE SET
                    name=excluded.name,
                    username=excluded.username
            """, (
                user_id,
                name or "",
                username or ""
            ))

            await db.commit()

    async def save_submission(self, user_id, uid):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO submissions(user_id,uid) VALUES(?,?)",
                (user_id, uid)
            )
            await db.commit()

    async def stats(self):
        async with aiosqlite.connect(self.path) as db:
            users = await (
                await db.execute(
                    "SELECT COUNT(*) FROM users"
                )
            ).fetchone()

            submissions = await (
                await db.execute(
                    "SELECT COUNT(*) FROM submissions"
                )
            ).fetchone()

            channels = await (
                await db.execute(
                    "SELECT COUNT(*) FROM channels"
                )
            ).fetchone()

            return {
                "users": users[0],
                "submissions": submissions[0],
                "channels": channels[0]
            }
