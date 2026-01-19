import os
import logging
import sys
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.types import BotCommand

from anon_bot import dp, bot, init_db

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение хоста Render
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else None

# Порт из переменной окружения Render
PORT = int(os.getenv("PORT", 10000))


# Health check
async def health_check(request):
    return web.Response(text="OK", status=200)


# Главная страница
async def home_page(request):
    return web.Response(
        text="🤖 Анонимный Telegram бот работает!\n\n"
             "Этот бот позволяет отправлять анонимные сообщения.\n"
             "Используйте Telegram для взаимодействия с ботом.",
        status=200
    )


# Startup
async def on_startup(app):
    try:
        # Инициализируем БД
        if init_db():
            logger.info("✅ База данных готова")
        else:
            logger.error("❌ Не удалось инициализировать БД")

        # Устанавливаем команды бота
        await bot.set_my_commands([
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="logs", description="Посмотреть логи (админ)"),
        ])
        logger.info("✅ Команды бота установлены")

        # Устанавливаем вебхук
        if WEBHOOK_URL:
            await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
            logger.info(f"✅ Вебхук установлен: {WEBHOOK_URL}")
        else:
            logger.warning("⚠️ RENDER_EXTERNAL_HOSTNAME не установлен")

        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот запущен: @{bot_info.username} (ID: {bot_info.id})")

        # Уведомление админу
        admin_id = os.getenv("ADMIN_ID")
        if admin_id and admin_id.strip():
            try:
                await bot.send_message(
                    chat_id=int(admin_id),
                    text=f"✅ Бот запущен!\n"
                         f"🤖 @{bot_info.username}\n"
                         f"🌐 Режим: {'Webhook' if WEBHOOK_URL else 'Polling'}\n"
                         f"🕒 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                logger.info(f"📨 Уведомление отправлено админу ID: {admin_id}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось отправить админу: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}", exc_info=True)


# Shutdown
async def on_shutdown(app):
    logger.info("🛑 Остановка бота...")
    try:
        if WEBHOOK_URL:
            await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка при остановке: {e}")


# Основная функция
def main():
    logger.info("🚀 Запуск анонимного Telegram бота...")

    # Проверка токена
    if not os.getenv("BOT_TOKEN"):
        logger.error("❌ BOT_TOKEN не найден! Установите переменную окружения BOT_TOKEN")
        sys.exit(1)

    # Создаем приложение
    app = web.Application()

    # Роуты
    app.router.add_get("/health", health_check)
    app.router.add_get("/", home_page)

    # Вебхук
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_handler.register(app, path=WEBHOOK_PATH)

    # Настройка приложения
    setup_application(app, dp, bot=bot)

    # Startup/shutdown
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # Запуск сервера
    logger.info(f"🌐 Сервер запускается на порту {PORT}")
    logger.info(f"🔧 Режим: {'Webhook' if WEBHOOK_URL else 'Polling'}")

    try:
        web.run_app(app, host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"❌ Ошибка запуска сервера: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()