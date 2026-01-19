#!/usr/bin/env python3
"""
Локальный запуск бота в режиме polling
Используется для разработки и тестирования
"""

import os
import sys
import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Основная функция для локального запуска"""

    # Загружаем переменные окружения из .env файла
    from dotenv import load_dotenv
    load_dotenv()

    # Проверка токена
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        logger.error("Создайте файл .env с содержимым:")
        logger.error("BOT_TOKEN=ваш_токен_бота")
        logger.error("ADMIN_ID=ваш_telegram_id")
        return

    logger.info("🚀 Локальный запуск анонимного Telegram бота...")

    # Импортируем после загрузки переменных окружения
    from anon_bot import dp, init_db, bot

    # Инициализируем БД
    if init_db():
        logger.info("✅ База данных инициализирована")
    else:
        logger.error("❌ Ошибка инициализации БД")

    # Устанавливаем команды бота
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="logs", description="Посмотреть логи (админ)"),
        ])
        logger.info("✅ Команды бота установлены")
    except Exception as e:
        logger.error(f"❌ Ошибка установки команд: {e}")

    # Получаем информацию о боте
    try:
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот запущен: @{bot_info.username} (ID: {bot_info.id})")

        # Проверяем админа
        ADMIN_ID = os.getenv("ADMIN_ID")
        if ADMIN_ID and ADMIN_ID.strip():
            try:
                await bot.send_message(
                    chat_id=int(ADMIN_ID),
                    text=f"✅ Бот запущен локально!\n"
                         f"🤖 @{bot_info.username}\n"
                         f"🌐 Режим: Polling\n"
                         f"🕒 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                logger.info(f"📨 Уведомление отправлено админу ID: {ADMIN_ID}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить админу: {e}")
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о боте: {e}")

    # Запускаем polling
    logger.info("🔄 Запускаем polling... (Ctrl+C для остановки)")

    try:
        # Удаляем вебхук если был установлен
        await bot.delete_webhook(drop_pending_updates=True)

        # Запускаем polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске polling: {e}")
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Остановлено пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")