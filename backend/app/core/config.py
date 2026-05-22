from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # LINE Messaging API
    line_channel_access_token: str = ""
    line_channel_secret: str = ""

    # Market Data
    market_data_api_key: str = ""

    # App
    app_env: str = "development"
    analysis_interval_minutes: int = 5
    cache_ttl_minutes: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
