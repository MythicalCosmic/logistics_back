import pytest
from django.test import RequestFactory

from base.decorators.decorators import require_auth, require_permission, require_role
from base.models import User


pytestmark = pytest.mark.django_db


def _dummy_view(request):
    from django.http import JsonResponse
    return JsonResponse({"ok": True})


class TestRequireAuth:

    def test_authenticated(self, admin_user):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = admin_user

        view = require_auth(_dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_unauthenticated(self):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = None

        view = require_auth(_dummy_view)
        response = view(request)
        assert response.status_code == 401

    def test_non_user_object(self):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = "not_a_user"

        view = require_auth(_dummy_view)
        response = view(request)
        assert response.status_code == 401


class TestRequirePermission:

    def test_has_permission(self, admin_user):
        from base.services.role_permission_service import RolePermissionService
        RolePermissionService.cache_permissions(admin_user)

        factory = RequestFactory()
        request = factory.get("/test")
        request.user = admin_user

        view = require_permission("users.view")(_dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_missing_permission(self, driver_user):
        from base.services.role_permission_service import RolePermissionService
        RolePermissionService.cache_permissions(driver_user)

        factory = RequestFactory()
        request = factory.get("/test")
        request.user = driver_user

        view = require_permission("users.create")(_dummy_view)
        response = view(request)
        assert response.status_code == 403

    def test_unauthenticated(self):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = None

        view = require_permission("users.view")(_dummy_view)
        response = view(request)
        assert response.status_code == 401


class TestRequireRole:

    def test_has_role(self, admin_user):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = admin_user

        view = require_role("admin")(_dummy_view)
        response = view(request)
        assert response.status_code == 200

    def test_missing_role(self, driver_user):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = driver_user

        view = require_role("admin")(_dummy_view)
        response = view(request)
        assert response.status_code == 403

    def test_unauthenticated(self):
        factory = RequestFactory()
        request = factory.get("/test")
        request.user = None

        view = require_role("admin")(_dummy_view)
        response = view(request)
        assert response.status_code == 401
