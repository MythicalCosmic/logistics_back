import json

import pytest
from django.utils import timezone
from datetime import timedelta

from base.models import Load, LoadLeg, Stop
from conftest import (
    post_json, put_json, auth_headers, make_session, make_load, _make_user,
)


pytestmark = pytest.mark.django_db


def _load_payload(**overrides):
    """Minimal valid load creation payload."""
    now = timezone.now()
    data = {
        "origin_facility": "FAC001",
        "origin_city": "Dallas",
        "origin_state": "TX",
        "origin_datetime": now.isoformat(),
        "destination_facility": "FAC002",
        "destination_city": "Houston",
        "destination_state": "TX",
        "destination_datetime": (now + timedelta(hours=5)).isoformat(),
        "total_miles": 250,
        "payout": 500,
    }
    data.update(overrides)
    return data


class TestListLoads:

    def test_list_loads(self, api_client, admin_headers, admin_user):
        make_load(admin_user)
        resp = api_client.get("/api/loads", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "loads" in data
        assert "pagination" in data
        assert data["pagination"]["total"] >= 1

    def test_pagination(self, api_client, admin_headers, admin_user):
        for i in range(5):
            make_load(admin_user, load_id=f"LD-{i}")
        resp = api_client.get("/api/loads?page=1&per_page=2", **admin_headers)
        data = resp.json()["data"]
        assert len(data["loads"]) == 2
        assert data["pagination"]["total"] == 5

    def test_filter_by_status(self, api_client, admin_headers, admin_user):
        make_load(admin_user, status="delivered")
        make_load(admin_user, status="available", load_id="LD-avail")
        resp = api_client.get("/api/loads?status=delivered", **admin_headers)
        loads = resp.json()["data"]["loads"]
        assert all(l["status"] == "delivered" for l in loads)

    def test_filter_by_origin(self, api_client, admin_headers, admin_user):
        make_load(admin_user, origin_city="Austin", origin_state="TX")
        resp = api_client.get("/api/loads?origin=Austin", **admin_headers)
        assert resp.status_code == 200

    def test_search(self, api_client, admin_headers, admin_user):
        make_load(admin_user, load_id="UNIQUE-SEARCH-123")
        resp = api_client.get("/api/loads?search=UNIQUE-SEARCH-123", **admin_headers)
        loads = resp.json()["data"]["loads"]
        assert len(loads) >= 1

    def test_sort_by_payout(self, api_client, admin_headers, admin_user):
        make_load(admin_user, payout=100, load_id="LD-low")
        make_load(admin_user, payout=900, load_id="LD-high")
        resp = api_client.get("/api/loads?sort_by=-payout", **admin_headers)
        loads = resp.json()["data"]["loads"]
        assert float(loads[0]["payout"]) >= float(loads[1]["payout"])

    def test_permission_required(self, api_client, db):
        resp = api_client.get("/api/loads")
        assert resp.status_code == 401

    def test_driver_with_loads_view_permission(self, api_client, driver_headers, admin_user):
        make_load(admin_user)
        resp = api_client.get("/api/loads", **driver_headers)
        assert resp.status_code == 200


class TestCreateLoad:

    def test_valid_create(self, api_client, dispatcher_headers):
        resp = post_json(api_client, "/api/loads/create", _load_payload(), **dispatcher_headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["origin_facility"] == "FAC001"

    def test_create_with_legs_and_stops(self, api_client, dispatcher_headers):
        payload = _load_payload(
            legs=[{
                "leg_number": 1,
                "origin_facility": "FAC001",
                "destination_facility": "FAC002",
                "miles": 250,
            }],
            stops=[{
                "stop_number": 1,
                "facility_code": "FAC001",
                "city": "Dallas",
                "state": "TX",
            }, {
                "stop_number": 2,
                "facility_code": "FAC002",
                "city": "Houston",
                "state": "TX",
            }],
        )
        resp = post_json(api_client, "/api/loads/create", payload, **dispatcher_headers)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert len(data["legs"]) == 1
        assert len(data["stops"]) == 2

    def test_missing_required_fields(self, api_client, dispatcher_headers):
        resp = post_json(api_client, "/api/loads/create", {}, **dispatcher_headers)
        assert resp.status_code == 400

    def test_invalid_datetime_format(self, api_client, dispatcher_headers):
        payload = _load_payload(origin_datetime="not-a-date")
        resp = post_json(api_client, "/api/loads/create", payload, **dispatcher_headers)
        assert resp.status_code == 400

    def test_integer_datetime_rejected(self, api_client, dispatcher_headers):
        payload = _load_payload(origin_datetime=1234567890)
        resp = post_json(api_client, "/api/loads/create", payload, **dispatcher_headers)
        assert resp.status_code == 400

    def test_permission_required(self, api_client, driver_headers):
        resp = post_json(api_client, "/api/loads/create", _load_payload(), **driver_headers)
        assert resp.status_code == 403


class TestGetLoad:

    def test_valid(self, api_client, admin_headers, sample_load):
        resp = api_client.get(f"/api/loads/{sample_load.pk}", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == sample_load.pk

    def test_not_found(self, api_client, admin_headers):
        resp = api_client.get("/api/loads/99999", **admin_headers)
        assert resp.status_code == 404


class TestUpdateLoad:

    def test_valid_partial_update(self, api_client, admin_headers, sample_load):
        resp = put_json(api_client, f"/api/loads/{sample_load.pk}/update",
                        {"payout": 999.99}, **admin_headers)
        assert resp.status_code == 200
        sample_load.refresh_from_db()
        assert float(sample_load.payout) == 999.99

    def test_cannot_update_delivered(self, api_client, admin_headers, admin_user):
        load = make_load(admin_user, status="delivered")
        resp = put_json(api_client, f"/api/loads/{load.pk}/update",
                        {"payout": 999}, **admin_headers)
        assert resp.status_code == 400

    def test_permission_required(self, api_client, driver_headers, sample_load):
        resp = put_json(api_client, f"/api/loads/{sample_load.pk}/update",
                        {"payout": 999}, **driver_headers)
        assert resp.status_code == 403


class TestCancelLoad:

    def test_valid_cancel(self, api_client, admin_headers, sample_load):
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/cancel", {}, **admin_headers)
        assert resp.status_code == 200
        sample_load.refresh_from_db()
        assert sample_load.status == "cancelled"

    def test_cannot_cancel_delivered(self, api_client, admin_headers, admin_user):
        load = make_load(admin_user, status="delivered")
        resp = post_json(api_client, f"/api/loads/{load.pk}/cancel", {}, **admin_headers)
        assert resp.status_code == 400

    def test_cannot_cancel_already_cancelled(self, api_client, admin_headers, admin_user):
        load = make_load(admin_user, status="cancelled")
        resp = post_json(api_client, f"/api/loads/{load.pk}/cancel", {}, **admin_headers)
        assert resp.status_code == 400


class TestAssignDriver:

    def test_valid_assign(self, api_client, dispatcher_headers, dispatcher_user, sample_load):
        driver = _make_user("assignee@test.com")
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/assign",
                         {"driver_id": driver.pk}, **dispatcher_headers)
        assert resp.status_code == 200
        sample_load.refresh_from_db()
        assert sample_load.assigned_driver_id == driver.pk
        assert sample_load.status == "booked"

    def test_invalid_driver_id(self, api_client, dispatcher_headers, sample_load):
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/assign",
                         {"driver_id": 99999}, **dispatcher_headers)
        assert resp.status_code == 404

    def test_missing_driver_id(self, api_client, dispatcher_headers, sample_load):
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/assign",
                         {}, **dispatcher_headers)
        assert resp.status_code == 400

    def test_cannot_assign_to_in_transit(self, api_client, dispatcher_headers, admin_user):
        load = make_load(admin_user, status="in_transit")
        driver = _make_user("d2@test.com")
        resp = post_json(api_client, f"/api/loads/{load.pk}/assign",
                         {"driver_id": driver.pk}, **dispatcher_headers)
        assert resp.status_code == 400


class TestUpdateStatus:

    def test_valid_transition(self, api_client, admin_headers, admin_user):
        load = make_load(admin_user, status="booked")
        resp = post_json(api_client, f"/api/loads/{load.pk}/status",
                         {"status": "in_transit"}, **admin_headers)
        assert resp.status_code == 200
        load.refresh_from_db()
        assert load.status == "in_transit"

    def test_invalid_transition(self, api_client, admin_headers, admin_user):
        load = make_load(admin_user, status="delivered")
        resp = post_json(api_client, f"/api/loads/{load.pk}/status",
                         {"status": "available"}, **admin_headers)
        assert resp.status_code == 400

    def test_available_to_booked(self, api_client, admin_headers, sample_load):
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/status",
                         {"status": "booked"}, **admin_headers)
        assert resp.status_code == 200

    def test_available_to_delivered_invalid(self, api_client, admin_headers, sample_load):
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/status",
                         {"status": "delivered"}, **admin_headers)
        assert resp.status_code == 400

    def test_missing_status(self, api_client, admin_headers, sample_load):
        resp = post_json(api_client, f"/api/loads/{sample_load.pk}/status",
                         {}, **admin_headers)
        assert resp.status_code == 400


class TestMyLoads:

    def test_returns_only_assigned(self, api_client, driver_headers, driver_user, admin_user):
        make_load(admin_user, assigned_driver=driver_user, load_id="MINE")
        make_load(admin_user, load_id="NOT-MINE")
        resp = api_client.get("/api/loads/my", **driver_headers)
        assert resp.status_code == 200
        loads = resp.json()["data"]["loads"]
        assert len(loads) == 1
        assert loads[0]["load_id"] == "MINE"

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/api/loads/my")
        assert resp.status_code == 401


class TestLoadStats:

    def test_stats(self, api_client, admin_headers, admin_user):
        make_load(admin_user)
        resp = api_client.get("/api/loads/stats", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_loads" in data
        assert "status_breakdown" in data
        assert "financial" in data


class TestLoadStress:

    @pytest.mark.slow
    def test_bulk_create_and_paginate(self, api_client, admin_headers, admin_user):
        loads = [
            Load(
                load_id=f"BULK-{i}",
                origin_facility="FAC001",
                origin_city="Dallas",
                origin_state="TX",
                origin_datetime=timezone.now(),
                destination_facility="FAC002",
                destination_city="Houston",
                destination_state="TX",
                destination_datetime=timezone.now() + timedelta(hours=5),
                total_miles=250,
                payout=500 + i,
                registered_by=admin_user,
            )
            for i in range(100)
        ]
        Load.objects.bulk_create(loads)
        assert Load.objects.count() == 100

        # Paginate through
        resp = api_client.get("/api/loads?page=1&per_page=20", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["pagination"]["total"] == 100
        assert data["pagination"]["pages"] == 5

    @pytest.mark.slow
    def test_search_across_large_dataset(self, api_client, admin_headers, admin_user):
        loads = [
            Load(
                load_id=f"SEARCH-{i}",
                origin_facility=f"ORIG-{i % 10}",
                origin_city="Dallas",
                origin_state="TX",
                origin_datetime=timezone.now(),
                destination_facility=f"DEST-{i % 10}",
                destination_city="Houston",
                destination_state="TX",
                destination_datetime=timezone.now() + timedelta(hours=5),
                total_miles=250,
                payout=500,
                registered_by=admin_user,
            )
            for i in range(100)
        ]
        Load.objects.bulk_create(loads)

        resp = api_client.get("/api/loads?search=ORIG-5", **admin_headers)
        assert resp.status_code == 200
        loads_found = resp.json()["data"]["loads"]
        assert len(loads_found) >= 1
