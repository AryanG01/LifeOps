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
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters,
)

from core.config import get_settings
from bot.handlers import commands, callbacks
from bot.handlers.commands import (
    NEWTASK_TITLE, NEWTASK_DUE,
    SNOOZE_CUSTOM,
    REPLY_EDIT_TEXT, REPLY_EDIT_CONFIRM,
    EDIT_CHOOSE_FIELD, EDIT_INPUT_VALUE,
)

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
    newtask_conv = ConversationHandler(
        entry_points=[CommandHandler("newtask", commands.handle_newtask_start)],
        states={
            NEWTASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, commands.handle_newtask_title)],
            NEWTASK_DUE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, commands.handle_newtask_due)],
        },
        fallbacks=[CommandHandler("cancel", commands.handle_newtask_cancel)],
        conversation_timeout=120,
    )
    app.add_handler(newtask_conv)
    app.add_handler(CommandHandler("status",  commands.handle_status))
    app.add_handler(CommandHandler("search",  commands.handle_search))
    app.add_handler(CommandHandler("replies", commands.handle_replies))

    # Task edit ConversationHandler — entry: edit:<task_id> callback
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(commands.handle_edit_start, pattern="^edit:")
        ],
        states={
            EDIT_CHOOSE_FIELD: [
                CallbackQueryHandler(commands.handle_edit_field_choice, pattern="^edit_field:")
            ],
            EDIT_INPUT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, commands.handle_edit_value)
            ],
        },
        fallbacks=[CommandHandler("cancel", commands.handle_edit_cancel)],
        conversation_timeout=120,
    )
    app.add_handler(edit_conv)

    # Reply edit ConversationHandler — entry point is reply_edit: callback; must come
    # before the generic CallbackQueryHandler.
    reply_edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(commands.handle_reply_edit_start, pattern="^reply_edit:")
        ],
        states={
            REPLY_EDIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, commands.handle_reply_edit_text)
            ],
            REPLY_EDIT_CONFIRM: [
                CallbackQueryHandler(commands.handle_reply_edit_confirm, pattern="^reply_edit_")
            ],
        },
        fallbacks=[CommandHandler("cancel", commands.handle_reply_cancel)],
        conversation_timeout=300,
    )
    app.add_handler(reply_edit_conv)

    # Snooze custom ConversationHandler — must be registered BEFORE the generic
    # CallbackQueryHandler so it wins the pattern match for snooze_custom:* callbacks.
    snooze_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(commands.handle_snooze_custom_start, pattern="^snooze_custom:")
        ],
        states={
            SNOOZE_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, commands.handle_snooze_custom_input)],
        },
        fallbacks=[CommandHandler("cancel", commands.handle_snooze_cancel)],
        conversation_timeout=120,
    )
    app.add_handler(snooze_conv)

    # Register callback handler (inline button taps) — generic catch-all, must come last
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
