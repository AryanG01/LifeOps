"""Unit tests for keyboards.py — no DB, no Telegram API calls."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/bot/src'))


def test_build_task_keyboard_returns_three_buttons():
    """Keyboard for a task has exactly 3 buttons in one row."""
    from bot.keyboards import build_task_keyboard

    kb = build_task_keyboard("task-uuid-123")
    assert len(kb) == 1  # one row
    assert len(kb[0]) == 3  # three buttons


def test_build_task_keyboard_callback_data_format():
    """callback_data follows action:uuid format."""
    from bot.keyboards import build_task_keyboard

    kb = build_task_keyboard("abc-123")
    row = kb[0]
    datas = [btn.callback_data for btn in row]
    assert "accept:abc-123" in datas
    assert "dismiss:abc-123" in datas
    assert "snooze:abc-123" in datas
