import pytest
from base.models import User, Session, Role
from conftest import post_json, put_json, delete_json, auth_headers, _make_user, make_session


pytestmark = pytest.mark.django_db


class TestListUsers:

    def test_list(self, api_client, admin_headers, admin_user):
        resp = api_client.get("/admin-api/users", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "users" in data
        assert "pagination" in data

    def test_pagination(self, api_client, admin_headers, seed_permissions):
        for i in range(5):
            _make_user(f"paguser{i}@test.com")
        resp = api_client.get("/admin-api/users?per_page=2", **admin_headers)
        data = resp.json()["data"]
        assert len(data["users"]) == 2

    def test_search(self, api_client, admin_headers, admin_user):
        resp = api_client.get("/admin-api/users?search=admin", **admin_headers)
        users = resp.json()["data"]["users"]
        assert len(users) >= 1

    def test_filter_by_role(self, api_client, admin_headers, admin_user):
        resp = api_client.get("/admin-api/users?role=admin", **admin_headers)
        users = resp.json()["data"]["users"]
        assert len(users) >= 1

    def test_filter_by_active(self, api_client, admin_headers, seed_permissions):
        inactive = _make_user("inactive@test.com")
        inactive.is_active = False
        inactive.save()
        resp = api_client.get("/admin-api/users?is_active=false", **admin_headers)
        users = resp.json()["data"]["users"]
        assert all(not u["is_active"] for u in users)

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/users", **driver_headers)
        assert resp.status_code == 403

    def test_unauthenticated(self, api_client):
        resp = api_client.get("/admin-api/users")
        assert resp.status_code == 401


class TestCreateUser:

    def test_valid(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/users/create", {
            "email": "newuser@test.com",
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass1",
        }, **admin_headers)
        assert resp.status_code == 201
        assert User.objects.filter(email="newuser@test.com").exists()

    def test_duplicate_email(self, api_client, admin_headers, admin_user):
        resp = post_json(api_client, "/admin-api/users/create", {
            "email": "admin@test.com",
            "first_name": "Dup",
            "last_name": "User",
            "password": "StrongPass1",
        }, **admin_headers)
        assert resp.status_code == 400

    def test_missing_fields(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/users/create", {}, **admin_headers)
        assert resp.status_code == 400

    def test_with_role_id(self, api_client, admin_headers, admin_role):
        resp = post_json(api_client, "/admin-api/users/create", {
            "email": "withrole@test.com",
            "first_name": "Role",
            "last_name": "User",
            "password": "StrongPass1",
            "role_id": admin_role.pk,
        }, **admin_headers)
        assert resp.status_code == 201

    def test_permission_required(self, api_client, driver_headers):
        resp = post_json(api_client, "/admin-api/users/create", {
            "email": "x@x.com", "first_name": "X", "last_name": "X", "password": "Pass1234",
        }, **driver_headers)
        assert resp.status_code == 403


class TestGetUser:

    def test_valid(self, api_client, admin_headers, admin_user):
        resp = api_client.get(f"/admin-api/users/{admin_user.pk}", **admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["email"] == "admin@test.com"

    def test_not_found(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/users/99999", **admin_headers)
        assert resp.status_code == 404


class TestUpdateUser:

    def test_valid(self, api_client, admin_headers, admin_user):
        target = _make_user("update@test.com")
        resp = put_json(api_client, f"/admin-api/users/{target.pk}/update",
                        {"first_name": "Updated"}, **admin_headers)
        assert resp.status_code == 200
        target.refresh_from_db()
        assert target.first_name == "Updated"

    def test_not_found(self, api_client, admin_headers):
        resp = put_json(api_client, "/admin-api/users/99999/update",
                        {"first_name": "X"}, **admin_headers)
        assert resp.status_code == 404


class TestDeleteUser:

    def test_valid(self, api_client, admin_headers, seed_permissions):
        target = _make_user("delete@test.com")
        resp = delete_json(api_client, f"/admin-api/users/{target.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 200
        target.refresh_from_db()
        assert not target.is_active

    def test_self_delete_blocked(self, api_client, admin_headers, admin_user):
        resp = delete_json(api_client, f"/admin-api/users/{admin_user.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 400

    def test_self_delete_with_force(self, api_client, admin_headers, admin_user):
        resp = delete_json(api_client, f"/admin-api/users/{admin_user.pk}/delete",
                           {"force": True}, **admin_headers)
        assert resp.status_code == 200


class TestToggleActive:

    def test_toggle(self, api_client, admin_headers, seed_permissions):
        target = _make_user("toggle@test.com")
        assert target.is_active is True
        resp = post_json(api_client, f"/admin-api/users/{target.pk}/toggle-active",
                         {}, **admin_headers)
        assert resp.status_code == 200
        target.refresh_from_db()
        assert target.is_active is False


class TestAdminChangePassword:

    def test_valid(self, api_client, admin_headers, seed_permissions):
        target = _make_user("chpw@test.com")
        resp = post_json(api_client, f"/admin-api/users/{target.pk}/change-password",
                         {"new_password": "NewAdmin1"}, **admin_headers)
        assert resp.status_code == 200
        target.refresh_from_db()
        assert target.check_password("NewAdmin1")


class TestForceLogout:

    def test_valid(self, api_client, admin_headers, seed_permissions):
        target = _make_user("flogout@test.com")
        Session.create_session(user=target)
        resp = post_json(api_client, f"/admin-api/users/{target.pk}/force-logout",
                         {}, **admin_headers)
        assert resp.status_code == 200
        assert Session.objects.filter(user=target, is_active=True).count() == 0


class TestUserSessions:

    def test_list(self, api_client, admin_headers, admin_user, admin_session):
        resp = api_client.get(f"/admin-api/users/{admin_user.pk}/sessions", **admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


class TestAssignRole:

    def test_assign(self, api_client, admin_headers, seed_permissions):
        target = _make_user("assignrole@test.com")
        role = Role.objects.get(slug="manager")
        resp = post_json(api_client, f"/admin-api/users/{target.pk}/roles",
                         {"role_id": role.pk}, **admin_headers)
        assert resp.status_code == 200
        assert target.has_role("manager")

    def test_remove(self, api_client, admin_headers, seed_permissions):
        target = _make_user("remrole@test.com")
        target.assign_role("driver")
        role = Role.objects.get(slug="driver")
        resp = delete_json(api_client, f"/admin-api/users/{target.pk}/roles/remove",
                           {"role_id": role.pk}, **admin_headers)
        assert resp.status_code == 200
        assert not target.has_role("driver")


class TestUserStats:

    def test_stats(self, api_client, admin_headers, admin_user):
        resp = api_client.get("/admin-api/users/stats", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_users" in data
        assert "active_sessions" in data
        assert "roles_breakdown" in data
