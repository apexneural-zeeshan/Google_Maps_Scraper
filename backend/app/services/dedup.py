"""Deduplication service for merging results from multiple data sources.

Primary dedup key: place_id matching.
Fallback: fuzzy name matching + geographic proximity.
"""

import logging
import re

from thefuzz import fuzz

from app.services.grid import haversine

logger = logging.getLogger(__name__)

# Fuzzy match threshold (0–100). 85+ is a strong match.
FUZZY_NAME_THRESHOLD = 85

# Maximum distance in km between two places to consider them the same
PROXIMITY_THRESHOLD_KM = 0.05  # 50 meters

# Regex patterns for place_id format detection
_HEX_CID_RE = re.compile(r"^0x[0-9a-fA-F]+:0x[0-9a-fA-F]+$")
_CHIJ_RE = re.compile(r"^ChIJ[A-Za-z0-9_-]+$")
_PW_GENERATED_RE = re.compile(r"^pw_[0-9a-f]+$")


def _is_real_place_id(pid: str) -> bool:
    """Return True if the place_id is a real Google ID (hex CID or ChIJ).

    Generated/fallback IDs (pw_...) are NOT real and should not be used
    for exact-match grouping across sources.
    """
    return bool(_HEX_CID_RE.match(pid) or _CHIJ_RE.match(pid))


# Source priority: higher = more authoritative for contact/enrichment data
_SOURCE_PRIORITY = {
    "outscraper": 3,
    "serp_api": 2,
    "playwright": 1,
}

# Fields where a higher-priority source should overwrite existing data
_PRIORITY_FIELDS = {
    "primary_email", "emails", "social_links", "owner_name",
    "employee_count", "year_established", "business_age_years",
    "description", "verified",
}


def _source_rank(source: str) -> int:
    """Return priority rank for a source string (handles combined sources like 'playwright+serp_api')."""
    parts = source.split("+") if source else []
    return max((_SOURCE_PRIORITY.get(p, 0) for p in parts), default=0)


def _merge_fields(existing: dict, new: dict) -> dict:
    """Merge missing fields from `new` into `existing`.

    Keeps existing non-None values and fills in gaps from the new record.
    For list fields (types, photos), merges unique items.
    For priority fields (contact/enrichment data), a higher-priority source
    can overwrite a lower-priority source's value.

    Returns:
        Updated existing dict with merged fields.
    """
    # Prefer standard ChIJ place_id over hex CID format
    new_pid = new.get("place_id", "")
    existing_pid = existing.get("place_id", "")
    if new_pid.startswith("ChIJ") and not existing_pid.startswith("ChIJ"):
        existing["place_id"] = new_pid

    new_rank = _source_rank(new.get("source", ""))
    existing_rank = _source_rank(existing.get("source", ""))

    for key, value in new.items():
        if key in ("place_id", "source", "raw_data"):
            continue

        existing_value = existing.get(key)

        if existing_value is None and value is not None:
            existing[key] = value
        elif key in _PRIORITY_FIELDS and value is not None and new_rank > existing_rank:
            # Higher-priority source overwrites for enrichment fields
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

    # Phase 1: Group by place_id (exact match within same format only)
    by_place_id: dict[str, dict] = {}
    needs_fuzzy: list[dict] = []

    for lead in leads:
        pid = lead.get("place_id", "").strip()
        if pid and _is_real_place_id(pid):
            if pid in by_place_id:
                logger.debug(
                    "Dedup place_id match: '%s' merged with '%s' (place_id=%s)",
                    lead.get("name"), by_place_id[pid].get("name"), pid,
                )
                by_place_id[pid] = _merge_fields(by_place_id[pid], lead)
            else:
                by_place_id[pid] = lead.copy()
        else:
            # No real place_id, or generated pw_ id — needs fuzzy matching
            needs_fuzzy.append(lead)

    logger.info(
        "Dedup phase 1 (place_id): %d with real place_id (%d unique), %d need fuzzy",
        len(leads) - len(needs_fuzzy), len(by_place_id), len(needs_fuzzy),
    )

    # Phase 2: Fuzzy match across all remaining leads
    # This catches: (a) leads without place_id, (b) leads with pw_ generated IDs,
    # and (c) cross-format matches (hex CID vs ChIJ for the same business)
    merged_leads = list(by_place_id.values())
    fuzzy_merged = 0

    for candidate in needs_fuzzy:
        matched = False
        for existing in merged_leads:
            if _fuzzy_match(existing, candidate):
                logger.debug(
                    "Dedup fuzzy match: '%s' (%s) merged with '%s' (%s)",
                    candidate.get("name"), candidate.get("address"),
                    existing.get("name"), existing.get("address"),
                )
                _merge_fields(existing, candidate)
                matched = True
                fuzzy_merged += 1
                break

        if not matched:
            merged_leads.append(candidate)

    # Phase 3: Cross-format fuzzy pass — check if any place_id-grouped leads
    # are actually the same business (hex CID from Playwright == ChIJ from SerpAPI)
    cross_merged = 0
    final_leads: list[dict] = []

    for lead in merged_leads:
        matched = False
        for existing in final_leads:
            if _fuzzy_match(existing, lead):
                logger.debug(
                    "Dedup cross-format match: '%s' (pid=%s) merged with '%s' (pid=%s)",
                    lead.get("name"), lead.get("place_id", "")[:20],
                    existing.get("name"), existing.get("place_id", "")[:20],
                )
                _merge_fields(existing, lead)
                matched = True
                cross_merged += 1
                break
        if not matched:
            final_leads.append(lead)

    original_count = len(leads)
    deduped_count = len(final_leads)
    removed = original_count - deduped_count

    logger.info(
        "Dedup phase 2 (fuzzy): %d candidates, %d merged",
        len(needs_fuzzy), fuzzy_merged,
    )
    logger.info(
        "Dedup phase 3 (cross-format): %d cross-format merges",
        cross_merged,
    )
    logger.info(
        "Dedup result: %d leads → %d unique (%d duplicates removed)",
        original_count, deduped_count, removed,
    )

    return final_leads
