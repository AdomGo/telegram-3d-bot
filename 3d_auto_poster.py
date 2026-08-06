#!/usr/bin/env python3
"""
3D Auto Poster — Telegram-бот для автоматической публикации 3D-моделей.
Парсит Printables, Thingiverse, MakerWorld, Creality Cloud.
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import random
import sqlite3
import logging
import hashlib
import asyncio
import threading
import traceback
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import schedule
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ═══════════════════════════════════════════════════════════════════════
# ЛОГИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════════
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(message)s"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("3D_AutoPoster")


# ═══════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════
class Config:
    BOT_TOKEN: str        = "8517153978:AAGNMGbzhu-saXIRqvbXMG0Vn56AbbcHxOY"
    CHANNEL_ID: str       = "@TREEDSTL"
    POST_START_HOUR: int  = 9
    POST_END_HOUR: int    = 21
    POST_INTERVAL_MINUTES: int = 60
    REQUEST_TIMEOUT: int  = 30
    MAX_RETRIES: int      = 3
    PORT: int             = 10000
    MAX_DOWNLOAD_SIZE: int = 47185920

    @classmethod
    def validate(cls) -> List[str]:
        errors = []
        if not cls.BOT_TOKEN: errors.append("BOT_TOKEN не задан")
        if not cls.CHANNEL_ID: errors.append("CHANNEL_ID не задан")
        return errors


# ═══════════════════════════════════════════════════════════════════════
# БАЗА ДАННЫХ (SQLite)
# ═══════════════════════════════════════════════════════════════════════
class Database:
    DB_PATH: str = "posted_models.db"

    def __init__(self) -> None:
        self.conn = sqlite3.connect(self.DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS posted_models (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id    TEXT    NOT NULL,
                source      TEXT    NOT NULL,
                url         TEXT    NOT NULL,
                title       TEXT    DEFAULT '',
                posted_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model_id, source)
            );
        """)
        self.conn.commit()

    def is_posted(self, model_id: str, source: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM posted_models WHERE model_id = ? AND source = ?",
            (model_id, source),
        ).fetchone()
        return row is not None

    def mark_posted(self, model_id: str, source: str, url: str, title: str = "") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO posted_models (model_id, source, url, title) VALUES (?, ?, ?, ?)",
            (model_id, source, url, title),
        )
        self.conn.commit()

    def count_posted(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM posted_models").fetchone()
        return row["cnt"] if row else 0


# ═══════════════════════════════════════════════════════════════════════
# HTTP-КЛИЕНТ
# ═══════════════════════════════════════════════════════════════════════
class HttpClient:
    USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    ]

    def __init__(self, timeout: int = 30, max_retries: int = 3) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    def _base_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        }

    def get(self, url: str, **kwargs) -> requests.Response:
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs.setdefault("headers", self._base_headers())
                kwargs.setdefault("timeout", self.timeout)
                resp = self.session.get(url, **kwargs)
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                logger.warning("⚠️ Ошибка %d/%d для %s: %s", attempt, self.max_retries, url, e)
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
        raise last_exc  # type: ignore

    def download(self, url: str, max_size: int = 0) -> Optional[bytes]:
        try:
            resp = self.get(url, stream=True)
            content = bytearray()
            for chunk in resp.iter_content(chunk_size=16384):
                if chunk:
                    content.extend(chunk)
                    if max_size and len(content) > max_size:
                        return None
            return bytes(content)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════
# ГЕНЕРАТОР ОПИСАНИЙ
# ═══════════════════════════════════════════════════════════════════════
class DescriptionGenerator:
    def _template_based(self, title: str) -> Dict[str, Any]:
        clean_title = re.sub(r"[-_]+", " ", title).strip()
        clean_title = re.sub(r"\.(stl|obj|3mf|step|stp)$", "", clean_title, flags=re.IGNORECASE)
        if len(clean_title) > 60:
            clean_title = clean_title[:57] + "..."

        templates = [
            {
                "description": f"🔧 Отличная модель «{clean_title}» для 3D-печати!",
                "print_tips": ["Высота слоя: 0.2 мм", "Заполнение: 15-20%"],
            },
            {
                "description": f"✨ «{clean_title}» — стильная и функциональная 3D-модель.",
                "print_tips": ["Печатайте с brim (8-10 мм)", "PLA или PETG"],
            },
        ]
        tpl = random.choice(templates)
        return {
            "title": clean_title,
            "description": tpl["description"],
            "print_tips": tpl["print_tips"],
            "hashtags": ["#3Dпечать", "#3Dмодель", "#3DPrinting", "#DIY"],
        }

    def generate(self, image_url: str, fallback_title: str = "3D-модель") -> Dict[str, Any]:
        return self._template_based(fallback_title)


# ═══════════════════════════════════════════════════════════════════════
# ПАРСЕРЫ
# ═══════════════════════════════════════════════════════════════════════
class BaseScraper:
    SOURCE: str = "unknown"
    BASE_URL: str = ""
    MODELS_URL: str = ""

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def fetch_models(self, limit: int = 12) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @staticmethod
    def _make_id(url: str, prefix: str = "") -> str:
        if prefix:
            return f"{prefix}_{hashlib.sha256(url.encode()).hexdigest()[:12]}"
        return hashlib.sha256(url.encode()).hexdigest()[:12]

    @staticmethod
    def _normalize_image_url(raw: Optional[str], base_url: str) -> str:
        if not raw:
            return ""
        raw = raw.strip()
        if raw.startswith("http"):
            return raw
        if raw.startswith("//"):
            return "https:" + raw
        if raw.startswith("/"):
            return urljoin(base_url, raw)
        return urljoin(base_url, raw)


class PrintablesScraper(BaseScraper):
    SOURCE = "printables"
    BASE_URL = "https://www.printables.com"
    MODELS_URL = "https://www.printables.com/model?o=newest"

    def fetch_models(self, limit: int = 12) -> List[Dict[str, Any]]:
        models = []
        try:
            resp = self.http.get(self.MODELS_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("a[href*='/model/']")
            for card in cards:
                if len(models) >= limit:
                    break
                href = card.get("href", "")
                if not href:
                    continue
                url = urljoin(self.BASE_URL, href.split("?")[0])
                model_id = self._make_id(url, "pr")
                title = card.get_text(strip=True)[:60] or "3D-модель"
                img_el = card.select_one("img")
                image_url = self._normalize_image_url(
                    (img_el.get("src") or img_el.get("data-src")) if img_el else None,
                    self.BASE_URL,
                )
                models.append({
                    "model_id": model_id,
                    "source": self.SOURCE,
                    "title": title,
                    "url": url,
                    "image_url": image_url,
                    "download_url": f"{url}/download",
                })
        except Exception as e:
            logger.error("❌ Printables: %s", e)
        return models


class ThingiverseScraper(BaseScraper):
    SOURCE = "thingiverse"
    BASE_URL = "https://www.thingiverse.com"
    MODELS_URL = "https://www.thingiverse.com/explore/popular?page=1"

    def fetch_models(self, limit: int = 12) -> List[Dict[str, Any]]:
        models = []
        try:
            resp = self.http.get(self.MODELS_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("a[href*='/thing:']")
            for card in cards:
                if len(models) >= limit:
                    break
                href = card.get("href", "")
                if not href:
                    continue
                url = urljoin(self.BASE_URL, href.split("?")[0])
                model_id = self._make_id(url, "tv")
                title = card.get_text(strip=True)[:60] or "3D-модель"
                img_el = card.select_one("img")
                image_url = self._normalize_image_url(
                    (img_el.get("src") or img_el.get("data-src")) if img_el else None,
                    self.BASE_URL,
                )
                models.append({
                    "model_id": model_id,
                    "source": self.SOURCE,
                    "title": title,
                    "url": url,
                    "image_url": image_url,
                    "download_url": f"https://www.thingiverse.com/thing:{model_id}/zip",
                })
        except Exception as e:
            logger.error("❌ Thingiverse: %s", e)
        return models


class MakerWorldScraper(BaseScraper):
    SOURCE = "makerworld"
    BASE_URL = "https://makerworld.com"
    MODELS_URL = "https://makerworld.com/en/models?sort=newest"

    def fetch_models(self, limit: int = 12) -> List[Dict[str, Any]]:
        models = []
        try:
            headers = self.http._base_headers()
            headers.update({
                "Referer": "https://makerworld.com/",
                "Origin": "https://makerworld.com",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
            })
            resp = self.http.session.get(self.MODELS_URL, headers=headers, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("a[href*='/models/']")
            for card in cards:
                if len(models) >= limit:
                    break
                href = card.get("href", "")
                if not href:
                    continue
                url = urljoin(self.BASE_URL, href.split("?")[0])
                model_id = self._make_id(url, "mw")
                title = card.get_text(strip=True)[:60] or "3D-модель"
                img_el = card.select_one("img")
                image_url = self._normalize_image_url(
                    (img_el.get("src") or img_el.get("data-src")) if img_el else None,
                    self.BASE_URL,
                )
                models.append({
                    "model_id": model_id,
                    "source": self.SOURCE,
                    "title": title,
                    "url": url,
                    "image_url": image_url,
                    "download_url": f"{url}/download",
                })
        except Exception as e:
            logger.error("❌ MakerWorld: %s", e)
        return models


# ===== НОВЫЙ ПАРСЕР: CREALITY CLOUD =====
class CrealityCloudScraper(BaseScraper):
    SOURCE = "crealitycloud"
    BASE_URL = "https://www.crealitycloud.com"
    # Список моделей (страница всех моделей, сортировка по новизне)
    MODELS_URL = "https://www.crealitycloud.com/models?sort=latest"

    def fetch_models(self, limit: int = 12) -> List[Dict[str, Any]]:
        models = []
        try:
            resp = self.http.get(self.MODELS_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Пробуем найти карточки моделей. Селектор может отличаться, но обычно это ссылки на /model/...
            cards = soup.select("a[href*='/model/']")
            for card in cards:
                if len(models) >= limit:
                    break
                href = card.get("href", "")
                if not href:
                    continue
                # Нормализуем URL
                if not href.startswith("http"):
                    url = urljoin(self.BASE_URL, href.split("?")[0])
                else:
                    url = href.split("?")[0]
                model_id = self._make_id(url, "cc")
                title = card.get_text(strip=True)[:60] or "3D-модель"
                # Ищем превью-картинку внутри карточки
                img_el = card.select_one("img")
                image_url = self._normalize_image_url(
                    (img_el.get("src") or img_el.get("data-src")) if img_el else None,
                    self.BASE_URL,
                )
                # Ссылка на скачивание - обычно на странице модели есть кнопка Download, но для простоты используем URL страницы
                # Многие сайты позволяют скачать по ссылке /model/{id}/download
                download_url = f"{url}/download" if url.endswith('/model/') else f"{url}/download"
                models.append({
                    "model_id": model_id,
                    "source": self.SOURCE,
                    "title": title,
                    "url": url,
                    "image_url": image_url,
                    "download_url": download_url,
                })
        except Exception as e:
            logger.error("❌ Creality Cloud: %s", e)
        return models


# ═══════════════════════════════════════════════════════════════════════
# ПУБЛИКАЦИЯ В TELEGRAM
# ═══════════════════════════════════════════════════════════════════════
class TelegramPublisher:
    def __init__(self) -> None:
        self.bot = Bot(token=Config.BOT_TOKEN)

    async def publish(self, model: Dict[str, Any], description: Dict[str, Any]) -> bool:
        try:
            title = description.get("title", model.get("title", "3D-модель"))
            desc = description.get("description", "")
            tips = description.get("print_tips", [])
            hashtags = description.get("hashtags", ["#3Dпечать", "#3Dмодель"])
            url = model.get("url", "")
            source = model.get("source", "")

            lines = [
                f"<b>🚀 {title}</b>",
                "",
                desc,
                "",
            ]
            if tips:
                lines.append("<b>💡 Советы по печати:</b>")
                for tip in tips:
                    lines.append(f"  • {tip}")
                lines.append("")
            lines.append(f'🔗 <a href="{url}">Скачать на {source.capitalize()}</a>')
            lines.append("")
            lines.append(" ".join(hashtags))
            caption = "\n".join(lines)

            # Фото
            photo_url = model.get("image_url", "")
            if photo_url:
                await self.bot.send_photo(
                    chat_id=Config.CHANNEL_ID,
                    photo=photo_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await self.bot.send_message(
                    chat_id=Config.CHANNEL_ID,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                )

            # Файл
            download_url = model.get("download_url", "")
            if download_url:
                content = self._download_file(download_url)
                if content:
                    filename = f"{title[:30]}.zip"
                    await self.bot.send_document(
                        chat_id=Config.CHANNEL_ID,
                        document=BytesIO(content),
                        filename=filename,
                    )
            return True
        except Exception as e:
            logger.error("❌ Ошибка публикации: %s", e)
            return False

    def _download_file(self, url: str) -> Optional[bytes]:
        try:
            r = requests.get(url, timeout=30, stream=True)
            content = bytearray()
            for chunk in r.iter_content(chunk_size=16384):
                if chunk:
                    content.extend(chunk)
                    if len(content) > Config.MAX_DOWNLOAD_SIZE:
                        return None
            return bytes(content)
        except:
            return None


# ═══════════════════════════════════════════════════════════════════════
# ОРКЕСТРАТОР
# ═══════════════════════════════════════════════════════════════════════
class AutoPoster:
    def __init__(self) -> None:
        self.http = HttpClient(timeout=Config.REQUEST_TIMEOUT, max_retries=Config.MAX_RETRIES)
        self.db = Database()
        self.desc_gen = DescriptionGenerator()
        self.publisher = TelegramPublisher()
        self.scrapers = [
            PrintablesScraper(self.http),
            ThingiverseScraper(self.http),
            MakerWorldScraper(self.http),
            CrealityCloudScraper(self.http),  # Добавили новый парсер
        ]

    def find_and_post(self) -> bool:
        random.shuffle(self.scrapers)
        for scraper in self.scrapers:
            logger.info("🔍 Поиск на %s...", scraper.SOURCE)
            try:
                models = scraper.fetch_models(limit=15)
            except Exception as e:
                logger.error("❌ Ошибка получения моделей с %s: %s", scraper.SOURCE, e)
                continue
            if not models:
                logger.info("   Пустой результат на %s", scraper.SOURCE)
                continue
            random.shuffle(models)
            for model in models:
                model_id = model["model_id"]
                source = model["source"]
                title = model.get("title", "Без названия")
                if self.db.is_posted(model_id, source):
                    continue
                logger.info("   🎯 Новая модель: «%s» (%s)", title, source)
                description = self.desc_gen.generate(
                    image_url=model.get("image_url", ""),
                    fallback_title=title,
                )
                try:
                    success = asyncio.run(self.publisher.publish(model, description))
                except:
                    success = False
                if success:
                    self.db.mark_posted(model_id, source, model.get("url", ""), title)
                    return True
        return False


# ═══════════════════════════════════════════════════════════════════════
# ВЕБ-СЕРВЕР
# ═══════════════════════════════════════════════════════════════════════
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"3D Auto Poster is running!\n")


def run_webserver(port: int) -> None:
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info("🌐 Веб-сервер запущен на порту %d", port)
        server.serve_forever()
    except Exception as e:
        logger.error("Ошибка веб-сервера: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# ПЛАНИРОВЩИК
# ═══════════════════════════════════════════════════════════════════════
def job(poster: AutoPoster) -> None:
    now = datetime.now()
    if Config.POST_START_HOUR <= now.hour <= Config.POST_END_HOUR:
        logger.info("⏰ Запуск публикации по расписанию...")
        poster.find_and_post()
    else:
        logger.info("⏸ Пропуск: вне диапазона %d:00–%d:00", Config.POST_START_HOUR, Config.POST_END_HOUR)


def run_scheduler(poster: AutoPoster) -> None:
    schedule.every().hour.at(":00").do(job, poster)
    logger.info("📅 Планировщик запущен (9:00–21:00)")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ═══════════════════════════════════════════════════════════════════════
# ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════════
def main() -> None:
    print("═" * 60)
    print("🚀 3D Auto Poster (с Creality Cloud)")
    print("═" * 60)

    errors = Config.validate()
    if errors:
        for e in errors:
            print(f"❌ {e}")
        sys.exit(1)

    poster = AutoPoster()
    logger.info("📊 Ранее опубликовано: %d моделей", poster.db.count_posted())

    threading.Thread(target=run_webserver, args=(Config.PORT,), daemon=True).start()
    run_scheduler(poster)


if __name__ == "__main__":
    main()
