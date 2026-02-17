"""Outscraper API integration — optional enrichment layer.

Enriches existing leads with email addresses and social media links.
Free tier: 500 records/month. Only called if OUTSCRAPER_API_KEY is configured.

API docs: https://app.outscraper.com/api-docs
"""

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OUTSCRAPER_API_URL = "https://api.app.outscraper.com/maps/search-v3"

# Simple in-memory monthly usage counter
_usage: dict[str, int] = {"month": 0, "count": 0}


def _get_current_month() -> int:
    """Return current month as YYYYMM integer."""
    t = time.gmtime()
    return t.tm_year * 100 + t.tm_mon


def get_monthly_usage() -> int:
    """Return the number of Outscraper records enriched this month."""
    current = _get_current_month()
    if _usage["month"] != current:
        _usage["month"] = current
        _usage["count"] = 0
    return _usage["count"]


def _increment_usage(count: int = 1) -> int:
    """Increment and return the monthly usage counter."""
    current = _get_current_month()
    if _usage["month"] != current:
        _usage["month"] = current
        _usage["count"] = 0
    _usage["count"] += count
    return _usage["count"]


async def enrich_leads(leads: list[dict]) -> list[dict]:
    """Enrich existing leads with email and social media data from Outscraper.

    Only runs if OUTSCRAPER_API_KEY is set and monthly limit is not exceeded.
    Queries Outscraper with business names + addresses to find matching records,
    then merges email, facebook, instagram, twitter, linkedin, youtube fields.

    Args:
        leads: List of lead dicts to enrich.

    Returns:
        The same list with additional fields merged in.
    """
    if not settings.outscraper_api_key:
        logger.info("Outscraper API key not configured — skipping enrichment")
        return leads

    current_usage = get_monthly_usage()
    limit = settings.outscraper_monthly_limit
    remaining = max(0, limit - current_usage)

    if remaining == 0:
        logger.warning(
            "Outscraper monthly limit reached (%d/%d) — skipping enrichment",
            current_usage, limit,
        )
        return leads

    if current_usage >= limit - 50:
        logger.warning(
            "Outscraper approaching monthly limit: %d/%d records used",
            current_usage, limit,
        )

    # Only enrich leads that are missing email/social data
    to_enrich = [
        lead for lead in leads
        if not lead.get("email") and (lead.get("name") and lead.get("address"))
    ]

    # Respect monthly limit
    to_enrich = to_enrich[:remaining]

    if not to_enrich:
        logger.info("No leads need enrichment (all have data or missing name/address)")
        return leads

    logger.info("Enriching %d leads via Outscraper (usage: %d/%d)", len(to_enrich), current_usage, limit)

    # Build name→lead index for matching results back
    lead_index: dict[str, dict] = {}
    for lead in to_enrich:
        key = f"{lead['name']}|||{lead.get('address', '')}"
        lead_index[key] = lead

    # Query Outscraper in batches of 20
    batch_size = 20
    headers = {"X-API-KEY": settings.outscraper_api_key}

    async with httpx.AsyncClient(timeout=60) as client:
        for batch_start in range(0, len(to_enrich), batch_size):
            batch = to_enrich[batch_start:batch_start + batch_size]
            queries = [
                f"{lead['name']}, {lead.get('address', '')}"
                for lead in batch
            ]

            try:
                response = await client.get(
                    OUTSCRAPER_API_URL,
                    params={
                        "query": queries,
                        "limit": 1,
                        "async": "false",
                    },
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "Outscraper API error: %d %s",
                    e.response.status_code,
                    e.response.text[:500],
                )
                break
            except httpx.ReadTimeout:
                logger.error("Outscraper API timeout for batch starting at %d", batch_start)
                continue

            # Parse results — API returns list of lists
            results = data.get("data", [])
            enriched_count = 0

            for i, result_group in enumerate(results):
                if not result_group or i >= len(batch):
                    continue

                result = result_group[0] if isinstance(result_group, list) and result_group else None
                if not result:
                    continue

                lead = batch[i]

                # Merge enrichment fields
                if result.get("email"):
                    lead["email"] = result["email"]
                    enriched_count += 1
                if result.get("facebook"):
                    lead["facebook"] = result["facebook"]
                if result.get("instagram"):
                    lead["instagram"] = result["instagram"]
                if result.get("twitter"):
                    lead["twitter"] = result["twitter"]
                if result.get("linkedin"):
                    lead["linkedin"] = result["linkedin"]
                if result.get("youtube"):
                    lead["youtube"] = result["youtube"]

                # Fill in phone/website if we didn't have them
                if not lead.get("phone") and result.get("phone"):
                    lead["phone"] = result["phone"]
                if not lead.get("website") and result.get("site"):
                    lead["website"] = result["site"]

            _increment_usage(len(batch))

            logger.debug(
                "Outscraper batch %d–%d: %d enriched [monthly: %d/%d]",
                batch_start, batch_start + len(batch), enriched_count,
                get_monthly_usage(), limit,
            )

            # Rate limit between batches
            await asyncio.sleep(1.0)

    logger.info(
        "Outscraper enrichment complete: %d leads processed [monthly: %d/%d]",
        len(to_enrich), get_monthly_usage(), limit,
    )
    return leads
