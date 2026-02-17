"""Playwright-based Google Maps scraper — PRIMARY data source (free, self-hosted).

Launches headless Chromium, navigates to Google Maps search results,
scrolls to load listings, and extracts business data from the results panel
and optionally from individual listing detail pages.
"""

import asyncio
import hashlib
import logging
import re
import urllib.parse

from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.config import settings

logger = logging.getLogger(__name__)

# Delay between visiting detail pages to avoid rate limiting
DETAIL_PAGE_DELAY = 2.0

# Max time to wait for selectors (ms)
SELECTOR_TIMEOUT = 8000


def _build_search_url(keyword: str, location: str, lat: float, lng: float, zoom: int = 14) -> str:
    """Build a Google Maps search URL."""
    query = urllib.parse.quote(f"{keyword} in {location}")
    return f"https://www.google.com/maps/search/{query}/@{lat},{lng},{zoom}z"


def _parse_rating_text(text: str) -> tuple[float | None, int | None]:
    """Parse a rating string like '4.5(123)' or '4.5 stars 123 reviews'."""
    rating = None
    count = None

    rating_match = re.search(r"(\d+\.?\d*)", text)
    if rating_match:
        try:
            rating = float(rating_match.group(1))
            if rating > 5:
                rating = None
        except ValueError:
            pass

    count_match = re.search(r"\((\d[\d,]*)\)", text)
    if count_match:
        try:
            count = int(count_match.group(1).replace(",", ""))
        except ValueError:
            pass

    return rating, count


async def _scroll_results_panel(page: Page, max_scrolls: int = 5) -> None:
    """Scroll the results feed to load more listings.

    Scrolls the results panel div[role='feed'] and waits for new items.
    """
    feed = page.locator('div[role="feed"]')

    try:
        await feed.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning("Results feed not found — page may not have loaded")
        return

    for scroll_num in range(max_scrolls):
        # Count current items
        items_before = await page.locator('div[role="feed"] > div > div[jsaction]').count()

        # Scroll to bottom of feed
        await feed.evaluate("el => el.scrollTop = el.scrollHeight")
        await asyncio.sleep(1.5)

        items_after = await page.locator('div[role="feed"] > div > div[jsaction]').count()

        logger.debug("Scroll %d: %d → %d items", scroll_num + 1, items_before, items_after)

        # Check for "end of results" indicator
        end_marker = page.locator('p.fontBodyMedium span:has-text("end of results")')
        if await end_marker.count() > 0:
            logger.debug("Reached end of results")
            break

        if items_after == items_before:
            # No new items loaded — might be at the end
            await asyncio.sleep(1.0)
            items_final = await page.locator('div[role="feed"] > div > div[jsaction]').count()
            if items_final == items_before:
                break


async def _extract_listings_from_feed(page: Page) -> list[dict]:
    """Extract listing data from the results feed panel."""
    listings: list[dict] = []

    # Each listing is an anchor tag within the feed
    links = page.locator('div[role="feed"] a[href*="/maps/place/"]')
    count = await links.count()

    logger.info("Found %d listing links in feed", count)

    for i in range(count):
        try:
            link = links.nth(i)
            href = await link.get_attribute("href") or ""
            aria_label = await link.get_attribute("aria-label") or ""

            if not aria_label:
                continue

            # The parent container has additional info
            container = link.locator("xpath=ancestor::div[contains(@jsaction, 'mouseover')]").first

            # Extract category/type
            category = ""
            category_els = container.locator('div.fontBodyMedium > div > span > span')
            if await category_els.count() > 0:
                category = (await category_els.first.inner_text()).strip()
                # Clean up common patterns like "· Restaurant" or "Restaurant · $$"
                category = re.sub(r"^[·\s]+|[·\s]+$", "", category)

            # Extract rating and review count from the aria-label or nearby elements
            rating = None
            review_count = None
            rating_el = container.locator('span[role="img"]')
            if await rating_el.count() > 0:
                rating_label = await rating_el.first.get_attribute("aria-label") or ""
                rating, review_count = _parse_rating_text(rating_label)

            # Extract address — usually the last line of text in the container
            address = ""
            address_candidates = container.locator('div.fontBodyMedium > div:not(:first-child)')
            addr_count = await address_candidates.count()
            if addr_count > 0:
                last_text = (await address_candidates.last.inner_text()).strip()
                # Address lines typically start with a number or contain comma-separated parts
                if last_text and not last_text.startswith("Open") and not last_text.startswith("Closed"):
                    address = last_text

            listing = {
                "place_id": "",
                "name": aria_label,
                "address": address or None,
                "phone": None,
                "website": None,
                "rating": rating,
                "review_count": review_count,
                "types": [category] if category else [],
                "business_type": category or None,
                "latitude": None,
                "longitude": None,
                "opening_hours": None,
                "photos": [],
                "price_level": None,
                "business_status": None,
                "maps_url": href,
                "source": "playwright",
                "raw_data": {"aria_label": aria_label, "href": href},
            }

            # Try to extract place_id from the URL
            # Google Maps URLs embed place IDs as hex CIDs (0x...) or
            # ChIJ... tokens in the data parameter or path segments
            place_id_match = re.search(r"(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", href)
            if not place_id_match:
                place_id_match = re.search(r"(ChIJ[A-Za-z0-9_-]+)", href)
            if place_id_match:
                listing["place_id"] = place_id_match.group(1)

            # Try to extract lat/lng from the URL
            coord_match = re.search(r"@(-?\d+\.?\d*),(-?\d+\.?\d*)", href)
            if coord_match:
                listing["latitude"] = float(coord_match.group(1))
                listing["longitude"] = float(coord_match.group(2))

            listings.append(listing)

        except Exception as e:
            logger.debug("Failed to extract listing %d: %s", i, e)
            continue

    return listings


async def _scrape_detail_page(page: Page, listing: dict) -> dict:
    """Visit a listing's detail page and scrape additional data.

    Enriches the listing dict with: phone, website, full address, hours, price_level.
    """
    url = listing.get("maps_url", "")
    if not url:
        return listing

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(DETAIL_PAGE_DELAY)

        # Wait for the detail panel to appear
        await page.wait_for_selector('div[role="main"]', timeout=SELECTOR_TIMEOUT)

        # Phone number
        phone_el = page.locator('button[data-item-id="phone:tel"] div.fontBodyMedium')
        if await phone_el.count() > 0:
            listing["phone"] = (await phone_el.first.inner_text()).strip()

        # Website
        website_el = page.locator('a[data-item-id="authority"] div.fontBodyMedium')
        if await website_el.count() > 0:
            website_text = (await website_el.first.inner_text()).strip()
            if website_text and not website_text.startswith("http"):
                website_text = f"https://{website_text}"
            listing["website"] = website_text

        # Full address
        address_el = page.locator('button[data-item-id="address"] div.fontBodyMedium')
        if await address_el.count() > 0:
            listing["address"] = (await address_el.first.inner_text()).strip()

        # Opening hours
        hours_el = page.locator('div[aria-label*="Monday"], div[aria-label*="Sunday"], div[aria-label*="hour"]')
        if await hours_el.count() > 0:
            hours_text = await hours_el.first.get_attribute("aria-label") or ""
            if hours_text:
                listing["opening_hours"] = {"text": hours_text}

        # Price level (from category area: "$" to "$$$$")
        category_el = page.locator('button[jsaction*="category"]')
        if await category_el.count() > 0:
            cat_text = (await category_el.first.inner_text()).strip()
            dollar_match = re.search(r"(\$+)", cat_text)
            if dollar_match:
                listing["price_level"] = len(dollar_match.group(1))

        # Place ID from the current URL
        current_url = page.url
        place_id_match = re.search(r"(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", current_url)
        if not place_id_match:
            place_id_match = re.search(r"(ChIJ[A-Za-z0-9_-]+)", current_url)
        if place_id_match and not listing.get("place_id"):
            listing["place_id"] = place_id_match.group(1)

        # Coordinates from current URL
        coord_match = re.search(r"@(-?\d+\.?\d*),(-?\d+\.?\d*)", current_url)
        if coord_match:
            listing["latitude"] = float(coord_match.group(1))
            listing["longitude"] = float(coord_match.group(2))

        logger.debug("Scraped detail: %s (phone=%s, website=%s)", listing["name"], listing["phone"], listing["website"])

    except PlaywrightTimeout:
        logger.debug("Timeout loading detail page for '%s'", listing.get("name", "?"))
    except Exception as e:
        logger.debug("Error scraping detail page for '%s': %s", listing.get("name", "?"), e)

    return listing


async def scrape_google_maps(
    keyword: str,
    location: str,
    latitude: float,
    longitude: float,
    max_results: int = 60,
    scrape_details: bool | None = None,
    zoom: int = 14,
) -> tuple[list[dict], int]:
    """Scrape Google Maps search results using Playwright.

    This is the PRIMARY data source — free, self-hosted, no API key needed.

    Args:
        keyword: Business type or search term (e.g., "restaurants").
        location: Location description (e.g., "Austin, TX").
        latitude: Center latitude for the search.
        longitude: Center longitude for the search.
        max_results: Maximum number of listings to extract.
        scrape_details: Whether to visit each listing's detail page for
            phone/website/hours. Defaults to settings.playwright_scrape_details.
        zoom: Google Maps zoom level.

    Returns:
        Tuple of (list of parsed listing dicts, number of pages scraped).
    """
    if scrape_details is None:
        scrape_details = settings.playwright_scrape_details

    search_url = _build_search_url(keyword, location, latitude, longitude, zoom)
    pages_scraped = 0
    listings: list[dict] = []

    logger.info("Playwright scraping: '%s' in '%s' at (%.4f, %.4f)", keyword, location, latitude, longitude)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            # Navigate to Google Maps search
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            pages_scraped += 1

            # Handle consent dialog if it appears
            try:
                consent_btn = page.locator('button:has-text("Accept all")')
                if await consent_btn.count() > 0:
                    await consent_btn.first.click()
                    await asyncio.sleep(1.0)
            except Exception:
                pass

            # Wait for results to load
            try:
                await page.wait_for_selector('div[role="feed"]', timeout=15000)
            except PlaywrightTimeout:
                logger.warning("No results feed found for '%s' in '%s'", keyword, location)
                await browser.close()
                return [], pages_scraped

            # Scroll to load more results
            max_scrolls = max(1, max_results // 15)  # ~15 results per scroll
            await _scroll_results_panel(page, max_scrolls=min(max_scrolls, 8))

            # Extract listings from the feed
            listings = await _extract_listings_from_feed(page)

            # Trim to max_results
            listings = listings[:max_results]

            logger.info("Extracted %d listings from feed", len(listings))

            # Optionally scrape detail pages for each listing
            if scrape_details and listings:
                logger.info("Scraping detail pages for %d listings...", len(listings))
                for i, listing in enumerate(listings):
                    listing = await _scrape_detail_page(page, listing)
                    listings[i] = listing

                    if (i + 1) % 10 == 0:
                        logger.info("Detail scrape progress: %d/%d", i + 1, len(listings))

        except Exception as e:
            logger.error("Playwright scraping failed: %s", e)
        finally:
            await browser.close()

    # Ensure all listings have a place_id (generate one if missing)
    for listing in listings:
        if not listing.get("place_id"):
            # Create a deterministic ID from name + address + maps_url
            # Using hashlib (not hash()) so the result is stable across runs
            identity = f"{listing.get('name', '')}|{listing.get('address', '')}|{listing.get('maps_url', '')}"
            digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
            listing["place_id"] = f"pw_{digest}"

    logger.info(
        "Playwright scrape complete: %d listings, details=%s",
        len(listings), scrape_details,
    )
    return listings, pages_scraped
