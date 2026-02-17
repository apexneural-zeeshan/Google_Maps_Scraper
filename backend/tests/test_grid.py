"""Tests for the grid generation service."""

from app.services.grid import (
    GridPoint,
    estimate_api_calls,
    estimate_cost_usd,
    generate_grid,
    haversine,
)


class TestHaversine:
    def test_same_point(self):
        assert haversine(30.0, -97.0, 30.0, -97.0) == 0.0

    def test_known_distance(self):
        # Austin to Dallas is approximately 290 km
        dist = haversine(30.2672, -97.7431, 32.7767, -96.7970)
        assert 280 < dist < 300

    def test_short_distance(self):
        # Two close points should be < 1km
        dist = haversine(30.2672, -97.7431, 30.2680, -97.7440)
        assert dist < 1.0

    def test_symmetry(self):
        d1 = haversine(30.0, -97.0, 31.0, -96.0)
        d2 = haversine(31.0, -96.0, 30.0, -97.0)
        assert abs(d1 - d2) < 0.001


class TestGenerateGrid:
    def test_small_radius_single_cell(self):
        """A radius smaller than 5km should return a single cell."""
        grid = generate_grid(30.2672, -97.7431, 2.0)
        assert len(grid) == 1
        assert grid[0].latitude == 30.2672
        assert grid[0].longitude == -97.7431
        assert grid[0].search_radius_m == 2000

    def test_larger_radius_multiple_cells(self):
        """A 10km radius should produce multiple grid points."""
        grid = generate_grid(30.2672, -97.7431, 10.0)
        assert len(grid) > 1

    def test_all_points_have_valid_coordinates(self):
        grid = generate_grid(30.2672, -97.7431, 15.0)
        for point in grid:
            assert -90 <= point.latitude <= 90
            assert -180 <= point.longitude <= 180
            assert point.search_radius_m > 0

    def test_center_point_included(self):
        """The center point should be close to one of the grid points."""
        center_lat, center_lng = 30.2672, -97.7431
        grid = generate_grid(center_lat, center_lng, 10.0)

        min_dist = min(
            haversine(center_lat, center_lng, p.latitude, p.longitude)
            for p in grid
        )
        assert min_dist < 5.0  # At least one point within 5km of center

    def test_grid_points_within_radius(self):
        """All grid points should be roughly within the search radius."""
        center_lat, center_lng, radius = 30.2672, -97.7431, 10.0
        grid = generate_grid(center_lat, center_lng, radius)

        for point in grid:
            dist = haversine(center_lat, center_lng, point.latitude, point.longitude)
            # Allow some tolerance for cell search radius
            assert dist < radius + 5.0

    def test_overlap_factor_increases_density(self):
        """Higher overlap should produce more grid points."""
        grid_low = generate_grid(30.2672, -97.7431, 15.0, overlap_factor=0.1)
        grid_high = generate_grid(30.2672, -97.7431, 15.0, overlap_factor=0.4)
        assert len(grid_high) >= len(grid_low)

    def test_zero_overlap(self):
        grid = generate_grid(30.2672, -97.7431, 15.0, overlap_factor=0.0)
        assert len(grid) > 0


class TestEstimateApiCalls:
    def test_single_point(self):
        grid = [GridPoint(30.0, -97.0, 5000)]
        calls = estimate_api_calls(grid)
        assert calls["places_api"] == 2
        assert calls["serp_api"] == 1

    def test_multiple_points(self):
        grid = [GridPoint(30.0 + i * 0.01, -97.0, 5000) for i in range(5)]
        calls = estimate_api_calls(grid)
        assert calls["places_api"] == 10
        assert calls["serp_api"] == 5


class TestEstimateCost:
    def test_cost_increases_with_grid_size(self):
        grid_small = [GridPoint(30.0, -97.0, 5000)]
        grid_large = [GridPoint(30.0 + i * 0.01, -97.0, 5000) for i in range(10)]
        assert estimate_cost_usd(grid_large) > estimate_cost_usd(grid_small)

    def test_cost_is_positive(self):
        grid = [GridPoint(30.0, -97.0, 5000)]
        assert estimate_cost_usd(grid) > 0
