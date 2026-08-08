import asyncio
import hashlib
import html
import os
import re
import sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from aiogram import Bot

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.getenv("CHANNEL_ID", "@upravaktiv")
DB_PATH = "published.sqlite3"
FEEDS = [x.strip() for x in os.getenv("RSS_FEEDS", "https://www.vedomosti.ru/rss/rubric/realty").split(";") if x.strip()]
KEYWORDS = [
    "коммерческая недвижимость", "офис", "офисы", "бизнес-центр", "бизнес центр", "бц",
    "мфк", "многофункциональный комплекс", "торговый центр", "торговый комплекс", "ритейл",
    "инвестици", "зпиф", "паевой инвестиционный фонд", "аренда офис", "девелопмент",
    "сделка с недвижимостью", "доходност", "вакантност", "бизнес-парк"
]


def clean(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def key(entry):
    return hashlib.sha256((entry.get("link") or entry.get("title", "")).encode()).hexdigest()


def relevant(entry):
    text = clean(" ".join([entry.get("title", ""), entry.get("summary", ""), entry.get("description", "")])).lower()
    return any(word in text for word in KEYWORDS)


def date_of(entry):
    try:
        return parsedate_to_datetime(entry.get("published", "")).astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    except Exception:
        return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def post(entry, feed_url):
    title = clean(entry.get("title", "Без заголовка"))
    summary = clean(entry.get("summary") or entry.get("description") or "")[:600]
    link = entry.get("link", "")
    source = feed_url.split("/")[2]
    text = f"<b>{html.escape(title)}</b>\n\n"
    if summary:
        text += html.escape(summary) + "\n\n"
    text += f"Источник: {html.escape(source)}\nДата: {date_of(entry)}"
    if link:
        text += f'\n<a href="{html.escape(link, quote=True)}">Читать оригинал</a>'
    return text


def main():
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS published (item_key TEXT PRIMARY KEY)")
    items = []
    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            item_key = key(entry)
            exists = db.execute("SELECT 1 FROM published WHERE item_key=?", (item_key,)).fetchone()
            if relevant(entry) and not exists:
                items.append((entry, feed_url, item_key))

    async def publish():
        bot = Bot(BOT_TOKEN)
        try:
            for entry, feed_url, item_key in items:
                await bot.send_message(CHANNEL_ID, post(entry, feed_url), disable_web_page_preview=False)
                db.execute("INSERT OR IGNORE INTO published(item_key) VALUES (?)", (item_key,))
                db.commit()
                await asyncio.sleep(1)
        finally:
            await bot.session.close()

    try:
        asyncio.run(publish())
    finally:
        db.close()


if __name__ == "__main__":
    main()
