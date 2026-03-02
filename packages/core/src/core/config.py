from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Resolve .env from project root (packages/core/src/core/ → 4 parents up)
_project_root = Path(__file__).parent.parent.parent.parent.parent
_env_file = _project_root / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_env_file), extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql://clawdbot:clawdbot@localhost:5432/clawdbot"
    )

    # LLM — provider: "gemini" (free, default) or "anthropic"
    llm_provider: str = Field(default="gemini")
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-sonnet-4-6")
    llm_mode: str = Field(default="enabled")          # enabled | disabled
    llm_triage_enabled: bool = Field(default=True)
    llm_triage_model: str = Field(default="gemini-2.5-flash-lite")
    llm_prompt_version: str = Field(default="v1")
    llm_label_filter: list[str] = Field(default=["INBOX", "UNREAD"])
    llm_filter_canvas_always: bool = Field(default=True)

    # Privacy
    privacy_store_full_bodies: bool = Field(default=True)
    privacy_redact_emails: bool = Field(default=False)

    # API server
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)

    # User defaults
    user_timezone: str = Field(default="Asia/Singapore")
    default_user_id: str = Field(
        default="00000000-0000-0000-0000-000000000001"
    )

    # Microsoft Graph / Outlook
    outlook_client_id: str = Field(default="")
    outlook_token_service: str = Field(default="clawdbot-outlook")

    # Gmail
    gmail_credentials_path: str = Field(
        default="~/.config/clawdbot/gmail_credentials.json"
    )
    gmail_token_service: str = Field(default="clawdbot-gmail")
    gmail_poll_interval_minutes: int = Field(default=15)
    gmail_max_results: int = Field(default=50)

    # Telegram
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")
    telegram_enabled: bool = Field(default=False)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
