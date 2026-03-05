import pytest
from base.models import ActivityLog
from conftest import make_load


pytestmark = pytest.mark.django_db


class TestListActivityLogs:

    def test_list(self, api_client, admin_headers, admin_user):
        ActivityLog.objects.create(user=admin_user, action="test.action", ip_address="127.0.0.1")
        resp = api_client.get("/admin-api/activity-logs", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "logs" in data
        assert "pagination" in data
        assert len(data["logs"]) >= 1

    def test_filter_by_user(self, api_client, admin_headers, admin_user, manager_user):
        ActivityLog.objects.create(user=admin_user, action="admin.action")
        ActivityLog.objects.create(user=manager_user, action="manager.action")
        resp = api_client.get(f"/admin-api/activity-logs?user_id={admin_user.pk}", **admin_headers)
        logs = resp.json()["data"]["logs"]
        assert all(log["user"]["id"] == admin_user.pk for log in logs)

    def test_filter_by_action(self, api_client, admin_headers, admin_user):
        ActivityLog.objects.create(user=admin_user, action="login")
        ActivityLog.objects.create(user=admin_user, action="logout")
        resp = api_client.get("/admin-api/activity-logs?action=login", **admin_headers)
        logs = resp.json()["data"]["logs"]
        assert all(log["action"] == "login" for log in logs)

    def test_search(self, api_client, admin_headers, admin_user):
        ActivityLog.objects.create(user=admin_user, action="unique.search.action")
        resp = api_client.get("/admin-api/activity-logs?search=unique.search", **admin_headers)
        logs = resp.json()["data"]["logs"]
        assert len(logs) >= 1

    def test_filter_by_load(self, api_client, admin_headers, admin_user):
        load = make_load(admin_user)
        ActivityLog.objects.create(user=admin_user, action="load.created", load=load)
        resp = api_client.get(f"/admin-api/activity-logs?load_id={load.pk}", **admin_headers)
        logs = resp.json()["data"]["logs"]
        assert len(logs) >= 1

    def test_permission_required(self, api_client, driver_headers):
        resp = api_client.get("/admin-api/activity-logs", **driver_headers)
        assert resp.status_code == 403


class TestGetActivityLog:

    def test_valid(self, api_client, admin_headers, admin_user):
        log = ActivityLog.objects.create(
            user=admin_user, action="test.detail", details={"key": "value"}
        )
        resp = api_client.get(f"/admin-api/activity-logs/{log.pk}", **admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "test.detail"
        assert data["details"] == {"key": "value"}

    def test_not_found(self, api_client, admin_headers):
        resp = api_client.get("/admin-api/activity-logs/99999", **admin_headers)
        assert resp.status_code == 404

    def test_permission_required(self, api_client, driver_headers, admin_user):
        log = ActivityLog.objects.create(user=admin_user, action="test")
        resp = api_client.get(f"/admin-api/activity-logs/{log.pk}", **driver_headers)
        assert resp.status_code == 403
