# tests/unit/test_dedup.py
from core.pipeline.normalizer import compute_dedup_hash


def test_dedup_hash_is_stable():
    h1 = compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    h2 = compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    assert h1 == h2


def test_dedup_hash_differs_for_different_external_id():
    h1 = compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    h2 = compute_dedup_hash("user1", "gmail456", "test@example.com", "Hello")
    assert h1 != h2


def test_dedup_hash_differs_for_different_user():
    h1 = compute_dedup_hash("user1", "gmail123", "test@example.com", "Hello")
    h2 = compute_dedup_hash("user2", "gmail123", "test@example.com", "Hello")
    assert h1 != h2


def test_dedup_hash_is_hex_string():
    h = compute_dedup_hash("user1", "id1", "sender@x.com", "Subject")
    assert isinstance(h, str)
    assert len(h) == 64  # SHA-256 hex digest length
