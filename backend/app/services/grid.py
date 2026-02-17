"""Grid generation for systematic area coverage.

Creates a hexagonal-ish grid of search points within a circular area to ensure
full coverage when querying location-based APIs with a limited search radius.
"""

import logging
import math
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# Earth radius in km
EARTH_RADIUS_KM = 6371.0

# Google Places API pricing per request (Nearby Search - Basic)
PLACES_API_COST_PER_REQUEST = 0.032

# SerpAPI pricing per search
SERP_API_COST_PER_SEARCH = 0.01


@dataclass
class GridPoint:
    """A search point in the grid."""

    latitude: float
    longitude: float
    search_radius_m: int  # meters


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth.

    Args:
        lat1, lon1: First point coordinates in degrees.
        lat2, lon2: Second point coordinates in degrees.

    Returns:
        Distance in kilometers.
    """
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return EARTH_RADIUS_KM * c


def generate_grid(
    center_lat: float,
    center_lng: float,
    radius_km: float,
    overlap_factor: float | None = None,
) -> list[GridPoint]:
    """Generate a grid of search points covering a circular area.

    Uses a square grid with configurable overlap to ensure no gaps. Each grid
    point gets a search_radius_m that, combined with overlap, covers the area.

    Args:
        center_lat: Center latitude in degrees.
        center_lng: Center longitude in degrees.
        radius_km: Total search area radius in km.
        overlap_factor: Fraction of overlap between adjacent cells (0.0–0.5).
            Defaults to settings.grid_overlap_factor.

    Returns:
        List of GridPoint objects covering the area.
    """
    if overlap_factor is None:
        overlap_factor = settings.grid_overlap_factor

    overlap_factor = max(0.0, min(0.5, overlap_factor))

    # Each cell's search radius: for small areas use the full radius,
    # for larger areas cap at 5km (Places API practical max for nearby search)
    max_cell_radius_km = min(radius_km, 5.0)

    # Step distance between grid points, accounting for overlap
    step_km = max_cell_radius_km * 2 * (1 - overlap_factor)

    if step_km <= 0:
        step_km = max_cell_radius_km

    # If the total radius fits in a single cell, return just the center
    if radius_km <= max_cell_radius_km:
        logger.info(
            "Single-cell grid at (%.4f, %.4f) r=%.1fkm",
            center_lat, center_lng, radius_km,
        )
        return [GridPoint(center_lat, center_lng, int(radius_km * 1000))]

    # Number of steps in each direction from center
    n_steps = math.ceil(radius_km / step_km)

    points: list[GridPoint] = []

    for row in range(-n_steps, n_steps + 1):
        for col in range(-n_steps, n_steps + 1):
            # Offset latitude
            dlat = (row * step_km) / EARTH_RADIUS_KM
            lat = center_lat + math.degrees(dlat)

            # Offset longitude (adjusted for latitude)
            dlng = (col * step_km) / (EARTH_RADIUS_KM * math.cos(math.radians(center_lat)))
            lng = center_lng + math.degrees(dlng)

            # Only include points within the total radius
            dist = haversine(center_lat, center_lng, lat, lng)
            if dist <= radius_km + max_cell_radius_km * 0.5:
                points.append(GridPoint(lat, lng, int(max_cell_radius_km * 1000)))

    logger.info(
        "Generated grid: %d points covering %.1fkm radius from (%.4f, %.4f), step=%.2fkm",
        len(points), radius_km, center_lat, center_lng, step_km,
    )
    return points


def estimate_api_calls(grid_points: list[GridPoint]) -> dict[str, int]:
    """Estimate the number of API calls for a grid.

    Assumes 1 Places API Nearby Search call per grid point (may paginate to 3),
    and 1 SerpAPI call per grid point.

    Returns:
        Dict with 'places_api' and 'serp_api' estimated call counts.
    """
    n = len(grid_points)
    return {
        "places_api": n * 2,  # Nearby + Text search per point, may paginate
        "serp_api": n,
    }


def estimate_cost_usd(grid_points: list[GridPoint]) -> float:
    """Estimate the total API cost in USD for a grid search.

    Returns:
        Estimated cost in USD.
    """
    calls = estimate_api_calls(grid_points)
    cost = (
        calls["places_api"] * PLACES_API_COST_PER_REQUEST
        + calls["serp_api"] * SERP_API_COST_PER_SEARCH
    )
    return round(cost, 4)
