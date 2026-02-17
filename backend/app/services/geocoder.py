"""Geocoding service using Nominatim (OpenStreetMap) — free, no API key required.

Nominatim usage policy: max 1 request/second, must set a descriptive User-Agent.
https://operations.osmfoundation.org/policies/nominatim/
"""

import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

HEADERS = {"User-Agent": settings.nominatim_user_agent}


async def geocode_location(address: str) -> tuple[float, float]:
    """Convert an address string to (latitude, longitude) coordinates.

    Uses Nominatim (OpenStreetMap) — free, no API key required.
    Respects Nominatim's 1 request/second rate limit.

    Args:
        address: Human-readable address string (e.g., "Austin, TX").

    Returns:
        Tuple of (latitude, longitude).

    Raises:
        ValueError: If geocoding fails or returns no results.
    """
    await asyncio.sleep(1.0)  # Nominatim rate limit: 1 req/sec

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            NOMINATIM_SEARCH_URL,
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
            },
            headers=HEADERS,
        )
        response.raise_for_status()
        data = response.json()

    if not data:
        raise ValueError(f"Geocoding failed for '{address}': no results found")

    result = data[0]
    lat = float(result["lat"])
    lng = float(result["lon"])

    logger.info(
        "Geocoded '%s' → (%f, %f) [%s]",
        address, lat, lng, result.get("display_name", ""),
    )
    return lat, lng


async def geocode_coordinates(lat: float, lng: float) -> str:
    """Reverse geocode coordinates to a human-readable address.

    Uses Nominatim (OpenStreetMap) — free, no API key required.

    Args:
        lat: Latitude.
        lng: Longitude.

    Returns:
        Formatted address string.

    Raises:
        ValueError: If reverse geocoding fails.
    """
    await asyncio.sleep(1.0)  # Nominatim rate limit: 1 req/sec

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            NOMINATIM_REVERSE_URL,
            params={
                "lat": lat,
                "lon": lng,
                "format": "json",
                "addressdetails": 1,
            },
            headers=HEADERS,
        )
        response.raise_for_status()
        data = response.json()

    if data.get("error"):
        raise ValueError(
            f"Reverse geocoding failed for ({lat}, {lng}): {data['error']}"
        )

    address = data.get("display_name", "")
    if not address:
        raise ValueError(f"Reverse geocoding failed for ({lat}, {lng}): empty result")

    logger.info("Reverse geocoded (%f, %f) → '%s'", lat, lng, address)
    return address
