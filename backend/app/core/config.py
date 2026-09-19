"""
Application settings.

Everything environment-specific (database URL, debug flags) lives here
and ONLY here. No other file should read os.environ directly - that
keeps config changes to a one-file diff instead of a grep-and-replace
across the codebase.

Default DATABASE_URL is SQLite so the API runs with zero setup on any
machine. Point it at Postgres (see docker-compose.yml) by setting
DATABASE_URL in a .env file - no code changes needed, since SQLAlchemy
abstracts the actual database engine away from the rest of the app.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Project Quant API"
    database_url: str = "sqlite:///./quant.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
