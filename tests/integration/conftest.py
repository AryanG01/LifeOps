# tests/integration/conftest.py
"""
Integration test fixtures.

Requires DATABASE_URL pointing to a test database (clawdbot_test).
Set: export DATABASE_URL=postgresql://clawdbot:clawdbot@localhost/clawdbot_test
Then: cd infra && alembic upgrade head
"""
import os
import pytest
import uuid

# Ensure integration tests use the test database
if "clawdbot_test" not in os.environ.get("DATABASE_URL", ""):
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql://clawdbot:clawdbot@localhost/clawdbot_test",
    )


@pytest.fixture(scope="function")
def db_user_source():
    """
    Create a fresh test User + Source for each test, and clean up after.
    Returns (user_id, source_id) strings.
    """
    from core.db.engine import get_db
    from core.db.models import User, Source

    user_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    with get_db() as db:
        db.add(User(
            id=user_id,
            email=f"test-{user_id[:8]}@integration.test",
            display_name="Integration Test User",
            timezone="Asia/Singapore",
        ))
        db.add(Source(
            id=source_id,
            user_id=user_id,
            source_type="gmail",
            display_name="Test Gmail",
            config_json={},
        ))
        db.commit()

    yield user_id, source_id

    # Teardown: delete user (cascades to all related records)
    with get_db() as db:
        from core.db.models import User
        user = db.query(User).filter_by(id=user_id).first()
        if user:
            db.delete(user)
            db.commit()
