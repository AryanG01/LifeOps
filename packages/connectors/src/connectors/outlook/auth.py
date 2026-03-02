"""Microsoft Graph authentication via MSAL device code flow.

Works for personal Outlook accounts AND any Microsoft 365 tenant (NUS, corp).
Device code flow: user visits a URL and enters a code — no redirect URI server needed.
"""
import msal
import structlog

from core.config import get_settings
from core.tokens import store_token, get_token

log = structlog.get_logger()

SCOPES = ["Mail.Read", "Calendars.Read", "User.Read"]


def _build_app() -> msal.PublicClientApplication:
    settings = get_settings()
    if not settings.outlook_client_id:
        raise RuntimeError(
            "OUTLOOK_CLIENT_ID not set in .env. "
            "Register an Azure app at https://portal.azure.com"
        )
    authority = f"https://login.microsoftonline.com/{settings.outlook_tenant}"
    return msal.PublicClientApplication(
        client_id=settings.outlook_client_id,
        authority=authority,
    )


def run_oauth_flow() -> dict:
    """
    Run MSAL device code flow. Prints instructions for user to authenticate.
    Returns token dict stored in keyring.
    """
    settings = get_settings()
    app = _build_app()

    # Check for cached token first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            store_token(settings.outlook_token_service, "default", result)
            log.info("outlook_token_refreshed_from_cache")
            return result

    # Device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")

    print(f"\n{flow['message']}\n")  # "Go to https://microsoft.com/devicelogin and enter code XXXX"

    result = app.acquire_token_by_device_flow(flow)  # blocks until user authenticates
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")

    store_token(settings.outlook_token_service, "default", result)
    log.info("outlook_oauth_complete")
    return result


def get_token_dict() -> dict:
    """Return cached token, refreshing if expired. Raises if not authenticated."""
    settings = get_settings()
    token = get_token(settings.outlook_token_service, "default")
    if not token:
        raise RuntimeError("Outlook not connected. Run: claw connect outlook")

    app = _build_app()
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            store_token(settings.outlook_token_service, "default", result)
            return result

    # Fallback: use stored token as-is (may be expired)
    return token
