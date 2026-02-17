"""SerpAPI Google Maps integration.

Uses SerpAPI's google_maps engine to scrape Google Maps SERP results
as a supplementary/validation layer. Free tier: 100 searches/month.

Cached searches are free — we set no_cache=false to maximize cache hits.
"""

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SERP_API_URL = "https://serpapi.com/search.json"

# Simple in-memory monthly usage counter.
# Resets when the month changes. In production, persist to Redis/DB.
_usage: dict[str, int] = {"month": 0, "count": 0}


def _get_current_month() -> int:
    """Return current month as YYYYMM integer."""
    t = time.gmtime()
    return t.tm_year * 100 + t.tm_mon


def get_monthly_usage() -> int:
    """Return the number of SerpAPI calls made this month."""
    current = _get_current_month()
    if _usage["month"] != current:
        _usage["month"] = current
        _usage["count"] = 0
    return _usage["count"]


def _increment_usage() -> int:
    """Increment and return the monthly usage counter."""
    current = _get_current_month()
    if _usage["month"] != current:
        _usage["month"] = current
        _usage["count"] = 0
    _usage["count"] += 1
    return _usage["count"]


async def _rate_limit():
    """Simple rate limiter — sleep to stay under RPS limit."""
    delay = 1.0 / settings.serp_api_rps
    await asyncio.sleep(delay)


def _parse_serp_result(result: dict) -> dict:
    """Parse a SerpAPI google_maps result into our standard lead format."""
    gps = result.get("gps_coordinates", {})

    return {
        "place_id": result.get("place_id", result.get("data_id", "")),
        "name": result.get("title", "Unknown"),
        "address": result.get("address"),
        "phone": result.get("phone"),
        "website": result.get("website"),
        "rating": result.get("rating"),
        "review_count": result.get("reviews"),
        "types": [result.get("type", "")].copy() if result.get("type") else [],
        "business_type": result.get("type"),
        "latitude": gps.get("latitude"),
        "longitude": gps.get("longitude"),
        "opening_hours": {"text": result.get("operating_hours")} if result.get("operating_hours") else None,
        "photos": [{"url": result.get("thumbnail")}] if result.get("thumbnail") else [],
        "price_level": None,
        "business_status": None,
        "maps_url": result.get("place_id_search"),
        "source": "serp_api",
        "raw_data": result,
    }


async def search_google_maps(
    query: str,
    latitude: float,
    longitude: float,
    zoom: int = 14,
    max_pages: int = 1,
    skip_if_over_limit: bool = True,
) -> tuple[list[dict], int]:
    """Search Google Maps via SerpAPI.

    Free tier: 100 searches/month. Cached results are free (no_cache=false).

    Args:
        query: Search query (e.g., "restaurants").
        latitude: Center latitude.
        longitude: Center longitude.
        zoom: Google Maps zoom level (affects area covered). 14 ~ city level.
        max_pages: Maximum pages of results to fetch.
        skip_if_over_limit: If True, return empty when monthly limit is exceeded.

    Returns:
        Tuple of (list of parsed result dicts, number of API calls made).
    """
    if not settings.serpapi_key:
        logger.warning("SerpAPI key not configured — skipping SERP search")
        return [], 0

    # Check monthly limit
    current_usage = get_monthly_usage()
    limit = settings.serpapi_monthly_limit

    if current_usage >= limit:
        if skip_if_over_limit:
            logger.warning(
                "SerpAPI monthly limit reached (%d/%d) — skipping search",
                current_usage, limit,
            )
            return [], 0
        logger.warning(
            "SerpAPI monthly limit reached (%d/%d) — proceeding anyway (skip_if_over_limit=False)",
            current_usage, limit,
        )

    if current_usage >= limit - 10:
        logger.warning(
            "SerpAPI approaching monthly limit: %d/%d searches used",
            current_usage, limit,
        )

    results: list[dict] = []
    api_calls = 0
    start = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(max_pages):
            # Re-check limit before each call
            if skip_if_over_limit and get_monthly_usage() >= limit:
                logger.warning("SerpAPI limit hit mid-search — stopping")
                break

            await _rate_limit()
            _increment_usage()
            api_calls += 1

            params = {
                "engine": "google_maps",
                "q": query,
                "ll": f"@{latitude},{longitude},{zoom}z",
                "type": "search",
                "api_key": settings.serpapi_key,
                "start": start,
                "no_cache": "false",  # Use cached results (free)
            }

            try:
                response = await client.get(SERP_API_URL, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "SerpAPI error: %d %s",
                    e.response.status_code,
                    e.response.text[:500],
                )
                break

            data = response.json()

            if data.get("error"):
                logger.error("SerpAPI error response: %s", data["error"])
                break

            local_results = data.get("local_results", [])
            if not local_results:
                break

            for item in local_results:
                results.append(_parse_serp_result(item))

            logger.debug(
                "SerpAPI page %d: %d results for '%s' at (%.4f, %.4f) [usage: %d/%d]",
                page + 1, len(local_results), query, latitude, longitude,
                get_monthly_usage(), limit,
            )

            # Check for next page
            serpapi_pagination = data.get("serpapi_pagination", {})
            if not serpapi_pagination.get("next"):
                break

            start += len(local_results)

    logger.info(
        "SerpAPI search complete: %d results, %d API calls for '%s' [monthly: %d/%d]",
        len(results), api_calls, query, get_monthly_usage(), limit,
    )
    return results, api_calls
