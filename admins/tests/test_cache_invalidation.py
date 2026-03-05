import pytest
from base.models import Facility
from base.services.base_service import CacheService
from conftest import post_json


pytestmark = pytest.mark.django_db


class TestFacilityCacheInvalidation:
    """
    When a facility is created/updated/deleted via admin API,
    the main-side facility cache should be cleared so the new data
    shows up immediately on GET /api/facilities.
    """

    def test_admin_create_clears_main_cache(self, api_client, admin_headers):
        # Warm up main-side cache
        resp = api_client.get("/api/facilities", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["pagination"]["total"] == 0

        # Create via admin
        post_json(api_client, "/admin-api/facilities/create", {
            "code": "CACHE-TEST",
            "name": "Cache Test Facility",
            "city": "Dallas",
            "state": "TX",
            "facility_type": "warehouse",
        }, **admin_headers)

        # Main side should see the new facility immediately
        resp = api_client.get("/api/facilities", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["pagination"]["total"] == 1


class TestCacheServiceDeletePattern:

    def test_delete_pattern_clears_matching_keys(self):
        CacheService.set("test:list:1", "a")
        CacheService.set("test:list:2", "b")
        CacheService.set("test:detail:1", "c")
        CacheService.set("other:key", "d")

        CacheService.delete_pattern("test:list:*")

        assert CacheService.get("test:list:1") is None
        assert CacheService.get("test:list:2") is None
        assert CacheService.get("test:detail:1") == "c"
        assert CacheService.get("other:key") == "d"

    def test_delete_pattern_no_match(self):
        CacheService.set("keep:this", "val")
        CacheService.delete_pattern("nope:*")
        assert CacheService.get("keep:this") == "val"
