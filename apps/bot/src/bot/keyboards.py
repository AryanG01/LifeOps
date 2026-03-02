# apps/bot/src/bot/keyboards.py
"""
InlineKeyboardMarkup builders for Telegram bot messages.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_task_keyboard(task_id: str) -> list[list[InlineKeyboardButton]]:
    """
    Build the Accept/Dismiss/Snooze keyboard for a task notification.

    Returns a list-of-rows suitable for InlineKeyboardMarkup(build_task_keyboard(...)).

    callback_data format: "action:task_uuid"
    """
    return [[
        InlineKeyboardButton("✓ Accept",     callback_data=f"accept:{task_id}"),
        InlineKeyboardButton("✗ Dismiss",    callback_data=f"dismiss:{task_id}"),
        InlineKeyboardButton("⏰ Snooze 2h",  callback_data=f"snooze:{task_id}"),
    ]]


def build_task_keyboard_markup(task_id: str) -> InlineKeyboardMarkup:
    """Convenience wrapper returning InlineKeyboardMarkup directly."""
    return InlineKeyboardMarkup(build_task_keyboard(task_id))
