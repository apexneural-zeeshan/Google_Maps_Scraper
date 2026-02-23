from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys (all optional — project runs on free tier)
    serpapi_key: str = ""
    outscraper_api_key: str = ""
    resend_api_key: str = ""

    # PostgreSQL
    postgres_user: str = "gmaps"
    postgres_password: str = "gmaps_secret"
    postgres_db: str = "gmaps_scraper"
    database_url: str = "postgresql+asyncpg://gmaps:gmaps_secret@db:5432/gmaps_scraper"
    database_url_sync: str = "postgresql+psycopg2://gmaps:gmaps_secret@db:5432/gmaps_scraper"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Backend
    secret_key: str = "change-me"
    backend_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://gmapscraper.apexneural.cloud",
    ]

    # URLs for email links
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    # Email notifications (Resend.com)
    # Resend.com free tier only allows "onboarding@resend.dev" as sender
    # unless you verify your own domain at https://resend.com/domains
    notification_from_email: str = "GMaps Scraper <onboarding@resend.dev>"

    # Nominatim (free geocoding)
    nominatim_user_agent: str = "GMapsScraperApp/1.0"

    # Playwright (free scraping)
    playwright_headless: bool = True
    playwright_scrape_details: bool = True

    # Rate Limits
    serp_api_rps: int = 5
    grid_overlap_factor: float = 0.2

    # Free tier limits
    serpapi_monthly_limit: int = 100
    outscraper_monthly_limit: int = 500


settings = Settings()
