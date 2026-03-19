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
            InlineKeyboardButton("✓ Accept",  callback_data=f"accept:{task_id}"),
            InlineKeyboardButton("✗ Dismiss", callback_data=f"dismiss:{task_id}"),
            InlineKeyboardButton("⏰ Snooze",  callback_data=f"snooze:{task_id}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("✗ Dismiss", callback_data=f"dismiss:{task_id}"),
            InlineKeyboardButton("⏰ Snooze",  callback_data=f"snooze:{task_id}"),
        ])
    rows.append([
        InlineKeyboardButton("✅ Done",   callback_data=f"done:{task_id}"),
        InlineKeyboardButton("✏️ Edit",  callback_data=f"edit:{task_id}"),
    ])
    return rows


def build_edit_field_keyboard(task_id: str) -> list[list[InlineKeyboardButton]]:
    """Field picker shown after tapping ✏️ Edit on a task card."""
    return [
        [
            InlineKeyboardButton("📝 Title",    callback_data=f"edit_field:title:{task_id}"),
            InlineKeyboardButton("⏰ Due date", callback_data=f"edit_field:due:{task_id}"),
            InlineKeyboardButton("🔢 Priority", callback_data=f"edit_field:priority:{task_id}"),
        ],
    ]


def build_reply_keyboard(draft_id: str) -> list[list[InlineKeyboardButton]]:
    """Keyboard for reply draft cards: Send / Edit / Skip."""
    return [[
        InlineKeyboardButton("✓ Send",  callback_data=f"reply_send:{draft_id}"),
        InlineKeyboardButton("✏️ Edit", callback_data=f"reply_edit:{draft_id}"),
        InlineKeyboardButton("✗ Skip",  callback_data=f"reply_skip:{draft_id}"),
    ]]


def build_snooze_menu(task_id: str) -> list[list[InlineKeyboardButton]]:
    """Snooze duration picker shown after tapping ⏰ Snooze."""
    return [
        [
            InlineKeyboardButton("1 hour",     callback_data=f"snooze_1h:{task_id}"),
            InlineKeyboardButton("3 hours",    callback_data=f"snooze_3h:{task_id}"),
        ],
        [
            InlineKeyboardButton("Tomorrow ☀️", callback_data=f"snooze_tom:{task_id}"),
            InlineKeyboardButton("Custom ✏️",   callback_data=f"snooze_custom:{task_id}"),
        ],
    ]
