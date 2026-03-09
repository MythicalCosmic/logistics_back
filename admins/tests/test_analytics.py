import pytest
from datetime import timedelta

from django.utils import timezone

from base.models import Load
from conftest import make_load, _make_user, make_session, auth_headers


pytestmark = pytest.mark.django_db


def _seed_loads(admin_user, count=10):
    """Create loads with varying load_ids to simulate duplicates."""
    now = timezone.now()
    loads = []
    for i in range(count):
        loads.append(Load(
            load_id=f"LD-{i % 5}",  # 5 unique IDs → duplicates
            tour_id=f"TR-{i % 3}",
            origin_facility=f"ORIG-{i % 3}",
            origin_city=["Dallas", "Houston", "Austin"][i % 3],
            origin_state="TX",
            origin_datetime=now - timedelta(days=i % 7),
            destination_facility=f"DEST-{i % 3}",
            destination_city=["Phoenix", "Denver", "LA"][i % 3],
            destination_state=["AZ", "CO", "CA"][i % 3],
            destination_datetime=now - timedelta(days=i % 7) + timedelta(hours=5),
            total_miles=200 + i * 10,
            payout=400 + i * 20,
            rate_per_mile=2.0,
            status=["available", "booked", "delivered"][i % 3],
            registered_by=admin_user,
        ))
    Load.objects.bulk_create(loads)


class TestAnalyticsOverview:

    def test_overview(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get("/admin-api/analytics/overview", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_loads" in data
        assert data["total_loads"] == 20
        assert "total_unique_routes" in data
        assert "this_week" in data
        assert "top_routes" in data
        assert "top_routes_this_week" in data

    def test_overview_empty(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/analytics/overview", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total_loads"] == 0

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/analytics/overview", **driver_headers)
        assert resp.status_code == 403

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/admin-api/analytics/overview")
        assert resp.status_code == 401


class TestLoadFrequency:

    def test_frequency(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get("/admin-api/analytics/loads/frequency?period=30d", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "loads" in data
        assert "pagination" in data
        assert len(data["loads"]) >= 1
        for load in data["loads"]:
            assert load["count"] >= 2
            assert "status_breakdown" in load
            assert "most_expensive" in load
            assert "cheapest" in load
            assert "total_payout" in load

    def test_frequency_min_count(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get(
            "/admin-api/analytics/loads/frequency?period=30d&min_count=5",
            **admin_headers,
        )
        assert resp.status_code == 200
        loads = resp.json()["data"]["loads"]
        assert all(l["count"] >= 5 for l in loads)

    def test_frequency_custom_period(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 10)
        resp = api_client.get("/admin-api/analytics/loads/frequency?period=24h", **admin_headers)
        assert resp.status_code == 200

    def test_frequency_pagination(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get(
            "/admin-api/analytics/loads/frequency?period=30d&per_page=2",
            **admin_headers,
        )
        data = resp.json()["data"]
        assert len(data["loads"]) <= 2

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/analytics/loads/frequency", **driver_headers)
        assert resp.status_code == 403


class TestRouteFrequency:

    def test_routes(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get("/admin-api/analytics/loads/routes?period=30d", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "routes" in data
        assert len(data["routes"]) >= 1
        route = data["routes"][0]
        assert "load_id" in route
        assert "count" in route
        assert "total_payout" in route
        assert "most_expensive" in route
        assert "cheapest" in route

    def test_routes_pagination(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get(
            "/admin-api/analytics/loads/routes?period=30d&per_page=1",
            **admin_headers,
        )
        data = resp.json()["data"]
        assert len(data["routes"]) <= 1

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/analytics/loads/routes", **driver_headers)
        assert resp.status_code == 403


class TestTrends:

    def test_daily_trends(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get("/admin-api/analytics/loads/trends?period=30d&group_by=day", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "data" in data
        assert "summary" in data
        assert data["group_by"] == "day"
        assert data["summary"]["total_loads"] == 20

    def test_weekly_trends(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get("/admin-api/analytics/loads/trends?period=30d&group_by=week", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["group_by"] == "week"

    def test_trends_data_fields(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get("/admin-api/analytics/loads/trends?period=30d", **admin_headers)
        data = resp.json()["data"]
        for entry in data["data"]:
            assert "count" in entry
            assert "total_payout" in entry
            assert "most_expensive" in entry
            assert "cheapest" in entry
            assert "unique_routes" in entry

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/analytics/loads/trends", **driver_headers)
        assert resp.status_code == 403


class TestComparePeriods:

    def test_compare(self, api_client, admin_headers, admin_user):
        _seed_loads(admin_user, 20)
        resp = api_client.get(
            "/admin-api/analytics/loads/compare?period_a=7d&period_b=14d",
            **admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "period_a" in data
        assert "period_b" in data
        assert "changes" in data
        assert "total_loads" in data["changes"]
        assert "change" in data["changes"]["total_loads"]
        assert "change_pct" in data["changes"]["total_loads"]

    def test_compare_empty_periods(self, api_client, admin_headers):
        resp = api_client.get(
            "/admin-api/analytics/loads/compare?period_a=7d&period_b=14d",
            **admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["period_a"]["stats"]["total_loads"] == 0

    def test_compare_requires_analytics_compare_permission(self, api_client, seed_permissions):
        from base.models import User
        user = _make_user("noperm@test.com")
        session = make_session(user)
        resp = api_client.get(
            "/admin-api/analytics/loads/compare?period_a=7d&period_b=14d",
            **auth_headers(session),
        )
        assert resp.status_code == 403

    def test_manager_can_compare(self, api_client, manager_headers, admin_user):
        _seed_loads(admin_user, 10)
        resp = api_client.get(
            "/admin-api/analytics/loads/compare?period_a=7d&period_b=14d",
            **manager_headers,
        )
        assert resp.status_code == 200
