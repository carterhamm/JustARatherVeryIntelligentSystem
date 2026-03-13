"""Application configuration loaded from environment variables."""

import base64
import os
import secrets
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _auto_jwt_secret() -> str:
    """Generate a secure JWT secret if the env var is missing or still default."""
    return secrets.token_hex(32)


def _auto_fernet_key() -> str:
    """Generate a valid Fernet key if the env var is missing or still default."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


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
    QDRANT_API_KEY: str = ""

    # -- Anthropic ------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""

    # -- Groq -----------------------------------------------------------------
    GROQ_API_KEY: str = ""

    # -- Google Gemini --------------------------------------------------------
    GOOGLE_GEMINI_API_KEY: str = ""

    # -- ZhipuAI GLM ---------------------------------------------------------
    GLM_API_KEY: str = ""

    # -- Stark Protocol (local Gemma via LM Studio) ----------------------------
    STARK_PROTOCOL_URL: str = "http://localhost:1234/v1"
    STARK_PROTOCOL_API_KEY: str = "lm-studio"
    STARK_PROTOCOL_ENABLED: bool = False

    # -- Cerebras (ultra-fast intent routing) -----------------------------------
    CEREBRAS_API_KEY: str = ""

    # -- Cloudflare AI Gateway (analytics, caching, fallback) -----------------
    # Create a gateway at https://dash.cloudflare.com → AI → AI Gateway
    # Routes Cerebras + Claude through CF edge for cost tracking & observability
    # Gemini excluded due to known streaming compatibility issue
    CLOUDFLARE_ACCOUNT_ID: str = ""
    CLOUDFLARE_AI_GATEWAY_ID: str = ""

    # -- Twilio (JARVIS phone number) -----------------------------------------
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""   # JARVIS's phone number (E.164 format)
    TWILIO_USER_PHONE: str = ""     # Owner's phone number to call/receive
    TWILIO_FAX_ENABLED: bool = False  # Fax capability (doesn't affect voice/SMS)

    # -- JARVIS Voice (Coqui TTS XTTS-v2) ------------------------------------
    JARVIS_VOICE_SERVER: str = ""  # path to jarvis_voice_training dir (local)
    JARVIS_VOICE_URL: str = ""  # remote endpoint URL (Modal deployment)
    JARVIS_VOICE_API_KEY: str = ""  # API key for remote endpoint
    JARVIS_VOICE_ENABLED: bool = False

    # -- Default LLM Provider -------------------------------------------------
    DEFAULT_LLM_PROVIDER: str = "gemini"

    # -- ElevenLabs -----------------------------------------------------------
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = "HsBg0b6zEPERDcKSn4Zl"

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

    # -- iMCP Bridge (remote macOS tools via Cloudflare tunnel) ---------------
    IMCP_BRIDGE_URL: str = ""      # e.g. https://imcp.malibupoint.dev
    IMCP_BRIDGE_KEY: str = ""      # Bearer token for auth

    # -- Mac Mini Agent (remote control via Cloudflare tunnel) ---------------
    MAC_MINI_AGENT_URL: str = ""   # e.g. https://agent.malibupoint.dev
    MAC_MINI_AGENT_KEY: str = ""   # Bearer token for auth

    # -- Camera / Security (TP-Link Tapo via Mac Mini daemon) ----------------
    CAMERA_PROXY_URL: str = ""       # Mac Mini camera daemon URL
    CAMERA_AUTH_TOKEN: str = ""      # Bearer token for Caddy auth proxy
    CAMERA_IP: str = ""              # Camera IP on local network
    CAMERA_USERNAME: str = ""        # Camera account username
    CAMERA_PASSWORD: str = ""        # Camera account password

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

    # -- Resend (outbound email from jarvis@malibupoint.dev) ------------------
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "JARVIS <jarvis@malibupoint.dev>"

    # -- Spotify --------------------------------------------------------------
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REFRESH_TOKEN: str = ""

    # -- Auth / Security ------------------------------------------------------
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    AES_KEY: str = ""

    # -- Setup Token (required to create the owner account) -------------------
    SETUP_TOKEN: str = ""

    # -- Service API Key (machine-to-machine auth for daemons) ----------------
    SERVICE_API_KEY: str = ""

    # -- Railway API (deployment monitoring / self-heal) ---------------------
    RAILWAY_API_TOKEN: str = ""
    RAILWAY_PROJECT_ID: str = ""
    RAILWAY_SERVICE_ID: str = ""
    RAILWAY_ENV_ID: str = ""

    # -- Owner contact -------------------------------------------------------
    OWNER_PHONE: str = ""

    # -- Login lockout -------------------------------------------------------
    LOGIN_MAX_ATTEMPTS: int = 3
    LOGIN_LOCKOUT_MINUTES: int = 30

    # -- Cryptographic constants -----------------------------------------------
    PBKDF2_ITERATIONS: int = 480_000

    @field_validator("JWT_SECRET_KEY", mode="before")
    @classmethod
    def _ensure_jwt_secret(cls, v: object) -> str:
        """Auto-generate a secure JWT secret if not explicitly set."""
        s = str(v) if v else ""
        if not s or s == "change-me-to-a-random-64-char-hex-string":
            return _auto_jwt_secret()
        return s

    @field_validator("AES_KEY", mode="before")
    @classmethod
    def _ensure_aes_key(cls, v: object) -> str:
        """Auto-generate a valid Fernet key if not explicitly set."""
        s = str(v) if v else ""
        if not s or s == "change-me-to-a-valid-fernet-key":
            return _auto_fernet_key()
        return s

    # -- WebAuthn / Passkeys --------------------------------------------------
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "J.A.R.V.I.S."
    WEBAUTHN_ORIGIN: str = "http://localhost:3000"

    # -- Apple / iOS ----------------------------------------------------------
    APPLE_TEAM_ID: str = "HKM8P29B68"
    APP_BUNDLE_ID: str = "dev.jarvis.malibupoint"

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


def cf_gateway_url(provider: str) -> str | None:
    """Build Cloudflare AI Gateway base URL for a provider.

    Returns None if AI Gateway is not configured, signaling direct API usage.
    Supported providers: 'anthropic', 'cerebras'.
    """
    if not settings.CLOUDFLARE_ACCOUNT_ID or not settings.CLOUDFLARE_AI_GATEWAY_ID:
        return None
    return (
        f"https://gateway.ai.cloudflare.com/v1/"
        f"{settings.CLOUDFLARE_ACCOUNT_ID}/"
        f"{settings.CLOUDFLARE_AI_GATEWAY_ID}/"
        f"{provider}"
    )
