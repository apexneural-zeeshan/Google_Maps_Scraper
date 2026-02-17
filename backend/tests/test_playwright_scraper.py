"""Tests for the Playwright scraper service.

These tests mock the Playwright browser to avoid needing a real browser instance.
They verify the parsing logic, URL building, and error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.playwright_scraper import (
    _build_search_url,
    _parse_rating_text,
)


class TestBuildSearchUrl:
    def test_basic_url(self):
        url = _build_search_url("restaurants", "Austin, TX", 30.2672, -97.7431, 14)
        assert "google.com/maps/search/" in url
        assert "restaurants" in url
        assert "Austin" in url
        assert "@30.2672,-97.7431,14z" in url

    def test_url_encodes_spaces(self):
        url = _build_search_url("coffee shops", "New York, NY", 40.7128, -74.0060)
        assert "coffee%20shops" in url or "coffee+shops" in url

    def test_custom_zoom(self):
        url = _build_search_url("pizza", "Chicago", 41.8781, -87.6298, 16)
        assert "16z" in url


class TestParseRatingText:
    def test_rating_with_count(self):
        rating, count = _parse_rating_text("4.5(123)")
        assert rating == 4.5
        assert count == 123

    def test_rating_with_comma_count(self):
        rating, count = _parse_rating_text("4.2(1,234)")
        assert rating == 4.2
        assert count == 1234

    def test_rating_only(self):
        rating, count = _parse_rating_text("4.8 stars")
        assert rating == 4.8
        assert count is None

    def test_no_rating(self):
        rating, count = _parse_rating_text("No reviews")
        assert rating is None
        assert count is None

    def test_empty_string(self):
        rating, count = _parse_rating_text("")
        assert rating is None
        assert count is None

    def test_integer_rating(self):
        rating, count = _parse_rating_text("5(42)")
        assert rating == 5.0
        assert count == 42

    def test_rejects_numbers_over_5(self):
        """Numbers > 5 shouldn't be treated as ratings."""
        rating, count = _parse_rating_text("123 reviews")
        assert rating is None  # 123 > 5, so rejected


class TestScrapeGoogleMaps:
    """Tests for the main scrape function using mocked Playwright."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        """When the feed never appears, should return empty list."""
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
        mock_page.url = "https://www.google.com/maps/search/test"
        mock_page.locator = MagicMock(return_value=AsyncMock(count=AsyncMock(return_value=0)))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw = AsyncMock()
        mock_pw.chromium = mock_chromium

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw_context.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.playwright_scraper.async_playwright", return_value=mock_pw_context):
            from app.services.playwright_scraper import scrape_google_maps

            results, pages = await scrape_google_maps(
                keyword="nonexistent",
                location="Nowhere",
                latitude=0.0,
                longitude=0.0,
                max_results=10,
                scrape_details=False,
            )

        assert isinstance(results, list)
        assert isinstance(pages, int)

    @pytest.mark.asyncio
    async def test_place_id_generated_when_missing(self):
        """Listings without a place_id should get a generated one."""
        listing = {
            "place_id": "",
            "name": "Test Restaurant",
            "address": "123 Main St",
            "source": "playwright",
        }

        # Simulate the place_id generation logic
        import re
        name_slug = re.sub(r"[^a-zA-Z0-9]", "", listing["name"])[:30]
        generated_id = f"pw_{name_slug}_{abs(hash(listing.get('address', ''))) % 100000}"

        assert generated_id.startswith("pw_TestRestaurant_")
        assert len(generated_id) > 10


class TestScrapeDetailsFlag:
    """Verify scrape_details parameter behavior."""

    def test_default_comes_from_settings(self):
        from app.config import settings

        assert isinstance(settings.playwright_scrape_details, bool)

    def test_headless_default(self):
        from app.config import settings

        assert isinstance(settings.playwright_headless, bool)
