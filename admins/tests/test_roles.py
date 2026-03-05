import pytest
from base.models import Role, Permission, RolePermission
from conftest import post_json, put_json, delete_json


pytestmark = pytest.mark.django_db


class TestListRoles:

    def test_list(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/roles", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 4  # Admin, Manager, Dispatcher, Driver

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/roles", **driver_headers)
        assert resp.status_code == 403


class TestCreateRole:

    def test_valid(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/roles/create", {
            "name": "Custom Role",
            "slug": "custom-role",
            "description": "A custom role",
        }, **admin_headers)
        assert resp.status_code == 201
        assert Role.objects.filter(slug="custom-role").exists()

    def test_duplicate_slug(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/roles/create", {
            "name": "Another Admin",
            "slug": "admin",
        }, **admin_headers)
        assert resp.status_code == 400

    def test_duplicate_name(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/roles/create", {
            "name": "Admin",
            "slug": "admin-dup",
        }, **admin_headers)
        assert resp.status_code == 400

    def test_missing_fields(self, api_client, admin_headers):
        resp = post_json(api_client, "/admin-api/roles/create", {}, **admin_headers)
        assert resp.status_code == 400


class TestGetRole:

    def test_valid(self, api_client, admin_headers, admin_role):
        resp = api_client.get(f"/admin-api/roles/{admin_role.pk}", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["slug"] == "admin"
        assert "permissions" in data

    def test_not_found(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/roles/99999", **admin_headers)
        assert resp.status_code == 404


class TestUpdateRole:

    def test_valid(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="ToUpdate", slug="to-update")
        resp = put_json(api_client, f"/admin-api/roles/{role.pk}/update",
                        {"description": "Updated"}, **admin_headers)
        assert resp.status_code == 200
        role.refresh_from_db()
        assert role.description == "Updated"

    def test_not_found(self, api_client, admin_headers):
        resp = put_json(api_client, "/admin-api/roles/99999/update",
                        {"description": "X"}, **admin_headers)
        assert resp.status_code == 404


class TestDeleteRole:

    def test_valid(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="ToDelete", slug="to-delete")
        resp = delete_json(api_client, f"/admin-api/roles/{role.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 200
        assert not Role.objects.filter(slug="to-delete").exists()

    def test_cannot_delete_default_role(self, api_client, admin_headers, driver_role):
        resp = delete_json(api_client, f"/admin-api/roles/{driver_role.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 400

    def test_cannot_delete_role_with_users(self, api_client, admin_headers, admin_role, admin_user):
        resp = delete_json(api_client, f"/admin-api/roles/{admin_role.pk}/delete",
                           {}, **admin_headers)
        assert resp.status_code == 400


class TestAssignPermission:

    def test_assign(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="PermRole", slug="perm-role")
        perm = Permission.objects.first()
        resp = post_json(api_client, f"/admin-api/roles/{role.pk}/permissions",
                         {"permission_id": perm.pk}, **admin_headers)
        assert resp.status_code == 200
        assert RolePermission.objects.filter(role=role, permission=perm).exists()

    def test_remove(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="PermRole2", slug="perm-role-2")
        perm = Permission.objects.first()
        RolePermission.objects.create(role=role, permission=perm)
        resp = delete_json(api_client, f"/admin-api/roles/{role.pk}/permissions/remove",
                           {"permission_id": perm.pk}, **admin_headers)
        assert resp.status_code == 200
        assert not RolePermission.objects.filter(role=role, permission=perm).exists()

    def test_already_assigned(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="DupPerm", slug="dup-perm")
        perm = Permission.objects.first()
        RolePermission.objects.create(role=role, permission=perm)
        resp = post_json(api_client, f"/admin-api/roles/{role.pk}/permissions",
                         {"permission_id": perm.pk}, **admin_headers)
        assert resp.status_code == 400


class TestBulkAssignPermissions:

    def test_bulk_assign(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="BulkRole", slug="bulk-role")
        perm_ids = list(Permission.objects.values_list("pk", flat=True)[:3])
        resp = post_json(api_client, f"/admin-api/roles/{role.pk}/permissions/bulk",
                         {"permission_ids": perm_ids}, **admin_headers)
        assert resp.status_code == 200
        assert RolePermission.objects.filter(role=role).count() == 3

    def test_partial_existing(self, api_client, admin_headers, seed_permissions):
        role = Role.objects.create(name="BulkRole2", slug="bulk-role-2")
        perms = list(Permission.objects.all()[:3])
        RolePermission.objects.create(role=role, permission=perms[0])
        perm_ids = [p.pk for p in perms]
        resp = post_json(api_client, f"/admin-api/roles/{role.pk}/permissions/bulk",
                         {"permission_ids": perm_ids}, **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["assigned"] == 2
        assert data["skipped"] == 1


class TestListPermissions:

    def test_list(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/permissions", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "permissions" in data
        assert "grouped" in data
        assert data["total"] > 0


class TestRoleStats:

    def test_stats(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/roles/stats", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_roles" in data
        assert "total_permissions" in data
