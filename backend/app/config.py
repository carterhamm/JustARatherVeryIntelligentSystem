"""Application configuration loaded from environment variables."""

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for every J.A.R.V.I.S. subsystem.

    Values are read from a ``.env`` file at the project root and can be
    overridden by real environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # -- Application ----------------------------------------------------------
    APP_NAME: str = "J.A.R.V.I.S."
    DEBUG: bool = False

    # -- PostgreSQL -----------------------------------------------------------
    DATABASE_URL: str = "postgresql+asyncpg://jarvis:jarvis_secret@localhost:5432/jarvis"

    # -- Redis ----------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # -- Neo4j ----------------------------------------------------------------
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_secret"

    # -- Qdrant ---------------------------------------------------------------
    QDRANT_URL: str = "http://localhost:6333"

    # -- OpenAI ---------------------------------------------------------------
    OPENAI_API_KEY: str = ""

    # -- Anthropic ------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""

    # -- Groq -----------------------------------------------------------------
    GROQ_API_KEY: str = ""

    # -- Google Gemini --------------------------------------------------------
    GOOGLE_GEMINI_API_KEY: str = ""

    # -- Stark Protocol (local Gemma via LM Studio or remote) ------------------
    STARK_PROTOCOL_URL: str = "http://localhost:1234/v1"
    STARK_PROTOCOL_ENDPOINT: str = ""
    STARK_PROTOCOL_API_KEY: str = "lm-studio"
    RUNPOD_API_KEY: str = ""  # legacy, kept for backwards compat
    STARK_PROTOCOL_ENABLED: bool = False

    # -- Default LLM Provider -------------------------------------------------
    DEFAULT_LLM_PROVIDER: str = "openai"

    # -- ElevenLabs -----------------------------------------------------------
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "hfL46UZ81fwyurp9f2X4"

    # -- Google (Gmail + Calendar) --------------------------------------------
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""

    # -- Google Drive ---------------------------------------------------------
    GOOGLE_DRIVE_ENABLED: bool = False

    # -- Slack ----------------------------------------------------------------
    SLACK_BOT_TOKEN: str = ""
    SLACK_ENABLED: bool = False

    # -- GitHub ---------------------------------------------------------------
    GITHUB_TOKEN: str = ""
    GITHUB_ENABLED: bool = False

    # -- Matter / Smart Home --------------------------------------------------
    MATTER_CONTROLLER_URL: str = "http://localhost:5580"

    # -- Wolfram Alpha --------------------------------------------------------
    WOLFRAM_APP_ID: str = ""

    # -- Perplexity -----------------------------------------------------------
    PERPLEXITY_API_KEY: str = ""

    # -- Alpha Vantage (Financial Data) ---------------------------------------
    ALPHA_VANTAGE_API_KEY: str = ""

    # -- AviationStack (Flight Tracking) --------------------------------------
    AVIATIONSTACK_API_KEY: str = ""

    # -- Google Maps Platform -------------------------------------------------
    GOOGLE_MAPS_API_KEY: str = ""

    # -- Edamam (Nutrition & Recipes) -----------------------------------------
    EDAMAM_APP_ID: str = ""
    EDAMAM_APP_KEY: str = ""

    # -- Web Search -----------------------------------------------------------
    TAVILY_API_KEY: str = ""
    SERPAPI_API_KEY: str = ""
    BRAVE_SEARCH_API_KEY: str = ""

    # -- Weather (OpenWeatherMap) ---------------------------------------------
    WEATHER_API_KEY: str = ""

    # -- News (NewsAPI) -------------------------------------------------------
    NEWS_API_KEY: str = ""

    # -- Spotify --------------------------------------------------------------
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REFRESH_TOKEN: str = ""

    # -- Auth / Security ------------------------------------------------------
    JWT_SECRET_KEY: str = "change-me-to-a-random-64-char-hex-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    AES_KEY: str = "change-me-to-a-valid-fernet-key"

    # -- WebAuthn / Passkeys --------------------------------------------------
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "J.A.R.V.I.S."
    WEBAUTHN_ORIGIN: str = "http://localhost:3000"

    # -- CORS -----------------------------------------------------------------
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> List[str]:
        """Accept a JSON-encoded list *or* a comma-separated string."""
        if isinstance(v, str):
            if v.startswith("["):
                import json

                return json.loads(v)
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return list(v)  # type: ignore[arg-type]


settings = Settings()
