import pytest
from base.models import Facility, Load
from conftest import post_json, put_json, delete_json, make_load, _make_user, make_session, auth_headers


pytestmark = pytest.mark.django_db


class TestAdminListFacilities:

    def test_list(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/admin-api/facilities", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "facilities" in data
        assert "pagination" in data

    def test_filter_by_type(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/admin-api/facilities?facility_type=warehouse", **admin_headers)
        facilities = resp.json()["data"]["facilities"]
        assert all(f["facility_type"] == "warehouse" for f in facilities)

    def test_search(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/admin-api/facilities?search=FAC001", **admin_headers)
        facilities = resp.json()["data"]["facilities"]
        assert len(facilities) >= 1

    def test_permission_required(self, api_client, seed_permissions):
        # User with no roles has no permissions
        user = _make_user("noperm@test.com")
        session = make_session(user)
        resp = api_client.get("/admin-api/facilities", **auth_headers(session))
        assert resp.status_code == 403


class TestAdminCreateFacility:

    def test_valid(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/facilities/create", {
            "code": "NEW001",
            "name": "New Facility",
            "city": "Austin",
            "state": "TX",
            "facility_type": "warehouse",
        }, **admin_headers)
        assert resp.status_code == 201
        assert Facility.objects.filter(code="NEW001").exists()

    def test_duplicate_code(self, api_client, admin_headers, sample_facility):
        resp = post_json(api_client, "/admin-api/facilities/create", {
            "code": "FAC001",
            "name": "Dup",
        }, **admin_headers)
        assert resp.status_code == 400

    def test_missing_code(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/facilities/create", {
            "name": "No Code",
        }, **admin_headers)
        assert resp.status_code == 400

    def test_permission_required(self, api_client, driver_headers):
        resp = post_json(api_client, "/admin-api/facilities/create",
                         {"code": "X"}, **driver_headers)
        assert resp.status_code == 403


class TestAdminGetFacility:

    def test_valid(self, api_client, admin_headers, sample_facility):
        resp = api_client.get(f"/admin-api/facilities/{sample_facility.pk}", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["code"] == "FAC001"

    def test_not_found(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/facilities/99999", **admin_headers)
        assert resp.status_code == 404


class TestAdminUpdateFacility:

    def test_valid(self, api_client, admin_headers, sample_facility):
        resp = put_json(api_client, f"/admin-api/facilities/{sample_facility.pk}/update",
                        {"name": "Updated Name"}, **admin_headers)
        assert resp.status_code == 200
        sample_facility.refresh_from_db()
        assert sample_facility.name == "Updated Name"

    def test_duplicate_code(self, api_client, admin_headers, sample_facility):
        Facility.objects.create(code="OTHER001", name="Other", facility_type="warehouse")
        resp = put_json(api_client, f"/admin-api/facilities/{sample_facility.pk}/update",
                        {"code": "OTHER001"}, **admin_headers)
        assert resp.status_code == 400


class TestAdminDeleteFacility:

    def test_valid(self, api_client, admin_headers, seed_permissions):
        fac = Facility.objects.create(code="DEL001", name="ToDelete", facility_type="warehouse")
        resp = delete_json(api_client, f"/admin-api/facilities/{fac.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 200
        assert not Facility.objects.filter(code="DEL001").exists()

    def test_cannot_delete_with_loads(self, api_client, admin_headers, admin_user, sample_facility):
        make_load(admin_user, origin_facility=sample_facility.code)
        resp = delete_json(api_client, f"/admin-api/facilities/{sample_facility.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 400

    def test_not_found(self, api_client, admin_headers):
        resp = delete_json(api_client, "/admin-api/facilities/99999/delete",
                           {}, **admin_headers)
        assert resp.status_code == 404


class TestAdminFacilityStats:

    def test_stats(self, api_client, admin_headers, sample_facility):
        resp = api_client.get("/admin-api/facilities/stats", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_facilities" in data
        assert "type_breakdown" in data
