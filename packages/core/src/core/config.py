from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql://clawdbot:clawdbot@localhost:5432/clawdbot"
    )

    # LLM
    anthropic_api_key: str = Field(default="")
    llm_model: str = Field(default="claude-sonnet-4-6")
    llm_mode: str = Field(default="enabled")          # enabled | disabled
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
