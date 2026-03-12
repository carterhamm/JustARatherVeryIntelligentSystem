"""
Sports integration for JARVIS — ESPN public API.

Provides scores, schedules, standings via ESPN's free, keyless endpoints.
Includes smart fallbacks: scoreboard → team schedule → web search.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://site.api.espn.com/apis/site/v2/sports"
_TIMEOUT = 10.0

# User's local timezone — used for "today" calculations so we don't
# accidentally query the wrong ESPN date when UTC is a day ahead.
_USER_TZ = ZoneInfo("America/Denver")  # Mountain Time


def _local_now() -> datetime:
    """Current time in the user's timezone (Mountain Time)."""
    return datetime.now(tz=_USER_TZ)

# ESPN team IDs for quick reference
_TEAM_IDS = {
    "byu": 252,
    "byu cougars": 252,
    "brigham young": 252,
    "utah": 254,
    "utah utes": 254,
    "utah state": 328,
    "utah state aggies": 328,
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

# Which sport is currently "in season" (rough month ranges)
_SPORT_SEASONS = {
    "football": (8, 1),       # Aug–Jan
    "basketball": (10, 4),    # Oct–Apr (March Madness into April)
    "mlb": (3, 10),           # Mar–Oct
    "nhl": (10, 6),           # Oct–Jun
}


def detect_sport_for_team(team: str, explicit_sport: str = "") -> str:
    """If no sport specified, infer from current month which sport is in season.

    For college teams like BYU, basketball and football are the main two.
    Returns a single sport. For overlap months (Nov-Jan), returns "both"
    so the caller can try both.
    """
    if explicit_sport:
        return explicit_sport

    month = _local_now().month

    # Overlap months: both football and basketball are active
    if month in (11, 12, 1):
        return "both"

    # Basketball only: Feb–Apr (March Madness)
    if month in (2, 3, 4):
        return "basketball"

    # Football only: Aug–Oct
    if month in (8, 9, 10):
        return "football"

    # Off-season (May–Jul): default basketball (could be NBA playoffs)
    return "basketball"


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
        status_info = comp.get("status", {}).get("type", {})
        completed = status_info.get("completed", False)
        status_desc = status_info.get("description", "")

        if completed:
            home_score = home.get("score", {})
            away_score = away.get("score", {})
            h_val = home_score.get("value", home_score) if isinstance(home_score, dict) else home_score
            a_val = away_score.get("value", away_score) if isinstance(away_score, dict) else away_score

            home_team_id = home.get("id") or home.get("team", {}).get("id", "")
            is_home = str(team_id) == str(home_team_id)
            winner = home.get("winner", False)
            if is_home:
                result = f"{'W' if winner else 'L'} {h_val}-{a_val}"
            else:
                result = f"{'W' if not winner else 'L'} {a_val}-{h_val}"

        games.append({
            "date": ev.get("date", ""),
            "name": ev.get("name", ""),
            "shortName": ev.get("shortName", ""),
            "home": home.get("team", {}).get("displayName", ""),
            "away": away.get("team", {}).get("displayName", ""),
            "result": result,
            "completed": completed,
            "status": status_desc,
        })

    return games


async def get_scoreboard(sport: str = "football", groups: str = "", limit: int = 25, dates: str = "") -> list[dict[str, Any]]:
    """Get scoreboard for a sport/league. Optionally pass dates=YYYYMMDD."""
    sport_path = _SPORT_PATHS.get(sport.lower(), _SPORT_PATHS["football"])

    params: dict[str, Any] = {"limit": limit}
    if groups:
        params["groups"] = groups
    if dates:
        params["dates"] = dates

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


async def get_recent_team_result(team: str, sport: str = "basketball") -> str | None:
    """Smart lookup: find the most recent game result for a team.

    Checks scoreboard (today + yesterday) for the team, then falls back to
    the team schedule for the last completed game.

    Returns a human-readable string or None if nothing found.
    """
    team_lower = team.lower().strip()
    team_id = _resolve_team(team)
    sport_path = _SPORT_PATHS.get(sport.lower(), _SPORT_PATHS.get("basketball"))

    # 1. Check today's scoreboard (use local time so "today" matches user's day)
    now = _local_now()
    today_str = now.strftime("%Y%m%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y%m%d")

    for date_str in [today_str, yesterday_str]:
        try:
            games = await get_scoreboard(sport=sport, dates=date_str, limit=50)
            for g in games:
                team_names = [t["name"].lower() for t in g.get("teams", [])]
                team_abbrs = [t["abbreviation"].lower() for t in g.get("teams", [])]
                if any(team_lower in n or "byu" in n for n in team_names) or any(team_lower in a for a in team_abbrs):
                    teams = g["teams"]
                    t1 = f"{teams[0]['name']} {teams[0]['score']}"
                    t2 = f"{teams[1]['name']} {teams[1]['score']}"
                    status = g.get("detail") or g.get("status", "")
                    return f"{t1} vs {t2} — {status} (on {g.get('date', date_str)[:10]})"
        except Exception as exc:
            logger.debug("Scoreboard check failed for %s: %s", date_str, exc)

    # 2. Fall back to team schedule — find most recent completed game
    try:
        schedule = await get_schedule(team, sport)
        completed = [g for g in schedule if g["completed"]]
        if completed:
            last = completed[-1]
            return f"{last['name']}: {last['result']} (on {last['date'][:10]})"
    except Exception as exc:
        logger.debug("Schedule fallback failed: %s", exc)

    return None


async def get_team_games_today(team: str, sport: str = "basketball") -> list[dict[str, Any]]:
    """Find today's game(s) for a specific team using scoreboard + schedule.

    Checks today's scoreboard first, then falls back to the full schedule
    and filters for games matching today's local date. Returns a list of
    game dicts (may be empty).
    """
    team_lower = team.lower().strip()
    today = _local_now()
    today_str = today.strftime("%Y%m%d")
    today_iso = today.strftime("%Y-%m-%d")

    # 1. Check today's scoreboard (most reliable for live/today games)
    try:
        games = await get_scoreboard(sport=sport, dates=today_str, limit=50)
        for g in games:
            team_names = [t["name"].lower() for t in g.get("teams", [])]
            team_abbrs = [t.get("abbreviation", "").lower() for t in g.get("teams", [])]
            if any(team_lower in n for n in team_names) or any(team_lower in a for a in team_abbrs):
                return [g]
    except Exception as exc:
        logger.debug("Scoreboard check for %s on %s failed: %s", team, today_str, exc)

    # 2. Fall back to team schedule and filter for today's date
    #    ESPN dates are in UTC — convert to local time for accurate day comparison
    try:
        schedule = await get_schedule(team, sport)
        today_games = []
        for g in schedule:
            raw_date = g.get("date", "")
            if raw_date:
                try:
                    game_dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    game_local = game_dt.astimezone(_USER_TZ)
                    game_date = game_local.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    game_date = raw_date[:10]
            else:
                game_date = ""
            if game_date == today_iso:
                today_games.append(g)
        if today_games:
            return today_games
    except Exception as exc:
        logger.debug("Schedule check for %s on %s failed: %s", team, today_str, exc)

    return []


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
            team_data = entry.get("team", {})
            stats = {s["name"]: s.get("displayValue", s.get("value", "")) for s in entry.get("stats", [])}
            standings.append({
                "group": group_name,
                "team": team_data.get("displayName", ""),
                "abbreviation": team_data.get("abbreviation", ""),
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
