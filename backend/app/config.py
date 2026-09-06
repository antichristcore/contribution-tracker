from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str = ""
    MINI_APP_URL: str = ""

    GITHUB_OWNER: str = ""
    GITHUB_REPO: str = ""
    GITHUB_TOKEN: str = ""

    DATABASE_URL: str = "sqlite:///./data/app.db"

    GITHUB_SYNC_INTERVAL_MINUTES: int = 15
    SCORE_RECALC_INTERVAL_MINUTES: int = 30
    GITHUB_SYNC_LOOKBACK_DAYS: int = 21
    SCORE_LOOKBACK_DAYS: int = 21

    DEV_TIME_TRAVEL: bool = False


settings = Settings()
