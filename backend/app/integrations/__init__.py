"""Integration clients package for J.A.R.V.I.S.

Exposes all third-party service clients used by the agent system.
"""

from app.integrations.calendar import CalendarClient
from app.integrations.elevenlabs import ElevenLabsClient
from app.integrations.gmail import GmailClient
from app.integrations.llm_client import LLMClient
from app.integrations.llm import BaseLLMClient, LLMProvider, get_llm_client
from app.integrations.matter import MatterClient
from app.integrations.mcp_client import MCPStdioClient
from app.integrations.news import NewsClient
from app.integrations.spotify import SpotifyClient
from app.integrations.vision import VisionClient
from app.integrations.weather import WeatherClient
from app.integrations.web_search import WebSearchClient
from app.integrations.wolfram import WolframClient
from app.integrations.perplexity import PerplexityClient
from app.integrations.alpha_vantage import AlphaVantageClient
from app.integrations.flight_tracker import FlightTrackerClient
from app.integrations.google_maps import GoogleMapsClient
from app.integrations.edamam import EdamamClient
from app.integrations.google_drive import GoogleDriveClient
from app.integrations.slack_client import SlackClient
from app.integrations.github_client import GitHubClient

__all__ = [
    "BaseLLMClient",
    "CalendarClient",
    "ElevenLabsClient",
    "GmailClient",
    "LLMClient",
    "LLMProvider",
    "MatterClient",
    "MCPStdioClient",
    "NewsClient",
    "SpotifyClient",
    "VisionClient",
    "WeatherClient",
    "WebSearchClient",
    "get_llm_client",
    "WolframClient",
    "PerplexityClient",
    "AlphaVantageClient",
    "FlightTrackerClient",
    "GoogleMapsClient",
    "EdamamClient",
    "GoogleDriveClient",
    "SlackClient",
    "GitHubClient",
]
