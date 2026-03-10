"""
Sports integration for JARVIS — ESPN public API.

Provides BYU Cougars football (and other sports) scores, schedules,
and standings via ESPN's free, keyless public endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://site.api.espn.com/apis/site/v2/sports"
_TIMEOUT = 10.0

# ESPN team IDs for quick reference
_TEAM_IDS = {
    "byu": 252,
    "byu cougars": 252,
    "utah": 254,
    "utah state": 328,
}

# Sport/league paths
_SPORT_PATHS = {
    "football": "football/college-football",
    "college-football": "football/college-football",
    "cfb": "football/college-football",
    "nfl": "football/nfl",
    "basketball": "basketball/mens-college-basketball",
    "college-basketball": "basketball/mens-college-basketball",
    "cbb": "basketball/mens-college-basketball",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "nhl": "hockey/nhl",
    "soccer": "soccer/usa.1",
    "mls": "soccer/usa.1",
}


async def get_team_info(team: str, sport: str = "football") -> dict[str, Any]:
    """Get basic team info (record, logo, next game)."""
    team_id = _resolve_team(team)
    sport_path = _SPORT_PATHS.get(sport.lower(), _SPORT_PATHS["football"])

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/{sport_path}/teams/{team_id}")
        resp.raise_for_status()
        data = resp.json()

    t = data.get("team", {})
    record = t.get("record", {}).get("items", [{}])[0].get("summary", "N/A")
    standing = t.get("standingSummary", "")

    next_event = {}
    events = t.get("nextEvent", [])
    if events:
        ev = events[0]
        next_event = {
            "name": ev.get("name", ""),
            "date": ev.get("date", ""),
            "shortName": ev.get("shortName", ""),
        }

    return {
        "name": t.get("displayName", team),
        "abbreviation": t.get("abbreviation", ""),
        "record": record,
        "standing": standing,
        "next_game": next_event,
        "color": t.get("color", ""),
        "logo": t.get("logos", [{}])[0].get("href", "") if t.get("logos") else "",
    }


async def get_schedule(team: str, sport: str = "football", season: str = "") -> list[dict[str, Any]]:
    """Get a team's schedule for the current (or specified) season."""
    team_id = _resolve_team(team)
    sport_path = _SPORT_PATHS.get(sport.lower(), _SPORT_PATHS["football"])

    url = f"{_BASE}/{sport_path}/teams/{team_id}/schedule"
    params = {}
    if season:
        params["season"] = season

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    games = []
    for ev in data.get("events", []):
        comp = ev.get("competitions", [{}])[0] if ev.get("competitions") else {}
        competitors = comp.get("competitors", [])

        home = away = {}
        for c in competitors:
            if c.get("homeAway") == "home":
                home = c
            else:
                away = c

        result = ""
        if comp.get("status", {}).get("type", {}).get("completed"):
            home_score = home.get("score", {})
            away_score = away.get("score", {})
            h_val = home_score.get("value", home_score) if isinstance(home_score, dict) else home_score
            a_val = away_score.get("value", away_score) if isinstance(away_score, dict) else away_score
            winner = home.get("winner", False)
            result = f"{'W' if winner else 'L'} {h_val}-{a_val}" if str(team_id) == str(home.get("id", "")) else f"{'W' if not winner else 'L'} {a_val}-{h_val}"

        games.append({
            "date": ev.get("date", ""),
            "name": ev.get("name", ""),
            "shortName": ev.get("shortName", ""),
            "home": home.get("team", {}).get("displayName", ""),
            "away": away.get("team", {}).get("displayName", ""),
            "result": result,
            "completed": comp.get("status", {}).get("type", {}).get("completed", False),
        })

    return games


async def get_scoreboard(sport: str = "football", groups: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """Get today's scoreboard for a sport/league."""
    sport_path = _SPORT_PATHS.get(sport.lower(), _SPORT_PATHS["football"])

    params: dict[str, Any] = {"limit": limit}
    if groups:
        params["groups"] = groups

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/{sport_path}/scoreboard", params=params)
        resp.raise_for_status()
        data = resp.json()

    games = []
    for ev in data.get("events", []):
        comp = ev.get("competitions", [{}])[0] if ev.get("competitions") else {}
        competitors = comp.get("competitors", [])

        teams_info = []
        for c in competitors:
            score = c.get("score", "0")
            teams_info.append({
                "name": c.get("team", {}).get("displayName", ""),
                "abbreviation": c.get("team", {}).get("abbreviation", ""),
                "score": score,
                "homeAway": c.get("homeAway", ""),
                "winner": c.get("winner", False),
            })

        status = comp.get("status", {})
        games.append({
            "name": ev.get("name", ""),
            "shortName": ev.get("shortName", ""),
            "date": ev.get("date", ""),
            "status": status.get("type", {}).get("description", ""),
            "detail": status.get("type", {}).get("detail", ""),
            "teams": teams_info,
            "completed": status.get("type", {}).get("completed", False),
        })

    return games


async def get_standings(sport: str = "football", group: str = "") -> list[dict[str, Any]]:
    """Get current standings for a sport/league."""
    sport_path = _SPORT_PATHS.get(sport.lower(), _SPORT_PATHS["football"])

    params = {}
    if group:
        params["group"] = group

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/{sport_path}/standings", params=params)
        resp.raise_for_status()
        data = resp.json()

    standings = []
    for group_data in data.get("children", []):
        group_name = group_data.get("name", "")
        for entry in group_data.get("standings", {}).get("entries", []):
            team = entry.get("team", {})
            stats = {s["name"]: s.get("displayValue", s.get("value", "")) for s in entry.get("stats", [])}
            standings.append({
                "group": group_name,
                "team": team.get("displayName", ""),
                "abbreviation": team.get("abbreviation", ""),
                "wins": stats.get("wins", ""),
                "losses": stats.get("losses", ""),
                "overall": stats.get("overall", ""),
                "conference": stats.get("conferenceRecord", ""),
            })

    return standings


def _resolve_team(team: str) -> int:
    """Resolve a team name/alias to an ESPN team ID."""
    lower = team.lower().strip()
    if lower in _TEAM_IDS:
        return _TEAM_IDS[lower]
    # Try numeric ID
    try:
        return int(team)
    except (ValueError, TypeError):
        pass
    # Partial match
    for key, tid in _TEAM_IDS.items():
        if lower in key or key in lower:
            return tid
    raise ValueError(f"Unknown team: '{team}'. Use a team name like 'BYU' or an ESPN team ID number.")
