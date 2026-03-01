"""Integration clients package for J.A.R.V.I.S.

Exposes all third-party service clients used by the agent system.
"""

from app.integrations.calendar import CalendarClient
from app.integrations.elevenlabs import ElevenLabsClient
from app.integrations.gmail import GmailClient
from app.integrations.llm_client import LLMClient
from app.integrations.matter import MatterClient
from app.integrations.news import NewsClient
from app.integrations.spotify import SpotifyClient
from app.integrations.vision import VisionClient
from app.integrations.weather import WeatherClient
from app.integrations.web_search import WebSearchClient

__all__ = [
    "CalendarClient",
    "ElevenLabsClient",
    "GmailClient",
    "LLMClient",
    "MatterClient",
    "NewsClient",
    "SpotifyClient",
    "VisionClient",
    "WeatherClient",
    "WebSearchClient",
]
