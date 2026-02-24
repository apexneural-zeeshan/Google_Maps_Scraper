"""Playwright-based Google Maps scraper — PRIMARY data source (free, self-hosted).

Launches headless Chromium, navigates to Google Maps search results,
scrolls to load listings, and extracts business data from the results panel
and optionally from individual listing detail pages.

Features:
- Auto-retry per grid cell (3 attempts with exponential backoff)
- Browser lifecycle management (restart after 50 detail pages)
- Random delays between detail page visits (anti-detection)
- Realistic user agent and viewport
"""

import asyncio
import hashlib
import logging
import random
import re
import urllib.parse

from playwright.async_api import Page, Browser, BrowserContext, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.config import settings

logger = logging.getLogger(__name__)

# Delay between visiting detail pages (randomized for anti-detection)
DETAIL_PAGE_DELAY_MIN = 3.0
DETAIL_PAGE_DELAY_MAX = 8.0

# Max time to wait for selectors (ms)
SELECTOR_TIMEOUT = 8000

# Chromium launch args to reduce memory usage (~2.8 GB Docker host)
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-extensions",
    "--disable-plugins",
    "--single-process",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--no-first-run",
    "--disable-features=site-per-process",
    "--js-flags=--max-old-space-size=256",
]

# JavaScript injected into every page to hide automation signals
_STEALTH_SCRIPT = """\
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = {runtime: {}};
"""

# Retry config per grid cell
MAX_CELL_RETRIES = 3
RETRY_BACKOFF_BASE = 5  # seconds: 5, 15, 45

# Realistic user agents (rotated)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _build_search_url(keyword: str, location: str, lat: float, lng: float, zoom: int = 14) -> str:
    """Build a Google Maps search URL.

    Appends ``hl=en`` to force English UI regardless of server location.
    """
    query = urllib.parse.quote(f"{keyword} in {location}")
    return f"https://www.google.com/maps/search/{query}/@{lat},{lng},{zoom}z?hl=en"


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


async def _create_browser_context(
    p,
) -> tuple[Browser, BrowserContext]:
    """Create a fresh browser and context with randomized fingerprint.

    Pre-sets Google consent cookies so the EU consent dialog at
    consent.google.com is never shown (critical for servers located in
    Europe, e.g. Contabo Germany).
    """
    browser = await p.chromium.launch(
        headless=settings.playwright_headless,
        args=CHROMIUM_ARGS,
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        user_agent=random.choice(USER_AGENTS),
    )

    # Pre-set consent cookies to bypass EU consent dialog
    await context.add_cookies([
        {
            "name": "CONSENT",
            "value": "YES+cb.20210720-07-p0.en+FX+410",
            "domain": ".google.com",
            "path": "/",
        },
        {
            "name": "SOCS",
            "value": "CAISHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg",
            "domain": ".google.com",
            "path": "/",
        },
    ])

    # Inject stealth script to hide automation signals
    await context.add_init_script(_STEALTH_SCRIPT)

    return browser, context


async def _scroll_results_panel(page: Page, max_scrolls: int = 5) -> None:
    """Scroll the results feed to load more listings."""
    feed = page.locator('div[role="feed"]')

    try:
        await feed.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning("Results feed not found — page may not have loaded")
        return

    for scroll_num in range(max_scrolls):
        items_before = await page.locator('div[role="feed"] > div > div[jsaction]').count()

        await feed.evaluate("el => el.scrollTop = el.scrollHeight")
        await asyncio.sleep(1.5)

        items_after = await page.locator('div[role="feed"] > div > div[jsaction]').count()

        logger.debug("Scroll %d: %d → %d items", scroll_num + 1, items_before, items_after)

        end_marker = page.locator('p.fontBodyMedium span:has-text("end of results")')
        if await end_marker.count() > 0:
            logger.debug("Reached end of results")
            break

        if items_after == items_before:
            await asyncio.sleep(1.0)
            items_final = await page.locator('div[role="feed"] > div > div[jsaction]').count()
            if items_final == items_before:
                break


async def _handle_consent_dialog(page: Page) -> None:
    """Dismiss Google's EU consent dialog if it appears.

    Tries multiple strategies in order:
    1. Click a known consent button (English + German variants)
    2. Try the same inside iframes
    3. Submit the consent form directly via JS
    4. Re-inject consent cookies and re-navigate
    """
    if "consent.google.com" not in page.url:
        # Also check for in-page consent overlays on maps
        consent_texts = ("Accept all", "I agree", "Agree", "Accept")
        for text in consent_texts:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if await btn.count() > 0:
                    await btn.first.click(timeout=2000)
                    await asyncio.sleep(1.0)
                    return
            except Exception:
                pass
        return

    logger.info("Google consent page detected at %s — attempting to dismiss", page.url)

    # Save original Maps URL from the redirect query string
    original_url = page.url
    continue_match = re.search(r"continue=([^&]+)", original_url)
    original_maps_url = (
        urllib.parse.unquote(continue_match.group(1)) if continue_match else None
    )

    # Strategy 1: Click consent buttons (English + German + CSS selectors)
    consent_selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Reject all")',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Alle ablehnen")',
        '[aria-label="Accept all"]',
        '[aria-label="Reject all"]',
        '#L2AGLb',
        '.VfPpkd-LgbsSe',
        'form[action*="consent"] button',
    ]

    for selector in consent_selectors:
        try:
            btn = page.locator(selector)
            if await btn.count() > 0:
                await btn.first.click(timeout=3000)
                logger.info("Clicked consent button: %s", selector)
                await asyncio.sleep(3.0)
                if "consent.google.com" not in page.url:
                    return
        except Exception:
            continue

    # Strategy 2: Try inside iframes
    for frame in page.frames:
        for selector in consent_selectors:
            try:
                btn = frame.locator(selector)
                if await btn.count() > 0:
                    await btn.first.click(timeout=3000)
                    logger.info("Clicked consent button in iframe: %s", selector)
                    await asyncio.sleep(3.0)
                    if "consent.google.com" not in page.url:
                        return
            except Exception:
                continue

    # Strategy 3: Submit the consent form via JavaScript
    if "consent.google.com" in page.url:
        logger.info("Trying form submit to bypass consent page")
        try:
            await page.evaluate("""
                const forms = document.querySelectorAll('form');
                for (const form of forms) {
                    if (form.action && form.action.includes('consent')) {
                        form.submit();
                        break;
                    }
                }
            """)
            await asyncio.sleep(3.0)
        except Exception:
            pass

    # Strategy 4: Re-inject cookies and navigate directly
    if "consent.google.com" in page.url and original_maps_url:
        logger.warning("Could not dismiss consent dialog, re-injecting cookies and retrying")
        await page.context.add_cookies([
            {
                "name": "CONSENT",
                "value": "YES+cb.20210720-07-p0.en+FX+410",
                "domain": ".google.com",
                "path": "/",
            },
            {
                "name": "SOCS",
                "value": "CAISHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg",
                "domain": ".google.com",
                "path": "/",
            },
        ])
        await page.goto(original_maps_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3.0)


async def _extract_listings_from_feed(page: Page) -> list[dict]:
    """Extract listing data from the results feed panel."""
    listings: list[dict] = []

    links = page.locator(
        'div[role="feed"] a[href*="/maps/place/"], '
        'div[role="feed"] a[href*="google.com/maps/place"], '
        'div[role="feed"] a[href*="/maps?cid="]'
    )
    count = await links.count()
    if count == 0:
        links = page.locator(
            'div[role="feed"] a.hfpxzc, div[role="feed"] a[href*="/maps/"]'
        )
        count = await links.count()

    logger.info("Found %d candidate listing links in feed", count)

    for i in range(count):
        try:
            link = links.nth(i)
            href = await link.get_attribute("href") or ""
            aria_label = await link.get_attribute("aria-label") or ""
            if not href:
                continue

            name = aria_label.strip()
            if not name:
                card = link.locator(
                    'xpath=ancestor::div[contains(@class, "Nv2PK")]'
                ).first
                title_el = card.locator("div.qBF1Pd").first
                if await title_el.count() > 0:
                    name = (await title_el.inner_text()).strip()
            if not name:
                name = (await link.inner_text()).strip()
            if not name:
                continue

            container = link.locator("xpath=ancestor::div[contains(@jsaction, 'mouseover')]").first
            if await container.count() == 0:
                container = link.locator(
                    'xpath=ancestor::div[contains(@class, "Nv2PK")]'
                ).first

            category = ""
            category_els = container.locator('div.fontBodyMedium > div > span > span')
            if await category_els.count() > 0:
                category = (await category_els.first.inner_text()).strip()
                category = re.sub(r"^[·\s]+|[·\s]+$", "", category)

            rating = None
            review_count = None
            if not category:
                chips = container.locator("div.W4Efsd span")
                if await chips.count() > 0:
                    category = (await chips.first.inner_text()).strip()
            rating_el = container.locator('span[role="img"]')
            if await rating_el.count() > 0:
                rating_label = await rating_el.first.get_attribute("aria-label") or ""
                rating, review_count = _parse_rating_text(rating_label)

            address = ""
            address_candidates = container.locator('div.fontBodyMedium > div:not(:first-child)')
            addr_count = await address_candidates.count()
            if addr_count > 0:
                last_text = (await address_candidates.last.inner_text()).strip()
                if last_text and not last_text.startswith("Open") and not last_text.startswith("Closed"):
                    address = last_text

            listing = {
                "place_id": "",
                "name": name,
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
                "description": None,
                "verified": None,
                "reviews_per_score": None,
                "primary_email": None,
                "emails": None,
                "social_links": None,
                "owner_name": None,
                "employee_count": None,
                "year_established": None,
                "business_age_years": None,
                "source": "playwright",
                "raw_data": {"aria_label": aria_label, "href": href},
            }

            place_id_match = re.search(r"(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", href)
            if not place_id_match:
                place_id_match = re.search(r"(ChIJ[A-Za-z0-9_-]+)", href)
            if place_id_match:
                listing["place_id"] = place_id_match.group(1)

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
    """Visit a listing's detail page and scrape additional data."""
    url = listing.get("maps_url", "")
    if not url:
        return listing

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)

        # Randomized delay for anti-detection
        delay = random.uniform(DETAIL_PAGE_DELAY_MIN, DETAIL_PAGE_DELAY_MAX)
        await asyncio.sleep(delay)

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

        # Price level
        category_el = page.locator('button[jsaction*="category"]')
        if await category_el.count() > 0:
            cat_text = (await category_el.first.inner_text()).strip()
            dollar_match = re.search(r"(\$+)", cat_text)
            if dollar_match:
                listing["price_level"] = len(dollar_match.group(1))

        # Place ID from current URL
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

        # Description
        about_el = page.locator('div.PYvSYb, div[class*="editorial"] span')
        if await about_el.count() > 0:
            desc_text = (await about_el.first.inner_text()).strip()
            if desc_text and len(desc_text) > 10:
                listing["description"] = desc_text

        # Verified badge
        verified_el = page.locator('span:has-text("Claimed"), span:has-text("Verified")')
        if await verified_el.count() > 0:
            listing["verified"] = True

        # Reviews per score
        reviews_per_score: dict[str, int] = {}
        for star in range(1, 6):
            star_el = page.locator(f'tr[aria-label*="{star} star"]')
            if await star_el.count() > 0:
                label = await star_el.first.get_attribute("aria-label") or ""
                count_match = re.search(r"(\d[\d,]*)\s*review", label)
                if count_match:
                    reviews_per_score[str(star)] = int(count_match.group(1).replace(",", ""))
        if reviews_per_score:
            listing["reviews_per_score"] = reviews_per_score

        # Owner
        owner_el = page.locator('span:has-text("Managed by"), span:has-text("Owner")')
        if await owner_el.count() > 0:
            owner_text = (await owner_el.first.inner_text()).strip()
            owner_text = re.sub(r"^(Managed by|Owner:?)\s*", "", owner_text).strip()
            if owner_text:
                listing["owner_name"] = owner_text

        logger.debug("Scraped detail: %s (phone=%s, website=%s)", listing["name"], listing["phone"], listing["website"])

    except PlaywrightTimeout:
        logger.debug("Timeout loading detail page for '%s'", listing.get("name", "?"))
    except Exception as e:
        logger.debug("Error scraping detail page for '%s': %s", listing.get("name", "?"), e)

    return listing


async def _scrape_single_cell(
    p,
    keyword: str,
    location: str,
    latitude: float,
    longitude: float,
    max_results: int,
    detail_limit: int | None,
    zoom: int,
) -> tuple[list[dict], int]:
    """Scrape a single grid cell with retry and fresh browser per attempt.

    A new browser is launched per attempt and closed when done, to keep
    memory usage low on constrained Docker hosts (~2.8 GB RAM).

    Args:
        detail_limit: Max detail pages to scrape per cell.
            None = scrape all, 0 = skip details entirely.

    Returns (listings, pages_scraped).
    """
    for attempt in range(MAX_CELL_RETRIES):
        browser = None
        try:
            browser, context = await _create_browser_context(p)
            page = await context.new_page()

            search_url = _build_search_url(
                keyword, location, latitude, longitude, zoom,
            )
            await page.goto(
                search_url, wait_until="domcontentloaded", timeout=30000,
            )

            # Handle consent dialog (including iframe variants).
            await _handle_consent_dialog(page)

            # Verify we landed on Google Maps, not consent or captcha
            current_url = page.url
            if "consent" in current_url or "sorry" in current_url:
                logger.error(
                    "Failed to bypass consent/captcha page: %s", current_url,
                )
                return [], 1

            # Wait for results
            try:
                await page.wait_for_selector(
                    'div[role="feed"]', timeout=15000,
                )
            except PlaywrightTimeout:
                logger.warning(
                    "No results feed for '%s' at (%.4f, %.4f); url=%s",
                    keyword, latitude, longitude,
                    page.url,
                )
                return [], 1

            max_scrolls = max(1, max_results // 15)
            await _scroll_results_panel(
                page, max_scrolls=min(max_scrolls, 8),
            )

            listings = await _extract_listings_from_feed(page)
            listings = listings[:max_results]

            logger.info(
                "Extracted %d listings from feed", len(listings),
            )

            # Close the feed page to free memory before details
            await page.close()

            # Scrape detail pages (one page at a time, close after each)
            should_scrape = (
                detail_limit is None or detail_limit > 0
            ) and listings
            if should_scrape:
                cap = len(listings)
                if detail_limit is not None:
                    cap = min(cap, detail_limit)
                logger.info(
                    "Scraping %d/%d detail pages...",
                    cap, len(listings),
                )

                for i in range(cap):
                    detail_page = await context.new_page()
                    listings[i] = await _scrape_detail_page(
                        detail_page, listings[i],
                    )
                    await detail_page.close()

                    if (i + 1) % 10 == 0:
                        logger.info(
                            "Detail progress: %d/%d", i + 1, cap,
                        )

            # Ensure place_ids
            for listing in listings:
                if not listing.get("place_id"):
                    identity = (
                        f"{listing.get('name', '')}|"
                        f"{listing.get('address', '')}|"
                        f"{listing.get('maps_url', '')}"
                    )
                    digest = hashlib.sha256(
                        identity.encode(),
                    ).hexdigest()[:16]
                    listing["place_id"] = f"pw_{digest}"

            return listings, 1

        except Exception as e:
            backoff = RETRY_BACKOFF_BASE * (3 ** attempt)
            logger.warning(
                "Cell (%.4f, %.4f) attempt %d/%d failed: %s."
                " Retrying in %ds...",
                latitude, longitude,
                attempt + 1, MAX_CELL_RETRIES, e, backoff,
            )
            if attempt < MAX_CELL_RETRIES - 1:
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    "Cell (%.4f, %.4f) failed after %d attempts",
                    latitude, longitude, MAX_CELL_RETRIES,
                )
                return [], 1

        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

    return [], 1


async def scrape_google_maps(
    keyword: str,
    location: str,
    latitude: float,
    longitude: float,
    max_results: int = 60,
    detail_limit: int | None = None,
    zoom: int = 14,
) -> tuple[list[dict], int]:
    """Scrape Google Maps search results using Playwright.

    This is the PRIMARY data source — free, self-hosted, no API key.

    Args:
        keyword: Business type or search term.
        location: Location description (e.g., "Austin, TX").
        latitude: Center latitude for the search.
        longitude: Center longitude for the search.
        max_results: Maximum number of listings to extract.
        detail_limit: Max detail pages to scrape per cell.
            None = scrape all (small jobs), 0 = skip details.
        zoom: Google Maps zoom level.

    Returns:
        Tuple of (list of listing dicts, pages scraped count).
    """
    # Default: respect global setting if detail_limit not specified
    if detail_limit is None and not settings.playwright_scrape_details:
        detail_limit = 0

    logger.info(
        "Playwright scraping: '%s' in '%s' at (%.4f, %.4f)"
        " detail_limit=%s",
        keyword, location, latitude, longitude, detail_limit,
    )

    async with async_playwright() as p:
        listings, pages_scraped = await _scrape_single_cell(
            p, keyword, location, latitude, longitude,
            max_results, detail_limit, zoom,
        )

    logger.info(
        "Playwright scrape complete: %d listings", len(listings),
    )
    return listings, pages_scraped
