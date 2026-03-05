import pytest
from base.models import Facility
from conftest import auth_headers, make_session


pytestmark = pytest.mark.django_db


class TestListFacilities:

    def test_list(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/api/facilities", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "facilities" in data
        assert len(data["facilities"]) >= 1

    def test_filter_by_type(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/api/facilities?facility_type=warehouse", **admin_headers)
        assert resp.status_code == 200
        facilities = resp.json()["data"]["facilities"]
        assert all(f["facility_type"] == "warehouse" for f in facilities)

    def test_filter_by_state(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/api/facilities?state=TX", **admin_headers)
        facilities = resp.json()["data"]["facilities"]
        assert len(facilities) >= 1

    def test_search(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/api/facilities?search=FAC001", **admin_headers)
        facilities = resp.json()["data"]["facilities"]
        assert len(facilities) >= 1

    def test_pagination(self, api_client, admin_headers, db):
        for i in range(5):
            Facility.objects.create(
                code=f"PG-{i}", name=f"Fac {i}", city="Test", state="CA",
                facility_type="warehouse",
            )
        resp = api_client.get("/api/facilities?per_page=2", **admin_headers)
        data = resp.json()["data"]
        assert len(data["facilities"]) == 2
        assert data["pagination"]["total"] == 5

    def test_auth_required(self, api_client):
        resp = api_client.get("/api/facilities")
        assert resp.status_code == 401


class TestGetFacility:

    def test_valid(self, api_client, admin_headers, sample_facility):
        resp = api_client.get(f"/api/facilities/{sample_facility.pk}", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["code"] == "FAC001"

    def test_not_found(self, api_client, admin_headers):
        resp = api_client.get("/api/facilities/99999", **admin_headers)
        assert resp.status_code == 404
