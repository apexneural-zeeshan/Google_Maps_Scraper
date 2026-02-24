"""Outscraper API integration — optional enrichment layer.

Enriches existing leads with email addresses and social media links.
Free tier: 500 records/month. Only called if OUTSCRAPER_API_KEY is configured.

API docs: https://app.outscraper.com/api-docs
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

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


def _merge_outscraper_result(lead: dict, result: dict) -> bool:
    """Merge Outscraper result fields into an existing lead dict.

    Only fills in fields that are currently None — never overwrites existing data.
    Validates emails contain '@' and URLs start with 'http'.

    Returns True if any enrichment field was added.
    """
    enriched = False

    # Collect validated emails
    all_emails: list[str] = []
    for key in ("email", "email_1", "email_2", "email_3"):
        val = result.get(key)
        if val and isinstance(val, str) and "@" in val and val not in all_emails:
            all_emails.append(val)

    # Primary email
    if all_emails and not lead.get("primary_email"):
        lead["primary_email"] = all_emails[0]
        enriched = True

    # Emails dict
    if all_emails and not lead.get("emails"):
        lead["emails"] = {
            "primary": all_emails[0],
            "secondary": all_emails[1:] if len(all_emails) > 1 else [],
        }
        enriched = True

    # Social links (validate URLs)
    if not lead.get("social_links"):
        social: dict[str, str] = {}
        for platform in (
            "facebook", "instagram", "linkedin", "twitter",
            "youtube", "tiktok", "pinterest",
        ):
            val = result.get(platform)
            if val and isinstance(val, str) and val.startswith("http"):
                social[platform] = val
        if social:
            lead["social_links"] = social
            enriched = True

    # Owner name
    owner = result.get("owner_name") or result.get("owner_title") or result.get("owner")
    if owner and isinstance(owner, str) and not lead.get("owner_name"):
        lead["owner_name"] = owner
        enriched = True

    # Employee count
    employees = (
        result.get("range_employees")
        or result.get("employees")
        or result.get("employee_count")
    )
    if employees and not lead.get("employee_count"):
        lead["employee_count"] = str(employees)
        enriched = True

    # Year established and business age
    year = result.get("founded") or result.get("year_established")
    if year and not lead.get("year_established"):
        try:
            year_int = int(year)
            lead["year_established"] = year_int
            lead["business_age_years"] = datetime.now(timezone.utc).year - year_int
            enriched = True
        except (ValueError, TypeError):
            pass

    # Description (only if we don't already have one from Playwright/SerpAPI)
    desc = result.get("description") or result.get("about")
    if desc and isinstance(desc, str) and not lead.get("description"):
        lead["description"] = desc
        enriched = True

    # Verified
    verified = result.get("verified")
    if verified is not None and lead.get("verified") is None:
        lead["verified"] = bool(verified)
        enriched = True

    # Reviews per score
    rps = result.get("reviews_per_score")
    if rps and isinstance(rps, dict) and not lead.get("reviews_per_score"):
        lead["reviews_per_score"] = rps
        enriched = True

    # Business status
    status = result.get("business_status") or result.get("status")
    if status and isinstance(status, str) and not lead.get("business_status"):
        lead["business_status"] = status

    # Fill in phone/website if we didn't have them
    if not lead.get("phone") and result.get("phone"):
        lead["phone"] = result["phone"]
    if not lead.get("website") and result.get("site"):
        lead["website"] = result["site"]

    return enriched


async def enrich_leads(leads: list[dict]) -> list[dict]:
    """Enrich existing leads with email and social media data from Outscraper.

    Only runs if OUTSCRAPER_API_KEY is set and monthly limit is not exceeded.
    Queries Outscraper with business names + addresses to find matching records,
    then merges email, social, owner, employee, and description fields.

    Handles 402 Payment Required gracefully (free tier requires verified card).

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
        if not lead.get("primary_email") and (lead.get("name") and lead.get("address"))
    ]

    # Respect monthly limit
    to_enrich = to_enrich[:remaining]

    if not to_enrich:
        logger.info("No leads need enrichment (all have data or missing name/address)")
        return leads

    logger.info("Enriching %d leads via Outscraper (usage: %d/%d)", len(to_enrich), current_usage, limit)

    total_enriched = 0

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
                if e.response.status_code == 402:
                    logger.warning(
                        "Outscraper 402 Payment Required — free tier may require "
                        "a verified credit card. Skipping remaining enrichment."
                    )
                    break
                logger.error(
                    "Outscraper API error: %d %s",
                    e.response.status_code,
                    e.response.text[:500],
                )
                break
            except httpx.ReadTimeout:
                logger.error("Outscraper API timeout for batch starting at %d", batch_start)
                continue

            # Log raw response structure for debugging
            logger.info(
                "Outscraper response keys: %s",
                list(data.keys()) if isinstance(data, dict) else type(data).__name__,
            )

            # Parse results — API returns list of lists under "data" key
            # Format: {"data": [[{result1}], [{result2}], ...]}
            # Each inner list corresponds to one query, first element is best match
            results = data.get("data", [])

            # Fallback: if no "data" key, the response itself might be the list
            if not results and isinstance(data, list):
                results = data
                logger.info("Outscraper response has no 'data' key, using raw list (len=%d)", len(results))

            if results:
                first_result = results[0] if results else None
                if first_result and isinstance(first_result, list) and first_result:
                    sample = first_result[0]
                    if isinstance(sample, dict):
                        logger.info(
                            "Outscraper sample keys: %s",
                            list(sample.keys())[:15],
                        )
                        logger.info(
                            "Outscraper sample — email_1=%s, owner=%s, facebook=%s",
                            sample.get("email_1", "N/A"),
                            sample.get("owner_name", "N/A"),
                            sample.get("facebook", "N/A"),
                        )
                    else:
                        logger.warning(
                            "Outscraper first result item is %s, not dict",
                            type(sample).__name__,
                        )
                elif first_result and isinstance(first_result, dict):
                    # Response might be a flat list of dicts (not list of lists)
                    logger.info(
                        "Outscraper returned flat list of dicts, wrapping each in a list",
                    )
                    results = [[r] if isinstance(r, dict) else r for r in results]
                else:
                    logger.warning(
                        "Outscraper returned unexpected result format: first_result=%s",
                        type(first_result).__name__ if first_result else "empty",
                    )

            enriched_count = 0

            for i, result_group in enumerate(results):
                if i >= len(batch):
                    break
                if not result_group:
                    continue

                result = (
                    result_group[0]
                    if isinstance(result_group, list) and result_group
                    else result_group if isinstance(result_group, dict)
                    else None
                )
                if not result or not isinstance(result, dict):
                    continue

                lead = batch[i]
                if _merge_outscraper_result(lead, result):
                    enriched_count += 1
                    logger.debug(
                        "Enriched '%s': email=%s, social=%s",
                        lead.get("name", "?"),
                        lead.get("primary_email", "none"),
                        bool(lead.get("social_links")),
                    )

            total_enriched += enriched_count
            _increment_usage(len(batch))

            logger.info(
                "Outscraper batch %d–%d: %d/%d enriched [monthly: %d/%d]",
                batch_start, batch_start + len(batch),
                enriched_count, len(batch),
                get_monthly_usage(), limit,
            )

            # Rate limit between batches
            await asyncio.sleep(1.0)

    logger.info(
        "Outscraper enrichment complete: %d/%d leads enriched [monthly: %d/%d]",
        total_enriched, len(to_enrich), get_monthly_usage(), limit,
    )
    return leads
