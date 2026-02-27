import logging
import asyncio
import re
import requests
import os
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InputFile
from aiogram.dispatcher.filters import CommandStart
from dotenv import load_dotenv
import yt_dlp

# Для Render Web Service
import http.server
import threading
import socketserver
from http import HTTPStatus

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Временная директория для файлов
DOWNLOAD_DIR = Path("/tmp")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Максимальный размер файла для Telegram (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Функция для очистки старых файлов
def cleanup_old_files(max_age_minutes: int = 60):
    """Удаляет файлы старше max_age_minutes минут"""
    try:
        current_time = time.time()
        for file_path in DOWNLOAD_DIR.glob("*.mp3"):
            file_age = current_time - file_path.stat().st_mtime
            if file_age > max_age_minutes * 60:
                file_path.unlink()
                logger.info(f"Удален старый файл: {file_path}")
    except Exception as e:
        logger.error(f"Ошибка при очистке файлов: {e}")

# Получение названия трека из Spotify
def get_spotify_track_info(url: str) -> dict | None:
    """Парсит страницу Spotify и возвращает информацию о треке"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        html = response.text

        title_match = re.search(r'<title>(.*?)</title>', html)
        if not title_match:
            return None

        full_title = title_match.group(1)
        full_title = full_title.replace(" | Spotify", "").strip()
        
        if " · " in full_title:
            artist, track = full_title.split(" · ", 1)
            return {
                "artist": artist,
                "track": track,
                "search_query": f"{artist} - {track}"
            }
        else:
            return {
                "artist": None,
                "track": full_title,
                "search_query": full_title
            }

    except Exception as e:
        logger.error(f"Ошибка получения информации из Spotify: {e}")
        return None

def get_file_size(file_path: str) -> int:
    return os.path.getsize(file_path)

# УЛУЧШЕННАЯ ФУНКЦИЯ СКАЧИВАНИЯ
def download_audio(url: str) -> str | None:
    """Скачивает аудио с YouTube или ищет трек по названию из Spotify"""
    
    timestamp = int(time.time())
    output_template = str(DOWNLOAD_DIR / f"audio_{timestamp}_%(title)s.%(ext)s")
    
    # РАБОЧИЕ НАСТРОЙКИ ДЛЯ YT-DLP
    ydl_opts = {
        # Формат: пробуем разные варианты
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': output_template,
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        
        # Конвертация в mp3
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        
        # Важные заголовки как у браузера
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
        },
        
        # Обход блокировок
        'ignoreerrors': True,
        'no_color': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        
        # Специально для YouTube
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
    }

    # Обработка Spotify
    if "spotify.com" in url:
        track_info = get_spotify_track_info(url)
        if not track_info:
            logger.error("❌ Не удалось получить информацию из Spotify")
            return None
        search_query = track_info['search_query']
        logger.info(f"🔍 Ищем на YouTube: {search_query}")
        url = f"ytsearch1:{search_query}"
        ydl_opts['default_search'] = 'ytsearch1'
    
    # Обработка плейлистов YouTube
    elif "list=" in url:
        logger.warning("📋 Обнаружен плейлист YouTube, скачиваю только первый трек")
        video_id_match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url)
        if video_id_match:
            url = f"https://youtube.com/watch?v={video_id_match.group(1)}"
    
    try:
        logger.info(f"⏬ Начинаю скачивание: {url}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Пробуем скачать
            info = ydl.extract_info(url, download=True)
            
            # Если это поиск, берем первый результат
            if "entries" in info and info['entries']:
                info = info['entries'][0]
                logger.info(f"✅ Найдено: {info.get('title', 'Unknown')}")
            
            # Получаем имя файла
            filename = ydl.prepare_filename(info)
            mp3_filename = str(Path(filename).with_suffix(".mp3"))
            
            # Если файл не найден, ищем по паттерну
            if not os.path.exists(mp3_filename):
                mp3_files = list(DOWNLOAD_DIR.glob(f"audio_{timestamp}_*.mp3"))
                if mp3_files:
                    mp3_filename = str(mp3_files[0])
                else:
                    # Последняя надежда - ищем любой свежий mp3
                    mp3_files = list(DOWNLOAD_DIR.glob("*.mp3"))
                    mp3_files.sort(key=os.path.getmtime, reverse=True)
                    if mp3_files:
                        mp3_filename = str(mp3_files[0])
                    else:
                        raise FileNotFoundError("MP3 файл не найден")
            
            # Проверяем размер
            file_size = get_file_size(mp3_filename)
            if file_size > MAX_FILE_SIZE:
                logger.warning(f"⚠️ Файл слишком большой: {file_size / 1024 / 1024:.1f} MB")
                os.remove(mp3_filename)
                return "TOO_LARGE"
            
            logger.info(f"✅ Успешно скачано: {mp3_filename} ({file_size / 1024 / 1024:.1f} MB)")
            return mp3_filename

    except Exception as e:
        logger.error(f"❌ Ошибка при скачивании: {e}")
        
        # Пробуем альтернативный метод с минимальными опциями
        try:
            logger.info("🔄 Пробую альтернативный метод...")
            minimal_opts = {
                'format': 'bestaudio',
                'outtmpl': output_template,
                'noplaylist': True,
                'quiet': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
            }
            
            with yt_dlp.YoutubeDL(minimal_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if "entries" in info and info['entries']:
                    info = info['entries'][0]
                
                filename = ydl.prepare_filename(info)
                mp3_filename = str(Path(filename).with_suffix(".mp3"))
                
                if os.path.exists(mp3_filename):
                    logger.info(f"✅ Альтернативный метод сработал!")
                    return mp3_filename
        except:
            pass
        
        return None

# Стартовая команда
@dp.message_handler(commands=['start'])
async def start_handler(message: Message):
    await message.answer(
        "🎵 Привет! Я музыкальный бот.\n\n"
        "Отправь мне:\n"
        "• Ссылку на YouTube\n"
        "• Ссылку на Spotify\n"
        "• Название песни\n\n"
        "Я пришлю MP3!"
    )

# Обработка сообщений
@dp.message_handler()
async def handle_message(message: Message):
    cleanup_old_files()
    
    text = message.text.strip()
    
    if not text:
        await message.answer("Отправь ссылку или название песни")
        return
    
    wait_msg = await message.answer("⏳ Скачиваю... это может занять до минуты")
    
    try:
        is_url = any(x in text for x in ["youtube.com", "youtu.be", "spotify.com", "http"])
        
        if not is_url:
            search_query = f"ytsearch1:{text}"
            logger.info(f"Поиск по названию: {text}")
            file_path = download_audio(search_query)
        else:
            logger.info(f"Обработка ссылки: {text}")
            file_path = download_audio(text)
        
        if file_path == "TOO_LARGE":
            await message.answer("❌ Файл слишком большой (>50 MB). Telegram не позволяет отправлять такие файлы.")
            await wait_msg.delete()
            return
        
        if not file_path or not os.path.exists(file_path):
            await message.answer("❌ Не удалось скачать аудио. Попробуй другую ссылку или название.")
            await wait_msg.delete()
            return
        
        audio = InputFile(file_path)
        await message.answer_audio(
            audio=audio,
            title=Path(file_path).stem.replace(f"audio_{int(time.time())}_", ""),
            performer="🎵 La Sekilé Bot"
        )
        
        # Удаляем файл после отправки
        try:
            os.remove(file_path)
            logger.info(f"Файл удален: {file_path}")
        except:
            pass
        
        await wait_msg.delete()
        
    except Exception as e:
        logger.error(f"Ошибка в обработчике: {e}")
        await message.answer(f"❌ Произошла ошибка: {str(e)[:100]}")
        await wait_msg.delete()

# HTTP сервер для Render
class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(HTTPStatus.OK)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get('PORT', 10000))
    handler = HealthCheckHandler
    httpd = socketserver.TCPServer(("0.0.0.0", port), handler)
    logger.info(f"Health check server running on port {port}")
    httpd.serve_forever()

# Запускаем HTTP сервер в отдельном потоке
threading.Thread(target=run_health_server, daemon=True).start()

# Запуск бота
if __name__ == "__main__":
    from aiogram import executor
    
    # Сбрасываем вебхуки перед запуском
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))
    
    logger.info("🚀 Бот запускается...")
    executor.start_polling(dp, skip_updates=True)