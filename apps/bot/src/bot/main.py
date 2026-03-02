# apps/bot/src/bot/main.py
"""
Clawdbot Telegram Bot — interactive bot process.

Run with:
    claw bot start
or directly:
    PYTHONPATH=... python3 -m bot.main

Runs long-polling (no webhook needed for personal use).
Uses python-telegram-bot v20+ async Application.
"""
import structlog
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

from core.config import get_settings
from bot.handlers import commands, callbacks

log = structlog.get_logger()


def build_app() -> Application:
    """Build and configure the Application. Returns without running (useful for testing)."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN not set. Add it to your .env file. "
            "Create a bot at @BotFather on Telegram."
        )

    app = Application.builder().token(settings.telegram_bot_token).build()

    # Register command handlers
    app.add_handler(CommandHandler("tasks",  commands.handle_tasks))
    app.add_handler(CommandHandler("inbox",  commands.handle_inbox))
    app.add_handler(CommandHandler("digest", commands.handle_digest))
    app.add_handler(CommandHandler("pvi",    commands.handle_pvi))
    app.add_handler(CommandHandler("focus",  commands.handle_focus))
    app.add_handler(CommandHandler("status", commands.handle_status))

    # Register callback handler (inline button taps)
    app.add_handler(CallbackQueryHandler(callbacks.handle_callback))

    log.info("bot_app_built")
    return app


def run() -> None:
    """Start the bot in long-polling mode (blocking)."""
    settings = get_settings()
    log.info("bot_starting", chat_id=settings.telegram_chat_id)
    app = build_app()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run()
