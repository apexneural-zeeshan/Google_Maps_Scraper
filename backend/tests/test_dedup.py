"""Tests for the deduplication service."""

from app.services.dedup import deduplicate


class TestDeduplicate:
    def test_empty_list(self):
        assert deduplicate([]) == []

    def test_no_duplicates(self):
        leads = [
            {"place_id": "a", "name": "Place A", "source": "places_api", "latitude": 30.0, "longitude": -97.0},
            {"place_id": "b", "name": "Place B", "source": "places_api", "latitude": 30.1, "longitude": -97.1},
        ]
        result = deduplicate(leads)
        assert len(result) == 2

    def test_exact_place_id_dedup(self, sample_leads):
        """Leads with the same place_id should be merged."""
        result = deduplicate(sample_leads)
        # 3 input leads, 2 unique place_ids → 2 results
        assert len(result) == 2

    def test_merged_fields_filled_in(self, sample_leads):
        """Merging should fill in missing fields from the duplicate."""
        result = deduplicate(sample_leads)

        # Find Joe's Pizza in results
        joes = next(r for r in result if r["place_id"] == "ChIJ_abc123")

        # Should have opening_hours from serp_api (was None in places_api)
        assert joes["opening_hours"] is not None
        assert joes["opening_hours"]["text"] == "Mon-Sun 11am-10pm"

        # Should keep price_level from places_api (was 2, not None)
        assert joes["price_level"] == 2

    def test_merged_source_tracking(self, sample_leads):
        """Merged leads should have combined source."""
        result = deduplicate(sample_leads)
        joes = next(r for r in result if r["place_id"] == "ChIJ_abc123")
        assert "playwright" in joes["source"]
        assert "serp_api" in joes["source"]

    def test_list_fields_merged(self, sample_leads):
        """List fields (types, photos) should have unique items merged."""
        result = deduplicate(sample_leads)
        joes = next(r for r in result if r["place_id"] == "ChIJ_abc123")

        # photos: places_api had [], serp_api had [{"url": "..."}]
        assert len(joes["photos"]) >= 1

    def test_fuzzy_match_same_name_nearby(self):
        """Leads with similar names at the same location should merge."""
        leads = [
            {
                "place_id": "id_1",
                "name": "McDonald's",
                "address": "100 Main St",
                "source": "places_api",
                "latitude": 30.2672,
                "longitude": -97.7431,
                "phone": "+1-555-0001",
                "website": None,
            },
            {
                "place_id": "",  # No place_id from this source
                "name": "McDonalds",  # Slightly different spelling
                "address": "100 Main St",
                "source": "serp_api",
                "latitude": 30.2672,
                "longitude": -97.7431,
                "phone": None,
                "website": "https://mcdonalds.com",
            },
        ]
        result = deduplicate(leads)
        assert len(result) == 1
        # Website should be filled in from serp_api
        assert result[0]["website"] == "https://mcdonalds.com"

    def test_fuzzy_no_match_different_location(self):
        """Similar names at different locations should NOT merge."""
        leads = [
            {
                "place_id": "id_1",
                "name": "Starbucks",
                "source": "places_api",
                "latitude": 30.2672,
                "longitude": -97.7431,
            },
            {
                "place_id": "",
                "name": "Starbucks",
                "source": "serp_api",
                "latitude": 31.0000,  # Far away
                "longitude": -97.0000,
            },
        ]
        result = deduplicate(leads)
        assert len(result) == 2

    def test_single_lead(self):
        leads = [{"place_id": "x", "name": "Only One", "source": "places_api"}]
        result = deduplicate(leads)
        assert len(result) == 1
        assert result[0]["name"] == "Only One"
