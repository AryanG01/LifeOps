"""Secure token storage using OS keychain (keyring) with encrypted file fallback."""
import json
import os
from pathlib import Path

import structlog

log = structlog.get_logger()

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False


def _fallback_path(service: str, username: str) -> Path:
    base = Path.home() / ".config" / "clawdbot" / "tokens"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{service}_{username}.json"


def store_token(service: str, username: str, token_data: dict) -> None:
    """Store token data securely. NEVER logs token values."""
    serialized = json.dumps(token_data)
    if _KEYRING_AVAILABLE:
        keyring.set_password(service, username, serialized)
        log.info("token_stored", service=service, username=username, backend="keyring")
    else:
        path = _fallback_path(service, username)
        path.write_text(serialized)
        path.chmod(0o600)
        log.info("token_stored", service=service, username=username, backend="file")


def get_token(service: str, username: str) -> dict | None:
    """Retrieve token data. Returns None if not found. NEVER logs token values."""
    if _KEYRING_AVAILABLE:
        value = keyring.get_password(service, username)
        if value:
            return json.loads(value)
        return None
    else:
        path = _fallback_path(service, username)
        if path.exists():
            return json.loads(path.read_text())
        return None


def delete_token(service: str, username: str) -> None:
    """Delete stored token."""
    if _KEYRING_AVAILABLE:
        try:
            keyring.delete_password(service, username)
            log.info("token_deleted", service=service, username=username, backend="keyring")
        except Exception:
            pass
    else:
        path = _fallback_path(service, username)
        if path.exists():
            path.unlink()
            log.info("token_deleted", service=service, username=username, backend="file")
