"""Gmail OAuth installed-app flow with PKCE and secure token storage."""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from core.tokens import delete_token, get_token, store_token

import structlog

log = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/calendar.readonly",
]

SERVICE_NAME = "clawdbot-gmail"
TOKEN_USERNAME = "default"


def get_credentials() -> Credentials:
    """Return valid credentials, refreshing if expired. Raises if not authorised."""
    token_data = get_token(SERVICE_NAME, TOKEN_USERNAME)

    creds: Credentials | None = None
    if token_data:
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes"),
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _persist(creds)
        log.info("gmail_token_refreshed")

    if not creds or not creds.valid:
        raise RuntimeError("No valid Gmail credentials. Run: claw connect gmail")

    return creds


def run_oauth_flow(credentials_file: str) -> Credentials:
    """Run OAuth installed-app flow. Opens system browser, listens on random local port."""
    creds_path = str(Path(credentials_file).expanduser())
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    _persist(creds)
    log.info("gmail_oauth_complete")
    return creds


def revoke_credentials() -> None:
    """Remove stored credentials."""
    delete_token(SERVICE_NAME, TOKEN_USERNAME)
    log.info("gmail_credentials_revoked")


def _persist(creds: Credentials) -> None:
    """Save credentials without logging any secret values."""
    store_token(SERVICE_NAME, TOKEN_USERNAME, {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    })
