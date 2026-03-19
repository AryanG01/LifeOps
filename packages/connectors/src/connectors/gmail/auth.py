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
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

SERVICE_NAME = "clawdbot-gmail"
# Legacy constant kept for backwards compatibility (single-account installs use "default")
TOKEN_USERNAME = "default"


def get_credentials(account_label: str = "default") -> Credentials:
    """Return valid credentials for the given account label, refreshing if expired.

    The ``account_label`` is the token storage key (e.g. "personal", "work").
    Defaults to "default" so existing single-account installs keep working unchanged.
    Raises RuntimeError if not authorised.
    """
    token_data = get_token(SERVICE_NAME, account_label)

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
        _persist(creds, account_label)
        log.info("gmail_token_refreshed", account_label=account_label)

    if not creds or not creds.valid:
        raise RuntimeError(
            f"No valid Gmail credentials for label '{account_label}'. "
            "Run: claw connect gmail"
        )

    return creds


def get_email_address(creds: Credentials) -> str:
    """Fetch the authenticated Gmail address by calling the profile API."""
    from googleapiclient.discovery import build as _build
    service = _build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def run_oauth_flow(credentials_file: str, account_label: str = "default") -> Credentials:
    """Run OAuth flow. Uses fixed port 8080 with no browser (works headless via SSH tunnel).

    Tokens are stored under ``account_label`` so multiple Gmail accounts can coexist.
    """
    creds_path = str(Path(credentials_file).expanduser())
    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=False)
    _persist(creds, account_label)
    log.info("gmail_oauth_complete", account_label=account_label)
    return creds


def revoke_credentials(account_label: str = "default") -> None:
    """Remove stored credentials for the given account label."""
    delete_token(SERVICE_NAME, account_label)
    log.info("gmail_credentials_revoked", account_label=account_label)


def _persist(creds: Credentials, account_label: str = "default") -> None:
    """Save credentials under account_label without logging any secret values."""
    store_token(SERVICE_NAME, account_label, {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    })
