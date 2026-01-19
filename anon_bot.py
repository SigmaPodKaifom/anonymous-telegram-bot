import asyncio
import sqlite3
import secrets
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования для Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Проверка обязательных переменных
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    # Не создаем бота, но создаем диспетчер для импорта
    bot = None
    dp = Dispatcher(storage=MemoryStorage())
else:
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)


# Состояния FSM для отправки анонимных сообщений
class SendAnonMessage(StatesGroup):
    waiting_for_anything = State()


# Функция для логирования
def log_anon_message(sender_id: int, sender_username: str, content_type: str,
                     content_info: str, recipient_id: int, link_code: str):
    """Логирует информацию об отправителе и сообщении"""
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        username_display = f"@{sender_username}" if sender_username else f"ID:{sender_id}"

        logger.info("=" * 50)
        logger.info(f"📨 АНОНИМНОЕ СООБЩЕНИЕ [{timestamp}]")
        logger.info(f"📤 ОТПРАВИТЕЛЬ: {username_display} (ID: {sender_id})")
        logger.info(f"📥 ПОЛУЧАТЕЛЬ: ID: {recipient_id}")
        logger.info(f"🔗 ССЫЛКА: {link_code}")
        logger.info(f"📄 ТИП: {content_type}")

        if content_type == "text":
            logger.info(f"💬 ТЕКСТ: {content_info}")
        else:
            logger.info(f"📁 ИНФО: {content_info}")

        logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Ошибка при логировании: {e}")


# Инициализация БД
def init_db():
    """Инициализация базы данных"""
    try:
        db_path = os.getenv("DB_PATH", "anon_bot.db")

        # На Render используем абсолютный путь и создаем директорию
        if 'RENDER' in os.environ or 'PORT' in os.environ:
            db_path = os.path.join(os.getcwd(), db_path)
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            logger.info(f"🗃️ Работаем на сервере, путь к БД: {db_path}")

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Таблица пользователей
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY,
                      username TEXT,
                      full_name TEXT,
                      created_at TEXT)''')

        # Таблица анонимных ссылок
        c.execute('''CREATE TABLE IF NOT EXISTS anon_links
                     (link_code TEXT PRIMARY KEY,
                      user_id INTEGER,
                      created_at TEXT,
                      is_active INTEGER DEFAULT 1,
                      FOREIGN KEY(user_id) REFERENCES users(user_id))''')

        # Таблица сообщений (для истории)
        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      link_code TEXT,
                      sender_id INTEGER,
                      sender_username TEXT,
                      content_type TEXT,
                      content_info TEXT,
                      timestamp TEXT)''')

        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return False


# Сохранение пользователя
def save_user(user: types.User):
    """Сохранение пользователя в БД"""
    try:
        db_path = os.getenv("DB_PATH", "anon_bot.db")
        if 'RENDER' in os.environ or 'PORT' in os.environ:
            db_path = os.path.join(os.getcwd(), db_path)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute('''INSERT OR REPLACE INTO users 
                     (user_id, username, full_name, created_at) 
                     VALUES (?, ?, ?, ?)''',
                  (user.id, user.username or '', user.full_name,
                   datetime.now().isoformat()))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения пользователя: {e}")


# Создание анонимной ссылки
def create_anon_link(user_id: int) -> str:
    """Создание анонимной ссылки для пользователя"""
    try:
        db_path = os.getenv("DB_PATH", "anon_bot.db")
        if 'RENDER' in os.environ or 'PORT' in os.environ:
            db_path = os.path.join(os.getcwd(), db_path)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("SELECT link_code FROM anon_links WHERE user_id = ? AND is_active = 1", (user_id,))
        existing = c.fetchone()

        if existing:
            conn.close()
            return existing[0]

        link_code = secrets.token_urlsafe(12)

        c.execute("INSERT INTO anon_links (link_code, user_id, created_at) VALUES (?, ?, ?)",
                  (link_code, user_id, datetime.now().isoformat()))

        conn.commit()
        conn.close()
        return link_code
    except Exception as e:
        logger.error(f"❌ Ошибка создания ссылки: {e}")
        # Возвращаем временную ссылку в случае ошибки
        return f"temp_{user_id}_{secrets.token_urlsafe(8)}"


# Получение владельца ссылки
def get_link_owner(link_code: str):
    """Получение ID владельца ссылки"""
    if not link_code:
        return None

    try:
        db_path = os.getenv("DB_PATH", "anon_bot.db")
        if 'RENDER' in os.environ or 'PORT' in os.environ:
            db_path = os.path.join(os.getcwd(), db_path)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Проверяем как обычную ссылку
        c.execute("SELECT user_id FROM anon_links WHERE link_code = ? AND is_active = 1", (link_code,))
        result = c.fetchone()

        # Если не нашли, проверяем как временную ссылку
        if not result and link_code.startswith("temp_"):
            # Извлекаем user_id из временной ссылки: temp_123456_abcdef
            parts = link_code.split("_")
            if len(parts) >= 2:
                try:
                    user_id = int(parts[1])
                    conn.close()
                    return user_id
                except ValueError:
                    pass

        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"❌ Ошибка получения владельца ссылки: {e}")
        return None


# Сохранение сообщения в историю
def save_message_history(link_code: str, sender: types.User, content_type: str, content_info: str):
    """Сохранение сообщения в историю"""
    try:
        db_path = os.getenv("DB_PATH", "anon_bot.db")
        if 'RENDER' in os.environ or 'PORT' in os.environ:
            db_path = os.path.join(os.getcwd(), db_path)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute('''INSERT INTO messages 
                     (link_code, sender_id, sender_username, content_type, content_info, timestamp) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (link_code, sender.id, sender.username or '', content_type, content_info,
                   datetime.now().isoformat()))

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения истории: {e}")


# Получение истории сообщений
def get_message_history(user_id: int):
    """Получение истории сообщений пользователя"""
    try:
        db_path = os.getenv("DB_PATH", "anon_bot.db")
        if 'RENDER' in os.environ or 'PORT' in os.environ:
            db_path = os.path.join(os.getcwd(), db_path)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("SELECT link_code FROM anon_links WHERE user_id = ? AND is_active = 1", (user_id,))
        link_result = c.fetchone()

        if not link_result:
            conn.close()
            return []

        link_code = link_result[0]

        c.execute('''SELECT sender_username, content_type, content_info, timestamp 
                     FROM messages 
                     WHERE link_code = ? 
                     ORDER BY timestamp DESC LIMIT 50''', (link_code,))
        messages = c.fetchall()

        conn.close()
        return messages
    except Exception as e:
        logger.error(f"❌ Ошибка получения истории: {e}")
        return []


# Обработчик текстовых сообщений
async def handle_text_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка текстовых сообщений"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        save_message_history(link_code, message.from_user, "text", message.text)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "ТЕКСТ",
            message.text[:200],
            recipient_id,
            link_code
        )

        await bot.send_message(
            recipient_id,
            f"📨 <b>Новое анонимное сообщение!</b>\n"
            f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
            f"{message.text}\n\n"
            f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Текст отправлен анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки текста: {e}")
        await message.answer("❌ Не удалось отправить сообщение. Возможно, пользователь заблокировал бота.")


# Обработчик фото
async def handle_photo_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка фото"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        photo_info = f"Фото ({message.photo[-1].file_size // 1024} KB)"
        save_message_history(link_code, message.from_user, "photo", photo_info)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "ФОТО",
            photo_info,
            recipient_id,
            link_code
        )

        caption = message.caption or "📷 Анонимное фото"
        await bot.send_photo(
            recipient_id,
            photo=message.photo[-1].file_id,
            caption=f"📸 <b>Анонимное фото!</b>\n"
                    f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
                    f"{caption}\n\n"
                    f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Фото отправлено анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")
        await message.answer("❌ Не удалось отправить фото.")


# Обработчик видео
async def handle_video_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка видео"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        video_info = f"Видео ({message.video.file_size // 1024} KB, {message.video.duration} сек)"
        save_message_history(link_code, message.from_user, "video", video_info)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "ВИДЕО",
            video_info,
            recipient_id,
            link_code
        )

        caption = message.caption or "🎥 Анонимное видео"
        await bot.send_video(
            recipient_id,
            video=message.video.file_id,
            caption=f"🎬 <b>Анонимное видео!</b>\n"
                    f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
                    f"{caption}\n\n"
                    f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Видео отправлено анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видео: {e}")
        await message.answer("❌ Не удалось отправить видео.")


# Обработчик голосовых сообщений
async def handle_voice_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка голосовых сообщений"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        voice_info = f"Голосовое ({message.voice.duration} сек)"
        save_message_history(link_code, message.from_user, "voice", voice_info)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "ГОЛОС",
            voice_info,
            recipient_id,
            link_code
        )

        await bot.send_voice(
            recipient_id,
            voice=message.voice.file_id,
            caption=f"🎤 <b>Анонимное голосовое сообщение!</b>\n"
                    f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n"
                    f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Голосовое отправлено анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки голосового: {e}")
        await message.answer("❌ Не удалось отправить голосовое сообщение.")


# Обработчик аудио (музыки)
async def handle_audio_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка аудио"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        audio_info = f"Аудио: {message.audio.title or 'Без названия'} - {message.audio.performer or 'Неизвестно'}"
        save_message_history(link_code, message.from_user, "audio", audio_info)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "АУДИО",
            audio_info,
            recipient_id,
            link_code
        )

        caption = f"🎵 <b>Анонимная музыка!</b>\n"
        if message.audio.title:
            caption += f"Название: {message.audio.title}\n"
        if message.audio.performer:
            caption += f"Исполнитель: {message.audio.performer}\n"
        caption += f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
        caption += f"<i>💬 Ответить нельзя</i>"

        await bot.send_audio(
            recipient_id,
            audio=message.audio.file_id,
            caption=caption,
            parse_mode="HTML"
        )
        await message.answer("✅ Аудио отправлено анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки аудио: {e}")
        await message.answer("❌ Не удалось отправить аудио.")


# Обработчик документов
async def handle_document_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка документов"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        doc_info = f"Документ: {message.document.file_name} ({message.document.file_size // 1024} KB)"
        save_message_history(link_code, message.from_user, "document", doc_info)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "ДОКУМЕНТ",
            doc_info,
            recipient_id,
            link_code
        )

        await bot.send_document(
            recipient_id,
            document=message.document.file_id,
            caption=f"📎 <b>Анонимный документ!</b>\n"
                    f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n"
                    f"Файл: {message.document.file_name}\n\n"
                    f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Документ отправлен анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки документа: {e}")
        await message.answer("❌ Не удалось отправить документ.")


# Обработчик стикеров
async def handle_sticker_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка стикеров"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        sticker_info = f"Стикер из набора"
        save_message_history(link_code, message.from_user, "sticker", sticker_info)
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "СТИКЕР",
            sticker_info,
            recipient_id,
            link_code
        )

        await bot.send_sticker(
            recipient_id,
            sticker=message.sticker.file_id
        )
        await bot.send_message(
            recipient_id,
            f"✨ <b>Анонимный стикер!</b>\n"
            f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
            f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Стикер отправлен анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки стикера: {e}")
        await message.answer("❌ Не удалось отправить стикер.")


# Обработчик видео-сообщений (видео-заметки)
async def handle_video_note_message(message: types.Message, recipient_id: int, link_code: str):
    """Обработка видео-заметок"""
    if bot is None:
        await message.answer("❌ Бот не инициализирован")
        return

    try:
        save_message_history(link_code, message.from_user, "video_note", "Видео-заметка")
        log_anon_message(
            message.from_user.id,
            message.from_user.username,
            "ВИДЕО-ЗАМЕТКА",
            f"{message.video_note.duration} сек",
            recipient_id,
            link_code
        )

        await bot.send_video_note(
            recipient_id,
            video_note=message.video_note.file_id
        )
        await bot.send_message(
            recipient_id,
            f"📹 <b>Анонимная видео-заметка!</b>\n"
            f"🕒 <i>{datetime.now().strftime('%H:%M')}</i>\n\n"
            f"<i>💬 Ответить нельзя</i>",
            parse_mode="HTML"
        )
        await message.answer("✅ Видео-заметка отправлена анонимно!")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видео-заметки: {e}")
        await message.answer("❌ Не удалось отправить видео-заметку.")


# Команда /start
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()

    user = message.from_user
    save_user(user)
    logger.info(f"👤 Пользователь: @{user.username or 'без username'} (ID: {user.id})")

    parts = message.text.split()

    if len(parts) > 1:
        link_code = parts[1]
        recipient_id = get_link_owner(link_code)

        if recipient_id:
            if recipient_id == user.id:
                # УБИРАЕМ КНОПКУ "МОИ СООБЩЕНИЯ"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔗 Моя ссылка", callback_data="my_link")]
                ])
                await message.answer(
                    "👋 Это твоя собственная ссылка!\n"
                    "Ты можешь получить ссылку для распространения.",
                    reply_markup=keyboard
                )
                logger.info(f"🔗 Пользователь открыл свою ссылку: {link_code}")
            else:
                await state.update_data(
                    link_code=link_code,
                    recipient_id=recipient_id
                )
                await state.set_state(SendAnonMessage.waiting_for_anything)

                await message.answer(
                    "✍️ <b>Анонимное сообщение</b>\n\n"
                    "Ты можешь отправить <b>любое сообщение</b> владельцу этой ссылки:\n"
                    "• Текст 📝\n"
                    "• Фото 📸\n"
                    "• Видео 🎬\n"
                    "• Голосовые 🎤\n"
                    "• Музыку 🎵\n"
                    "• Документы 📎\n"
                    "• Стикеры ✨\n\n"
                    "⚠️ <b>ВНИМАНИЕ:</b>\n"
                    "• Сообщение будет отправлено <b>полностью анонимно</b>\n"
                    "• Отправитель не узнает, кто ты\n\n"
                    "Просто отправь что угодно:",
                    parse_mode="HTML"
                )
                logger.info(f"📤 Пользователь готов отправить сообщение через ссылку: {link_code}")
            return
        else:
            await message.answer("❌ Ссылка недействительна или устарела.")
            logger.warning(f"⚠️ Недействительная ссылка: {link_code}")
            return

    # УБИРАЕМ КНОПКУ "МОИ СООБЩЕНИЯ"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить мою ссылку", callback_data="get_link")]
    ])

    await message.answer(
        "👋 <b>Анонимный бот</b>\n\n"
        "📌 <b>Как это работает:</b>\n"
        "1. Нажми «Получить мою ссылку»\n"
        "2. Отправь ссылку друзьям\n"
        "3. Они смогут писать тебе анонимно\n"
        "4. Получай любые сообщения: текст, фото, видео, голосовые и т.д.\n\n"
        "Чтобы отправить анонимное сообщение, перейди по чужой ссылке.",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    logger.info(f"🚀 Новый пользователь: @{user.username or 'без username'} (ID: {user.id})")


# Обработка ВСЕХ типов сообщений в состоянии отправки
@dp.message(SendAnonMessage.waiting_for_anything)
async def process_any_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    link_code = data.get('link_code')
    recipient_id = data.get('recipient_id')

    if not link_code or not recipient_id:
        await message.answer("❌ Ошибка. Попробуй перейти по ссылке снова.")
        await state.clear()
        logger.error("❌ Не найдены link_code или recipient_id в состоянии FSM")
        return

    try:
        # Определяем тип сообщения и обрабатываем
        if message.text:
            await handle_text_message(message, recipient_id, link_code)

        elif message.photo:
            await handle_photo_message(message, recipient_id, link_code)

        elif message.video:
            await handle_video_message(message, recipient_id, link_code)

        elif message.voice:
            await handle_voice_message(message, recipient_id, link_code)

        elif message.audio:
            await handle_audio_message(message, recipient_id, link_code)

        elif message.document:
            await handle_document_message(message, recipient_id, link_code)

        elif message.sticker:
            await handle_sticker_message(message, recipient_id, link_code)

        elif message.video_note:
            await handle_video_note_message(message, recipient_id, link_code)

        else:
            await message.answer("❌ Этот тип сообщения пока не поддерживается.")
            logger.warning(f"⚠️ Неподдерживаемый тип сообщения от пользователя ID: {message.from_user.id}")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}", exc_info=True)
        await message.answer("❌ Не удалось отправить сообщение.")

    # Очищаем состояние после отправки
    await state.clear()


# Обработка кнопок
@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    try:
        if callback.data == "get_link":
            link_code = create_anon_link(user_id)
            try:
                bot_info = await bot.get_me()
                username = bot_info.username
            except Exception as e:
                logger.error(f"❌ Ошибка получения информации о боте: {e}")
                username = "anon_message_bot"

            link_url = f"https://t.me/{username}?start={link_code}"

            logger.info(f"🔗 Пользователь ID: {user_id} получил ссылку: {link_code}")

            # УБИРАЕМ КНОПКУ "МОИ СООБЩЕНИЯ" и "НОВАЯ ССЫЛКА"
            await callback.message.edit_text(
                f"🔗 <b>Твоя анонимная ссылка:</b>\n\n"
                f"<code>{link_url}</code>\n\n"
                f"📢 <b>Что можно отправлять по этой ссылке:</b>\n"
                f"• Текст 📝\n"
                f"• Фото 📸\n"
                f"• Видео 🎬\n"
                f"• Голосовые 🎤\n"
                f"• Музыку 🎵\n"
                f"• Документы 📎\n"
                f"• Стикеры ✨\n"
                f"• Видео-заметки 📹\n\n"
                f"⚠️ <b>Все сообщения будут анонимными!</b>\n\n"
                f"🔗 <b>Скопируй и отправь друзьям:</b>\n"
                f"<code>{link_url}</code>",
                parse_mode="HTML"
                # УБИРАЕМ ВСЕ КНОПКИ
            )
            await callback.answer()

        elif callback.data == "my_link":
            link_code = create_anon_link(user_id)
            try:
                bot_info = await bot.get_me()
                username = bot_info.username
            except Exception as e:
                logger.error(f"❌ Ошибка получения информации о боте: {e}")
                username = "anon_message_bot"

            link_url = f"https://t.me/{username}?start={link_code}"

            logger.info(f"🔗 Пользователь ID: {user_id} запросил свою ссылку: {link_code}")

            # УБИРАЕМ КНОПКУ "МОИ СООБЩЕНИЯ"
            await callback.message.edit_text(
                f"🔗 <b>Твоя ссылка:</b>\n\n"
                f"<code>{link_url}</code>\n\n"
                f"Отправь эту ссылку друзьям, чтобы получать анонимные сообщения.",
                parse_mode="HTML"
                # УБИРАЕМ ВСЕ КНОПКИ
            )
            await callback.answer()

        # УДАЛЯЕМ ВСЕ ОСТАЛЬНЫЕ ОБРАБОТЧИКИ КНОПОК:
        # - "new_link"
        # - "check_messages"
        # - "my_messages"

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике кнопок: {e}", exc_info=True)
        await callback.answer("Произошла ошибка, попробуй еще раз")


# Команда для админа - просмотр всех логов
@dp.message(Command("logs"))
async def show_logs(message: types.Message):
    user_id = message.from_user.id
    ADMIN_ID = os.getenv("ADMIN_ID")

    if not ADMIN_ID or not ADMIN_ID.strip():
        await message.answer("❌ ADMIN_ID не настроен в переменных окружения.")
        logger.warning("⚠️ ADMIN_ID не настроен")
        return

    try:
        admin_id_int = int(ADMIN_ID)
    except ValueError:
        await message.answer("❌ ADMIN_ID должен быть числом.")
        logger.warning(f"⚠️ Неверный формат ADMIN_ID: {ADMIN_ID}")
        return

    if user_id != admin_id_int:
        await message.answer("❌ У тебя нет доступа к этой команде.")
        logger.warning(f"⚠️ Пользователь ID: {user_id} попытался получить доступ к /logs")
        return

    logger.info(f"👑 Админ ID: {user_id} запросил логи")

    db_path = os.getenv("DB_PATH", "anon_bot.db")
    if 'RENDER' in os.environ or 'PORT' in os.environ:
        db_path = os.path.join(os.getcwd(), db_path)

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute('''SELECT sender_username, sender_id, content_type, content_info, link_code, timestamp 
                     FROM messages 
                     ORDER BY timestamp DESC LIMIT 20''')
        logs = c.fetchall()

        if not logs:
            await message.answer("📭 Логов пока нет.")
            return

        response = "📋 <b>Последние анонимные сообщения:</b>\n\n"

        for username, sender_id, content_type, content_info, link_code, timestamp in logs:
            try:
                time = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
            except:
                time = timestamp

            username_display = f"@{username}" if username else f"ID:{sender_id}"

            response += f"🕒 <b>{time}</b>\n"
            response += f"👤 <b>{username_display}</b>\n"
            response += f"📁 <b>{content_type.upper()}</b>\n"

            if content_type == "text":
                response += f"💬 {content_info[:50]}"
                if len(content_info) > 50:
                    response += "..."
            else:
                response += f"📄 {content_info}"

            response += f"\n🔗 {link_code[:8]}...\n"
            response += "─" * 30 + "\n\n"

        response += f"📊 Всего сообщений в БД: {len(logs)} показано"

        await message.answer(response, parse_mode="HTML")
        logger.info(f"📊 Админу отправлено {len(logs)} логов")
    except Exception as e:
        logger.error(f"❌ Ошибка получения логов: {e}")
        await message.answer(f"❌ Ошибка получения логов: {str(e)}")
    finally:
        if conn:
            conn.close()