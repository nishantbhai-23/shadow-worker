from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str
    telegram_start_secret: str

    database_url: str

    llm_provider: str = "anthropic"
    llm_model: str
    llm_api_key: str
    llm_base_url: str | None = None

    digest_hour: int = 10
    tz: str = "UTC"


settings = Settings()
