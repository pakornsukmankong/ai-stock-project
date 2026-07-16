from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    # Symmetric secret used to sign Supabase auth JWTs (Project Settings → API →
    # JWT Secret). When set, tokens are verified locally instead of round-tripping
    # to the Supabase Auth server on every request.
    supabase_jwt_secret: str = ""

    # OpenAI
    openai_api_key: str = ""
    # Model used for both the signal analysis and the daily news briefing.
    # Overridable via OPENAI_MODEL so the model can be swapped without a code
    # change. Default: GPT-5.6 Luna (fast, low-cost, high-volume tier).
    openai_model: str = "gpt-5.6-luna"

    # LINE Messaging API
    line_channel_access_token: str = ""
    line_channel_secret: str = ""
    # Lifetime of an account-linking code (Settings → "Generate linking code").
    # Short so a leaked/screenshotted code is useless minutes later.
    line_link_code_ttl_minutes: int = 10

    # Market Data
    market_data_api_key: str = ""

    # App
    app_env: str = "development"
    analysis_interval_minutes: int = 5
    cache_ttl_minutes: int = 30
    # Minimum hours between alerts for the same user+symbol. A buy setup can
    # stay valid for hours/days; without a long enough cooldown the same signal
    # re-fires every cycle once the previous window expires.
    alert_cooldown_hours: int = 24
    # Edge-triggered alerting: only act when a symbol's signal NEWLY turns active
    # (was inactive the previous cycle), not every cycle it stays active. The
    # cooldown above remains a safety net against flapping/restart bursts.
    alert_edge_trigger: bool = True
    # How long alerts are kept before the cleanup job deletes them.
    alerts_retention_days: int = 30

    # Analysis pipeline
    # Symbols analyzed concurrently per cycle. Bounded so a large watchlist does
    # not hammer Yahoo Finance (which rate-limits aggressively).
    analysis_concurrency: int = 5
    # Minimum seconds between manual /analysis/trigger runs *per user*. The
    # endpoint fans out to every watched symbol and calls OpenAI, so it must not
    # be callable in a tight loop.
    trigger_cooldown_seconds: int = 300

    # Chart endpoint cache TTL (seconds). Dashboard tab-switching re-requests the
    # same candles constantly; without this every switch hits Yahoo.
    chart_cache_ttl_seconds: int = 300

    # Security
    # Regex of allowed browser origins. The default matches only this project's
    # Vercel deployments — NOT all of *.vercel.app, which anyone can deploy to.
    cors_allow_origin_regex: str = r"https://ai-stock-project[a-z0-9-]*\.vercel\.app"
    # Number of reverse proxies in front of the app (Railway/Render = 1). The
    # rate limiter reads the client IP this many hops from the right of
    # X-Forwarded-For; anything further left is attacker-controlled.
    trusted_proxy_hops: int = 1

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
