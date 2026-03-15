"""
Smart multi-stop directions with personal context for JARVIS.

Uses JARVIS's knowledge of Mr. Stark's preferences combined with
Google Maps Directions API + Places API to plan intelligent routes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("jarvis.smart_directions")


async def plan_smart_route(request: str, user_id: str) -> dict[str, Any]:
    """Plan an intelligent multi-stop route using personal context.

    1. Parse the request with Gemini to extract stops/needs.
    2. For each stop, search knowledge base for preferences.
    3. Get current location from DB (posted by iOS app).
    4. Use Google Maps Places API to find options near the route.
    5. Use Google Maps Directions API to calculate optimal order.
    6. Return structured route with alternatives.
    """
    # Step 1: Parse route request into structured stops
    stops = await _parse_route_request(request)
    if not stops:
        return {
            "success": False,
            "error": "Could not understand the route request.",
            "itinerary": "",
        }

    logger.info("Parsed %d stops from request: %s", len(stops), [s["need"] for s in stops])

    # Step 2: Get current location
    origin = await _get_current_location(user_id)
    logger.info("Origin: %s", origin.get("display", "unknown"))

    # Step 3: Search preferences for each stop
    for stop in stops:
        stop["preferences"] = await _search_preferences(
            stop["need"],
            stop.get("preference_query", stop["need"]),
            user_id,
        )

    # Step 4: Find places along route for each stop
    places_per_stop: list[list[dict]] = []
    for stop in stops:
        places = await _find_places_along_route(
            stop["need"],
            origin,
            stop.get("preferences", {}),
            optimize_for=stop.get("optimize"),
        )
        places_per_stop.append(places)
        # Pick the best place for this stop
        if places:
            stop["selected_place"] = places[0]
            stop["alternatives"] = places[1:3]
        else:
            stop["selected_place"] = None
            stop["alternatives"] = []

    # Step 5: Optimize route order
    route = await _optimize_route(stops, origin)

    # Step 6: Format the itinerary
    itinerary = _format_itinerary(route, stops)

    return {
        "success": True,
        "origin": origin,
        "stops": stops,
        "route": route,
        "itinerary": itinerary,
    }


async def _parse_route_request(request: str) -> list[dict[str, Any]]:
    """Use Gemini to extract structured stops from a natural language request.

    Returns a list of dicts like:
    [
        {"need": "haircut", "preference_query": "barber haircut place", "flexible": true},
        {"need": "gas", "preference_query": "gas station", "flexible": true, "optimize": "price"},
        {"need": "grocery store", "preference_query": "favorite store grocery", "flexible": false},
    ]
    """
    if not settings.GOOGLE_GEMINI_API_KEY:
        # Fallback: simple keyword extraction
        return _parse_route_fallback(request)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GOOGLE_GEMINI_API_KEY)

        system_prompt = (
            "You are a route planning assistant. Extract structured stops from "
            "the user's request. Return ONLY valid JSON — an array of objects.\n\n"
            "Each object has:\n"
            '- "need": short description of what they need (e.g. "haircut", "gas", "groceries")\n'
            '- "preference_query": search terms to find user preferences (e.g. "barber haircut place")\n'
            '- "place_type": Google Maps place type (e.g. "hair_care", "gas_station", "grocery_or_supermarket")\n'
            '- "search_keyword": keyword for Google Maps search (e.g. "barber", "gas station", "grocery store")\n'
            '- "flexible": true if any location works, false if the user specified a specific place\n'
            '- "optimize": null normally, "price" for gas/fuel stops\n'
            '- "specific_place": the exact place name if the user mentioned one, else null\n\n'
            "Common place_type values: hair_care, gas_station, grocery_or_supermarket, "
            "pharmacy, car_wash, bank, post_office, gym, restaurant, cafe, "
            "shopping_mall, hardware_store, pet_store, laundry, dry_cleaning\n\n"
            "Output ONLY the JSON array, no markdown fences, no explanation."
        )

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=request)],
                ),
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        stops = json.loads(raw)
        if not isinstance(stops, list):
            logger.warning("Gemini returned non-list: %s", type(stops))
            return _parse_route_fallback(request)

        # Validate and normalize
        validated: list[dict[str, Any]] = []
        for s in stops:
            validated.append({
                "need": s.get("need", "unknown"),
                "preference_query": s.get("preference_query", s.get("need", "")),
                "place_type": s.get("place_type"),
                "search_keyword": s.get("search_keyword", s.get("need", "")),
                "flexible": s.get("flexible", True),
                "optimize": s.get("optimize"),
                "specific_place": s.get("specific_place"),
            })
        return validated

    except Exception as exc:
        logger.warning("Gemini route parsing failed: %s", exc)
        return _parse_route_fallback(request)


def _parse_route_fallback(request: str) -> list[dict[str, Any]]:
    """Simple keyword-based fallback when Gemini is unavailable."""
    keywords = {
        "haircut": {"place_type": "hair_care", "search_keyword": "barber haircut"},
        "barber": {"place_type": "hair_care", "search_keyword": "barber"},
        "gas": {"place_type": "gas_station", "search_keyword": "gas station", "optimize": "price"},
        "fuel": {"place_type": "gas_station", "search_keyword": "gas station", "optimize": "price"},
        "grocery": {"place_type": "grocery_or_supermarket", "search_keyword": "grocery store"},
        "store": {"place_type": "grocery_or_supermarket", "search_keyword": "grocery store"},
        "pharmacy": {"place_type": "pharmacy", "search_keyword": "pharmacy"},
        "bank": {"place_type": "bank", "search_keyword": "bank"},
        "car wash": {"place_type": "car_wash", "search_keyword": "car wash"},
        "post office": {"place_type": "post_office", "search_keyword": "post office"},
        "restaurant": {"place_type": "restaurant", "search_keyword": "restaurant"},
        "coffee": {"place_type": "cafe", "search_keyword": "coffee shop"},
    }

    request_lower = request.lower()
    stops: list[dict[str, Any]] = []
    matched_needs: set[str] = set()

    for keyword, info in keywords.items():
        if keyword in request_lower and keyword not in matched_needs:
            matched_needs.add(keyword)
            stops.append({
                "need": keyword,
                "preference_query": keyword,
                "place_type": info["place_type"],
                "search_keyword": info["search_keyword"],
                "flexible": True,
                "optimize": info.get("optimize"),
                "specific_place": None,
            })

    return stops


async def _get_current_location(user_id: str) -> dict[str, Any]:
    """Get user's current location from DB preferences or Mac Mini Find My.

    Returns dict with lat, lng, display, and source fields.
    """
    # Try DB preferences first (populated by iOS Shortcut)
    if user_id:
        try:
            from sqlalchemy import select
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as _AS
            from sqlalchemy.orm import sessionmaker
            from app.models.user import User

            engine = create_async_engine(settings.DATABASE_URL)
            async_session = sessionmaker(engine, class_=_AS, expire_on_commit=False)
            async with async_session() as session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                if user and user.preferences:
                    loc_data = user.preferences.get("current_location")
                    if loc_data and loc_data.get("latitude") and loc_data.get("longitude"):
                        lat, lng = loc_data["latitude"], loc_data["longitude"]
                        city = loc_data.get("city", "")
                        await engine.dispose()
                        return {
                            "lat": lat,
                            "lng": lng,
                            "latlng": f"{lat},{lng}",
                            "display": city or f"{lat:.4f},{lng:.4f}",
                            "source": "ios_shortcut",
                            "updated_at": loc_data.get("updated_at"),
                        }
            await engine.dispose()
        except Exception as exc:
            logger.debug("DB location check failed: %s", exc)

    # Try Mac Mini Find My
    try:
        from app.integrations.mac_mini import get_location, is_configured as mini_configured
        if mini_configured():
            loc = await get_location()
            if loc.get("found"):
                lat, lng = loc["latitude"], loc["longitude"]
                return {
                    "lat": lat,
                    "lng": lng,
                    "latlng": f"{lat},{lng}",
                    "display": f"{lat:.4f},{lng:.4f}",
                    "source": "find_my",
                }
    except Exception as exc:
        logger.debug("Find My location failed: %s", exc)

    # Fallback: Orem, UT (user's home area)
    logger.info("Using fallback location (Orem, UT)")
    return {
        "lat": 40.2969,
        "lng": -111.6946,
        "latlng": "40.2969,-111.6946",
        "display": "Orem, UT (approximate)",
        "source": "fallback",
    }


async def _search_preferences(
    need: str, query: str, user_id: str
) -> dict[str, Any]:
    """Search knowledge base and contacts for user preferences related to a need.

    Returns dict with preferred_places, notes, and any relevant context.
    """
    preferences: dict[str, Any] = {
        "preferred_places": [],
        "notes": [],
        "contact_matches": [],
    }

    # Search Qdrant knowledge base
    try:
        from app.db.qdrant import get_qdrant_store
        from app.graphrag.vector_store import VectorStore

        store = get_qdrant_store()
        vs = VectorStore(qdrant_store=store)
        results = await vs.search_similar(
            query=f"{need} {query} favorite preferred",
            limit=3,
            min_score=0.5,
        )
        if results:
            for hit in results:
                payload = hit.get("payload", {})
                text = payload.get("text", payload.get("content", ""))
                if text:
                    preferences["notes"].append(text[:300])
    except Exception:
        logger.debug("Qdrant preference search unavailable for '%s'", need)

    # Search local knowledge files
    try:
        from app.agents.tools import SearchKnowledgeTool

        kt = SearchKnowledgeTool()
        local_results = kt._search_local(f"{need} {query} favorite preferred", limit=3)
        for hit in local_results:
            payload = hit.get("payload", {})
            text = payload.get("text", payload.get("content", ""))
            if text and text[:200] not in [n[:200] for n in preferences["notes"]]:
                preferences["notes"].append(text[:300])
    except Exception:
        logger.debug("Local knowledge search failed for '%s'", need)

    # Search contacts for relevant businesses
    if user_id:
        try:
            from sqlalchemy import select
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as _AS
            from sqlalchemy.orm import sessionmaker
            from app.models.contact import Contact
            from app.core.encryption import decrypt_message

            engine = create_async_engine(settings.DATABASE_URL)
            async_session = sessionmaker(engine, class_=_AS, expire_on_commit=False)
            async with async_session() as session:
                result = await session.execute(
                    select(Contact).where(Contact.user_id == user_id)
                )
                contacts = result.scalars().all()
            await engine.dispose()

            query_lower = query.lower()
            for c in contacts:
                try:
                    company = decrypt_message(c.company, c.user_id) if c.company else ""
                    notes = decrypt_message(c.notes, c.user_id) if c.notes else ""
                    name = ""
                    if c.first_name:
                        name += decrypt_message(c.first_name, c.user_id) or ""
                    if c.last_name:
                        name += " " + (decrypt_message(c.last_name, c.user_id) or "")
                    searchable = f"{name} {company} {notes}".lower()
                    if any(word in searchable for word in query_lower.split() if len(word) > 2):
                        address = decrypt_message(c.address, c.user_id) if c.address else ""
                        phone = decrypt_message(c.phone, c.user_id) if c.phone else ""
                        preferences["contact_matches"].append({
                            "name": name.strip(),
                            "company": company,
                            "address": address,
                            "phone": phone,
                        })
                except Exception:
                    continue
        except Exception:
            logger.debug("Contact search failed for '%s'", need)

    return preferences


async def _find_places_along_route(
    need: str,
    origin: dict[str, Any],
    preferences: dict[str, Any],
    optimize_for: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Find candidate places for a stop using Google Maps.

    Uses nearby search and text search, ranks by distance, rating,
    and user preferences. For gas stations, can optimize by price.
    """
    from app.integrations.google_maps import GoogleMapsClient

    maps = GoogleMapsClient()
    origin_str = origin.get("latlng", "")
    if not origin_str:
        return []

    candidates: list[dict[str, Any]] = []

    # If user has a preferred place from contacts with an address, put it first
    for contact in preferences.get("contact_matches", []):
        if contact.get("address"):
            candidates.append({
                "name": contact.get("company") or contact.get("name", "Preferred"),
                "address": contact["address"],
                "source": "contacts",
                "preferred": True,
                "rating": None,
                "lat": None,
                "lng": None,
            })

    # Search Google Maps for nearby places
    search_keyword = need
    try:
        nearby_result = await maps.places_search(
            search_keyword,
            location=origin_str,
            radius=15000,  # 15km radius
        )
        if not nearby_result.get("error"):
            for p in nearby_result.get("results", [])[:8]:
                ploc = p.get("geometry", {}).get("location", {})
                candidates.append({
                    "name": p.get("name", "Unknown"),
                    "address": p.get("formatted_address", ""),
                    "source": "google_maps",
                    "preferred": False,
                    "rating": p.get("rating"),
                    "user_ratings_total": p.get("user_ratings_total", 0),
                    "lat": ploc.get("lat"),
                    "lng": ploc.get("lng"),
                    "place_id": p.get("place_id"),
                    "types": p.get("types", []),
                    "price_level": p.get("price_level"),
                    "open_now": p.get("opening_hours", {}).get("open_now"),
                })
    except Exception as exc:
        logger.warning("Places search failed for '%s': %s", need, exc)

    if not candidates:
        return []

    # Calculate distance from origin for non-preferred candidates
    for c in candidates:
        if c.get("lat") and c.get("lng"):
            c["distance_km"] = _haversine(
                origin["lat"], origin["lng"], c["lat"], c["lng"]
            )
        else:
            c["distance_km"] = None

    # Score and rank candidates
    scored = _rank_candidates(candidates, optimize_for, preferences)
    return scored[:5]


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in km between two lat/lng points."""
    import math

    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _rank_candidates(
    candidates: list[dict[str, Any]],
    optimize_for: Optional[str],
    preferences: dict[str, Any],
) -> list[dict[str, Any]]:
    """Rank place candidates by relevance score."""
    for c in candidates:
        score = 0.0

        # Preferred places from contacts get a huge boost
        if c.get("preferred"):
            score += 100.0

        # Rating bonus (0-5 scale, weight x3)
        if c.get("rating"):
            score += c["rating"] * 3.0

        # Popularity bonus (log scale)
        total_ratings = c.get("user_ratings_total", 0)
        if total_ratings > 0:
            import math
            score += math.log10(total_ratings + 1) * 2.0

        # Distance penalty (closer is better)
        dist = c.get("distance_km")
        if dist is not None:
            score -= dist * 0.5  # -0.5 points per km

        # Open now bonus
        if c.get("open_now"):
            score += 5.0

        # Price optimization (for gas)
        if optimize_for == "price" and c.get("price_level") is not None:
            score -= c["price_level"] * 2.0  # lower price = better

        # Check if name matches any preference notes
        name_lower = c.get("name", "").lower()
        for note in preferences.get("notes", []):
            if name_lower and name_lower in note.lower():
                score += 20.0  # mentioned in knowledge base

        c["_score"] = score

    candidates.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return candidates


async def _optimize_route(
    stops: list[dict[str, Any]], origin: dict[str, Any]
) -> dict[str, Any]:
    """Calculate the optimal route order using Google Maps Directions API.

    Uses waypoints optimization when there are intermediate stops.
    Returns route details with total time, distance, and per-leg info.
    """
    from app.integrations.google_maps import GoogleMapsClient

    maps = GoogleMapsClient()
    origin_str = origin.get("latlng", "")

    # Build waypoint addresses from selected places
    waypoint_addresses: list[str] = []
    for stop in stops:
        place = stop.get("selected_place")
        if place:
            if place.get("lat") and place.get("lng"):
                waypoint_addresses.append(f"{place['lat']},{place['lng']}")
            elif place.get("address"):
                waypoint_addresses.append(place["address"])
            else:
                waypoint_addresses.append(stop["need"])
        else:
            waypoint_addresses.append(stop.get("search_keyword", stop["need"]))

    if not waypoint_addresses:
        return {"error": "No valid stops to route to.", "legs": []}

    route_data: dict[str, Any] = {
        "legs": [],
        "total_duration_text": "",
        "total_duration_seconds": 0,
        "total_distance_text": "",
        "total_distance_meters": 0,
        "waypoint_order": list(range(len(stops))),
    }

    if len(waypoint_addresses) == 1:
        # Single stop: simple directions
        result = await maps.directions(origin_str, waypoint_addresses[0])
        if result.get("error"):
            route_data["error"] = result["error"]
            return route_data

        routes = result.get("routes", [])
        if routes:
            leg = routes[0].get("legs", [{}])[0]
            route_data["legs"].append({
                "start": leg.get("start_address", origin.get("display", "")),
                "end": leg.get("end_address", waypoint_addresses[0]),
                "distance": leg.get("distance", {}),
                "duration": leg.get("duration", {}),
            })
            route_data["total_duration_text"] = leg.get("duration", {}).get("text", "")
            route_data["total_duration_seconds"] = leg.get("duration", {}).get("value", 0)
            route_data["total_distance_text"] = leg.get("distance", {}).get("text", "")
            route_data["total_distance_meters"] = leg.get("distance", {}).get("value", 0)

    else:
        # Multi-stop: use the last stop as destination, rest as waypoints
        destination = waypoint_addresses[-1]
        intermediate = waypoint_addresses[:-1]

        result = await maps.directions_with_waypoints(
            origin=origin_str,
            destination=destination,
            waypoints=intermediate,
            optimize=True,
        )

        if result.get("error"):
            route_data["error"] = result["error"]
            return route_data

        routes = result.get("routes", [])
        if routes:
            route = routes[0]
            # Google returns optimized waypoint order
            wp_order = route.get("waypoint_order", list(range(len(intermediate))))
            # Map back: waypoint_order indices refer to intermediate stops,
            # plus the final destination stays last
            full_order = list(wp_order) + [len(stops) - 1]
            route_data["waypoint_order"] = full_order

            total_seconds = 0
            total_meters = 0
            for leg in route.get("legs", []):
                route_data["legs"].append({
                    "start": leg.get("start_address", ""),
                    "end": leg.get("end_address", ""),
                    "distance": leg.get("distance", {}),
                    "duration": leg.get("duration", {}),
                })
                total_seconds += leg.get("duration", {}).get("value", 0)
                total_meters += leg.get("distance", {}).get("value", 0)

            # Format totals
            hours, remainder = divmod(total_seconds, 3600)
            minutes = remainder // 60
            if hours:
                route_data["total_duration_text"] = f"{hours} hr {minutes} min"
            else:
                route_data["total_duration_text"] = f"{minutes} min"

            miles = total_meters / 1609.344
            route_data["total_distance_text"] = f"{miles:.1f} miles"
            route_data["total_duration_seconds"] = total_seconds
            route_data["total_distance_meters"] = total_meters

    return route_data


def _format_itinerary(route: dict[str, Any], stops: list[dict[str, Any]]) -> str:
    """Format the route as a natural JARVIS response."""
    if route.get("error"):
        return (
            f"I'm afraid I couldn't plan that route, sir. {route['error']} "
            "Perhaps try with more specific locations."
        )

    legs = route.get("legs", [])
    if not legs:
        return "No route data available, sir."

    wp_order = route.get("waypoint_order", list(range(len(stops))))
    ordered_stops = [stops[i] for i in wp_order if i < len(stops)]

    lines: list[str] = ["Very well, sir. I've planned your route:\n"]

    for i, (stop, leg) in enumerate(zip(ordered_stops, legs), 1):
        place = stop.get("selected_place", {})
        name = place.get("name", stop["need"].title()) if place else stop["need"].title()
        address = place.get("address", leg.get("end", ""))
        duration = leg.get("duration", {}).get("text", "")
        distance = leg.get("distance", {}).get("text", "")

        # Build the line
        detail_parts: list[str] = []
        if duration and distance:
            detail_parts.append(f"{duration}, {distance}")
        elif duration:
            detail_parts.append(duration)

        # Add context based on source
        if place and place.get("preferred"):
            detail_parts.append("from your contacts")
        elif place and place.get("rating"):
            detail_parts.append(f"rating: {place['rating']}")

        # Gas price note
        if stop.get("optimize") == "price":
            detail_parts.append("optimized for price")

        # Open status
        if place and place.get("open_now"):
            detail_parts.append("currently open")

        detail_str = f" ({', '.join(detail_parts)})" if detail_parts else ""

        # Ordinal labels
        ordinals = {1: "First stop", 2: "Second", 3: "Third", 4: "Fourth", 5: "Fifth"}
        ordinal = ordinals.get(i, f"Stop {i}")
        if i == len(ordered_stops):
            ordinal = "Finally" if i > 1 else "Your destination"

        if address and address != name:
            lines.append(f"  {i}. {ordinal}: {name} — {address}{detail_str}")
        else:
            lines.append(f"  {i}. {ordinal}: {name}{detail_str}")

        # Show alternatives if any
        alts = stop.get("alternatives", [])
        if alts:
            alt_names = [a.get("name", "?") for a in alts[:2]]
            lines.append(f"     Alternatives: {', '.join(alt_names)}")

    # Total
    total_time = route.get("total_duration_text", "")
    total_dist = route.get("total_distance_text", "")
    if total_time and total_dist:
        lines.append(f"\n  Total: {total_time}, {total_dist}")
    elif total_time:
        lines.append(f"\n  Total: {total_time}")

    return "\n".join(lines)
