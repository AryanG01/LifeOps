# apps/bot/src/bot/keyboards.py
"""
InlineKeyboardMarkup builders for Telegram bot messages.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_task_keyboard(task_id: str, status: str = "proposed") -> list[list[InlineKeyboardButton]]:
    """
    Build task action keyboard. Accept only shown for proposed tasks.

    callback_data format: "action:task_uuid"
    """
    rows = []
    if status == "proposed":
        rows.append([
            InlineKeyboardButton("✓ Accept",    callback_data=f"accept:{task_id}"),
            InlineKeyboardButton("✗ Dismiss",   callback_data=f"dismiss:{task_id}"),
            InlineKeyboardButton("⏰ Snooze 2h", callback_data=f"snooze:{task_id}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("✗ Dismiss",   callback_data=f"dismiss:{task_id}"),
            InlineKeyboardButton("⏰ Snooze 2h", callback_data=f"snooze:{task_id}"),
        ])
    rows.append([InlineKeyboardButton("✅ Done", callback_data=f"done:{task_id}")])
    return rows


def build_task_keyboard_markup(task_id: str) -> InlineKeyboardMarkup:
    """Convenience wrapper returning InlineKeyboardMarkup directly."""
    return InlineKeyboardMarkup(build_task_keyboard(task_id))
