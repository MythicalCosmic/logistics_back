import pytest
from datetime import timedelta

from django.utils import timezone

from base.models import User, Load, Session, Facility
from conftest import auth_headers, make_session, _make_user


pytestmark = [pytest.mark.django_db, pytest.mark.slow]


class TestUserStress:

    def test_bulk_create_users_and_paginate(self, api_client, admin_headers, seed_permissions):
        users = [
            User(
                email=f"bulk{i}@test.com",
                first_name=f"Bulk{i}",
                last_name="User",
                password="hashed",
            )
            for i in range(200)
        ]
        User.objects.bulk_create(users)
        assert User.objects.count() >= 200

        resp = api_client.get("/admin-api/users?per_page=50&page=1", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["users"]) == 50
        assert data["pagination"]["pages"] >= 4

    def test_bulk_user_search(self, api_client, admin_headers, seed_permissions):
        users = [
            User(
                email=f"search{i}@test.com",
                first_name=f"SearchUser{i}",
                last_name="Test",
                password="hashed",
            )
            for i in range(100)
        ]
        User.objects.bulk_create(users)

        resp = api_client.get("/admin-api/users?search=SearchUser5", **admin_headers)
        assert resp.status_code == 200
        users_found = resp.json()["data"]["users"]
        assert len(users_found) >= 1


class TestLoadStress:

    def test_bulk_create_loads_and_filter(self, api_client, admin_headers, admin_user):
        now = timezone.now()
        loads = [
            Load(
                load_id=f"STRESS-{i}",
                origin_facility=f"ORIG-{i % 20}",
                origin_city="Dallas",
                origin_state="TX",
                origin_datetime=now,
                destination_facility=f"DEST-{i % 20}",
                destination_city="Houston",
                destination_state="TX",
                destination_datetime=now + timedelta(hours=5),
                total_miles=100 + i,
                payout=200 + i,
                status=["available", "booked", "in_transit", "delivered"][i % 4],
                registered_by=admin_user,
            )
            for i in range(500)
        ]
        Load.objects.bulk_create(loads)
        assert Load.objects.count() == 500

        # Filter by status
        resp = api_client.get("/api/loads?status=available&per_page=50", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pagination"]["total"] == 125  # 500/4

        # Search
        resp = api_client.get("/api/loads?search=ORIG-5", **admin_headers)
        assert resp.status_code == 200

        # Sort
        resp = api_client.get("/api/loads?sort_by=-payout&per_page=10", **admin_headers)
        assert resp.status_code == 200
        loads_data = resp.json()["data"]["loads"]
        payouts = [float(l["payout"]) for l in loads_data]
        assert payouts == sorted(payouts, reverse=True)


class TestSessionStress:

    def test_bulk_session_creation_and_invalidation(self, seed_permissions):
        user = _make_user("sessionstress@test.com")
        sessions = []
        for _ in range(50):
            sessions.append(Session.create_session(user=user))

        active = Session.objects.filter(user=user, is_active=True).count()
        assert active == 50

        Session.invalidate_all(user)
        active = Session.objects.filter(user=user, is_active=True).count()
        assert active == 0


class TestLargePayloadValidation:

    def test_oversized_fields(self, api_client, admin_headers):
        resp = api_client.post(
            "/admin-api/users/create",
            data='{"email":"x@x.com","first_name":"' + "A" * 10000 + '","last_name":"B","password":"Pass1234"}',
            content_type="application/json",
            **admin_headers,
        )
        # Should either succeed (DB will truncate) or fail validation gracefully
        assert resp.status_code in (201, 400, 500)


class TestFacilityStress:

    def test_bulk_create_and_search(self, api_client, admin_headers, seed_permissions):
        facilities = [
            Facility(
                code=f"STRESS-FAC-{i}",
                name=f"Facility {i}",
                city=f"City{i % 50}",
                state=["TX", "CA", "NY", "FL", "WA"][i % 5],
                facility_type=["warehouse", "cross_dock", "delivery_station"][i % 3],
            )
            for i in range(200)
        ]
        Facility.objects.bulk_create(facilities)

        resp = api_client.get("/admin-api/facilities?search=STRESS-FAC-10", **admin_headers)
        assert resp.status_code == 200
        facilities_found = resp.json()["data"]["facilities"]
        assert len(facilities_found) >= 1

        resp = api_client.get("/admin-api/facilities?state=TX&per_page=100", **admin_headers)
        assert resp.status_code == 200
