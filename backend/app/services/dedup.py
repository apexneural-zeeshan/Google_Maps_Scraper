"""Deduplication service for merging results from multiple data sources.

Primary dedup key: place_id matching.
Fallback: fuzzy name matching + geographic proximity.
"""

import logging

from thefuzz import fuzz

from app.services.grid import haversine

logger = logging.getLogger(__name__)

# Fuzzy match threshold (0–100). 85+ is a strong match.
FUZZY_NAME_THRESHOLD = 85

# Maximum distance in km between two places to consider them the same
PROXIMITY_THRESHOLD_KM = 0.05  # 50 meters


def _merge_fields(existing: dict, new: dict) -> dict:
    """Merge missing fields from `new` into `existing`.

    Keeps existing non-None values and fills in gaps from the new record.
    For list fields (types, photos), merges unique items.

    Returns:
        Updated existing dict with merged fields.
    """
    for key, value in new.items():
        if key in ("place_id", "source", "raw_data"):
            continue

        existing_value = existing.get(key)

        if existing_value is None and value is not None:
            existing[key] = value
        elif isinstance(existing_value, list) and isinstance(value, list):
            # Merge unique items for list fields
            seen = set()
            merged = []
            for item in existing_value + value:
                item_key = str(item)
                if item_key not in seen:
                    seen.add(item_key)
                    merged.append(item)
            existing[key] = merged

    # Track that this record was enriched by multiple sources
    sources = set()
    if existing.get("source"):
        sources.add(existing["source"])
    if new.get("source"):
        sources.add(new["source"])
    if len(sources) > 1:
        existing["source"] = "+".join(sorted(sources))

    return existing


def _fuzzy_match(lead_a: dict, lead_b: dict) -> bool:
    """Check if two leads likely refer to the same business using fuzzy name + proximity.

    Returns:
        True if the leads are likely the same business.
    """
    name_a = (lead_a.get("name") or "").strip().lower()
    name_b = (lead_b.get("name") or "").strip().lower()

    if not name_a or not name_b:
        return False

    # Check name similarity
    name_score = fuzz.ratio(name_a, name_b)
    if name_score < FUZZY_NAME_THRESHOLD:
        return False

    # Check geographic proximity — REQUIRE coordinates on both sides
    lat_a, lng_a = lead_a.get("latitude"), lead_a.get("longitude")
    lat_b, lng_b = lead_b.get("latitude"), lead_b.get("longitude")

    if not all(v is not None for v in [lat_a, lng_a, lat_b, lng_b]):
        # Without coordinates on both leads we can't confirm proximity,
        # so only match if names are nearly identical (score >= 95)
        return name_score >= 95

    distance = haversine(lat_a, lng_a, lat_b, lng_b)
    if distance > PROXIMITY_THRESHOLD_KM:
        return False

    return True


def deduplicate(leads: list[dict]) -> list[dict]:
    """Deduplicate a list of lead dicts from multiple sources.

    Strategy:
    1. Group by place_id (exact match) — merge fields.
    2. For remaining leads without a match, fuzzy-match on name + proximity.

    Args:
        leads: List of lead dicts (from places_api, serp_api, etc.).

    Returns:
        Deduplicated list of lead dicts with merged fields.
    """
    if not leads:
        return []

    # Phase 1: Group by place_id
    by_place_id: dict[str, dict] = {}
    no_place_id: list[dict] = []

    for lead in leads:
        pid = lead.get("place_id", "").strip()
        if pid:
            if pid in by_place_id:
                logger.debug(
                    "Dedup place_id match: '%s' merged with '%s' (place_id=%s)",
                    lead.get("name"), by_place_id[pid].get("name"), pid,
                )
                by_place_id[pid] = _merge_fields(by_place_id[pid], lead)
            else:
                by_place_id[pid] = lead.copy()
        else:
            no_place_id.append(lead)

    logger.info(
        "Dedup phase 1 (place_id): %d with place_id (%d unique), %d without",
        len(leads) - len(no_place_id), len(by_place_id), len(no_place_id),
    )

    # Phase 2: Fuzzy match leads without place_id against known leads
    merged_leads = list(by_place_id.values())
    fuzzy_merged = 0

    for orphan in no_place_id:
        matched = False
        for existing in merged_leads:
            if _fuzzy_match(existing, orphan):
                logger.debug(
                    "Dedup fuzzy match: '%s' (%s) merged with '%s' (%s)",
                    orphan.get("name"), orphan.get("address"),
                    existing.get("name"), existing.get("address"),
                )
                _merge_fields(existing, orphan)
                matched = True
                fuzzy_merged += 1
                break

        if not matched:
            merged_leads.append(orphan)

    original_count = len(leads)
    deduped_count = len(merged_leads)
    removed = original_count - deduped_count

    logger.info(
        "Dedup phase 2 (fuzzy): %d orphans checked, %d merged, %d kept as unique",
        len(no_place_id), fuzzy_merged, len(no_place_id) - fuzzy_merged,
    )
    logger.info(
        "Dedup result: %d leads → %d unique (%d duplicates removed)",
        original_count, deduped_count, removed,
    )

    return merged_leads
