"""Website email and social media link extractor.

Visits business websites to extract contact emails and social media URLs.
Used as a supplementary enrichment layer — no API key required.
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[^\s\"'<>]+"),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[^\s\"'<>]+"),
    "linkedin": re.compile(
        r"https?://(?:www\.)?linkedin\.com/(?:company|in)/[^\s\"'<>]+"
    ),
    "twitter": re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[^\s\"'<>]+"),
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/[^\s\"'<>]+"),
}

# Junk email patterns to exclude
EXCLUDED_SUBSTRINGS = frozenset({
    "sentry@", "webpack@", "noreply@", "no-reply@", "example@", "test@",
    "wix.com", "sentry.io", "w3.org", "schema.org", "googleapis.com",
    "google.com", "cloudflare.com", "wordpress.org", "gravatar.com",
    ".png", ".jpg", ".gif", ".svg", ".css", ".js",
})

# Common contact page paths to try
CONTACT_PATHS = ("/contact", "/contact-us", "/about", "/about-us")

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _clean_emails(raw_emails: list[str]) -> list[str]:
    """Deduplicate and filter out junk emails."""
    seen: set[str] = set()
    clean: list[str] = []
    for email in raw_emails:
        email = email.lower().strip()
        if email in seen:
            continue
        if any(excl in email for excl in EXCLUDED_SUBSTRINGS):
            continue
        seen.add(email)
        clean.append(email)
    return clean[:5]


def _clean_social_url(url: str) -> str:
    """Strip trailing quote/bracket chars from a regex-captured URL."""
    return url.rstrip("\"'/>#);,")


async def extract_contact_from_website(
    website_url: str, timeout: float = 10.0,
) -> dict:
    """Visit a website and extract emails and social media links.

    Args:
        website_url: Full URL to scrape (must start with http).
        timeout: Request timeout in seconds.

    Returns:
        Dict with keys: primary_email, emails, social_links.
    """
    result: dict = {"emails": [], "social_links": {}, "primary_email": None}

    if not website_url or not website_url.startswith("http"):
        return result

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout, verify=False,
        ) as client:
            # Fetch main page
            resp = await client.get(website_url, headers=REQUEST_HEADERS)
            all_html = resp.text

            # Also try common contact pages (best-effort)
            base = website_url.rstrip("/")
            for path in CONTACT_PATHS:
                try:
                    contact_resp = await client.get(
                        f"{base}{path}", headers=REQUEST_HEADERS,
                    )
                    if contact_resp.status_code == 200:
                        all_html += contact_resp.text
                except httpx.HTTPError:
                    pass

            # Extract emails
            raw_emails = EMAIL_REGEX.findall(all_html)
            clean = _clean_emails(raw_emails)
            result["emails"] = clean
            result["primary_email"] = clean[0] if clean else None

            # Extract social links
            for platform, pattern in SOCIAL_PATTERNS.items():
                matches = pattern.findall(all_html)
                if matches:
                    result["social_links"][platform] = _clean_social_url(matches[0])

    except httpx.TimeoutException:
        logger.debug("Timeout scraping %s", website_url)
    except Exception as exc:
        logger.debug("Failed to scrape %s: %s", website_url, str(exc)[:100])

    return result
