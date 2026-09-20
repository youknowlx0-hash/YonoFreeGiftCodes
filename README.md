# Advanced Force-Join Telegram Bot

Features:
- Up to 4 force-join buttons
- Public/private invite links and Telegram folder links can be displayed
- Configurable force-join photo + message
- "I've Joined — Verify" button
- Configurable post-verification offer message
- UID submission -> notification to every admin
- In-bot admin panel
- Add/delete channel buttons without editing code
- User and submission statistics
- Railway/GitHub friendly

## Important Telegram limitation
A bot cannot reliably verify that a user joined an entire Telegram folder. Folder links can be used as buttons, but actual membership verification should be done for individual channels where the bot has access.

For a channel you want verified:
1. Add the bot as an admin.
2. Put the numeric chat ID in the channel entry.
3. Keep the invite/public URL as the button URL.

## Railway
1. Create a GitHub repo and upload these files.
2. Create a Railway project and deploy from GitHub.
3. Add variables:
   - BOT_TOKEN
   - ADMIN_IDS (comma-separated numeric Telegram IDs)
   - DATABASE_URL=sqlite:///bot.db
4. Start command: `python bot.py` (or use the Procfile worker).
5. For persistent SQLite data, attach a Railway Volume and set:
   `DATABASE_URL=sqlite:////data/bot.db`

Never put a real bot token into GitHub.
